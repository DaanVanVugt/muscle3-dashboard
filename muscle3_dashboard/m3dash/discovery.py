"""Discovery of MUSCLE3 runs belonging to the current user.

Three sources are combined:

1. ``squeue``: workdirs of the user's SLURM jobs are scanned for run
   directories, which also yields a job id and job state.
2. ``pgrep``: ``muscle_manager`` processes running on this host (e.g. a
   login node), which yields a pid and run dir from the command line.
3. A bounded filesystem scan of configured *run roots* (default: the
   user's home directory), which also finds finished runs.

A run directory is defined as a directory containing a
``muscle3_manager.log`` file. inotify is deliberately not used: run
directories typically live on shared filesystems (NFS/GPFS) where events
generated on other hosts are not delivered, so callers should rescan
periodically instead.
"""

import getpass
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

MANAGER_LOG = "muscle3_manager.log"

#: Directory names that are never descended into during filesystem scans.
PRUNE_DIRS = frozenset(
    {
        ".git",
        ".svn",
        ".cache",
        ".conda",
        ".local",
        "node_modules",
        "__pycache__",
        "site-packages",
        "venv",
        ".venv",
    }
)

#: Maximum directory depth (relative to a run root) for filesystem scans.
MAX_SCAN_DEPTH = 8

#: Bytes of ``muscle3_manager.log`` tail inspected for status detection.
_TAIL_BYTES = 8192

_SUCCESS_RE = re.compile(r"The simulation finished without error\.")
_FAILURE_RE = re.compile(
    r"crashed|finished with exit code [1-9]|Instantiator crashed"
)


class RunStatus(Enum):
    """Status of a discovered run."""

    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass
class Run:
    """A discovered MUSCLE3 run directory."""

    run_dir: Path
    status: RunStatus = RunStatus.UNKNOWN
    #: Discovery sources that found this run ("slurm", "process", "scan")
    sources: list[str] = field(default_factory=list)
    job_id: str | None = None
    job_state: str | None = None
    pid: int | None = None
    last_updated: datetime | None = None

    @property
    def name(self) -> str:
        return self.run_dir.name

    def to_dict(self) -> dict:
        return {
            "run_dir": str(self.run_dir),
            "name": self.name,
            "status": self.status.value,
            "sources": self.sources,
            "job_id": self.job_id,
            "job_state": self.job_state,
            "pid": self.pid,
            "last_updated": (
                self.last_updated.isoformat() if self.last_updated else None
            ),
        }


def _log_status(run_dir: Path) -> tuple[RunStatus, datetime | None]:
    """Determine run status from the tail of the manager log."""
    logfile = run_dir / MANAGER_LOG
    try:
        stat = logfile.stat()
        with logfile.open("rb") as f:
            f.seek(max(0, stat.st_size - _TAIL_BYTES))
            tail = f.read().decode("utf-8", errors="replace")
    except OSError:
        return RunStatus.UNKNOWN, None
    mtime = datetime.fromtimestamp(stat.st_mtime)
    if _SUCCESS_RE.search(tail):
        return RunStatus.FINISHED, mtime
    if _FAILURE_RE.search(tail):
        return RunStatus.FAILED, mtime
    return RunStatus.UNKNOWN, mtime


def _scan_tree(root: Path, max_depth: int = MAX_SCAN_DEPTH) -> list[Path]:
    """Find run directories under root, bounded in depth, with pruning."""
    run_dirs = []
    root = root.expanduser()
    if not root.is_dir():
        return run_dirs
    base_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        depth = len(Path(dirpath).parts) - base_depth
        if depth >= max_depth:
            dirnames[:] = []
            continue
        dirnames[:] = [
            d for d in dirnames if d not in PRUNE_DIRS and not d.startswith(".")
        ]
        if MANAGER_LOG in filenames:
            run_dirs.append(Path(dirpath))
            # run dirs do not contain nested run dirs, except snapshots of
            # sub-runs; don't descend
            dirnames[:] = []
    return run_dirs


def _run_command(args: list[str], timeout: float = 10.0) -> str | None:
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def scan_slurm_jobs() -> list[Run]:
    """Discover runs in the working directories of the user's SLURM jobs."""
    out = _run_command(
        [
            "squeue",
            "--noheader",
            "--user",
            getpass.getuser(),
            "--format",
            "%i|%T|%Z",
        ]
    )
    if out is None:
        return []
    runs = []
    for line in out.splitlines():
        parts = line.strip().split("|")
        if len(parts) != 3:
            continue
        job_id, job_state, workdir = parts
        for run_dir in _scan_tree(Path(workdir), max_depth=4):
            status, mtime = _log_status(run_dir)
            if status is RunStatus.UNKNOWN and job_state == "RUNNING":
                status = RunStatus.RUNNING
            runs.append(
                Run(
                    run_dir=run_dir,
                    status=status,
                    sources=["slurm"],
                    job_id=job_id,
                    job_state=job_state,
                    last_updated=mtime,
                )
            )
    return runs


def _manager_run_dir(pid: int, cmdline: str) -> Path | None:
    """Extract the run dir of a muscle_manager process."""
    try:
        cwd = Path(os.readlink(f"/proc/{pid}/cwd"))
    except OSError:
        cwd = Path.cwd()
    match = re.search(r"--run-dir[= ](\S+)", cmdline)
    if match:
        run_dir = Path(match.group(1))
        if not run_dir.is_absolute():
            run_dir = cwd / run_dir
        return run_dir
    # No --run-dir: the manager created run_<model>_<date>-<time> in its cwd;
    # pick the newest one.
    candidates = sorted(
        (d for d in cwd.glob("run_*") if (d / MANAGER_LOG).exists()),
        key=lambda d: d.stat().st_mtime,
    )
    return candidates[-1] if candidates else None


def scan_processes() -> list[Run]:
    """Discover runs of muscle_manager processes on this host."""
    out = _run_command(
        ["pgrep", "--uid", getpass.getuser(), "-af", "muscle_manager"]
    )
    if out is None:
        return []
    runs = []
    for line in out.splitlines():
        pid_str, _, cmdline = line.strip().partition(" ")
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        run_dir = _manager_run_dir(pid, cmdline)
        if run_dir is None or not (run_dir / MANAGER_LOG).exists():
            continue
        _, mtime = _log_status(run_dir)
        runs.append(
            Run(
                run_dir=run_dir,
                status=RunStatus.RUNNING,
                sources=["process"],
                pid=pid,
                last_updated=mtime,
            )
        )
    return runs


def scan_roots(roots: list[Path]) -> list[Run]:
    """Discover runs by scanning the filesystem under the given roots."""
    runs = []
    for root in roots:
        for run_dir in _scan_tree(root):
            status, mtime = _log_status(run_dir)
            runs.append(
                Run(
                    run_dir=run_dir,
                    status=status,
                    sources=["scan"],
                    last_updated=mtime,
                )
            )
    return runs


def discover_runs(roots: list[Path]) -> list[Run]:
    """Discover runs from all sources, merged by run directory.

    SLURM and process sources take precedence for liveness information;
    the filesystem scan contributes runs that are no longer active.
    Results are sorted by last update time, newest first.
    """
    merged: dict[Path, Run] = {}
    for run in scan_slurm_jobs() + scan_processes() + scan_roots(roots):
        key = run.run_dir.resolve()
        if key not in merged:
            run.run_dir = key
            merged[key] = run
            continue
        existing = merged[key]
        existing.sources.extend(
            s for s in run.sources if s not in existing.sources
        )
        existing.job_id = existing.job_id or run.job_id
        existing.job_state = existing.job_state or run.job_state
        existing.pid = existing.pid or run.pid
        if existing.status is RunStatus.UNKNOWN:
            existing.status = run.status
    runs = list(merged.values())
    runs.sort(
        key=lambda r: r.last_updated or datetime.fromtimestamp(0), reverse=True
    )
    return runs


def runs_to_json(runs: list[Run]) -> str:
    return json.dumps([run.to_dict() for run in runs], indent=2)
