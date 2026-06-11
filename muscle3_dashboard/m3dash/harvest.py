"""Harvest served-UI URLs that MUSCLE3 actors print to their logs.

Many actors start a web server (a Panel/Bokeh dashboard, a Dash app, a
plain http.server, ...) and announce it on stdout, e.g.::

    Launching server at http://localhost:53711

This module scans the instance logs of a run for *any* ``http(s)://``
URL and, where the URL points at loopback (``localhost`` /
``127.0.0.1``), resolves the node the actor actually runs on so the URL
can be reached from elsewhere. It is deliberately actor-agnostic: it
keys off the URL text, not any IMAS-MUSCLE3 specifics.

Node resolution, in order of preference:

1. The URL already names a non-loopback host or IP -> use it.
2. The per-node agent log filename: ``logs/muscle3_agent_<host>.log``
   whose body contains ``Starting process <instance>``.
3. The manager log's ``Connecting to peer <instance> at tcp:<host>:..``
   lines (INFO level). NB these name *sender* instances (a receiver
   connects to its sender), so a receive-only actor will not appear
   here; hence this is a fallback to (2).
4. A caller-provided fallback node (the run's discovery node).
"""

import re
from dataclasses import dataclass
from pathlib import Path

#: Hosts that need resolving to a real node.
_LOOPBACK = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}

#: Bytes read per log file. URL announcements are near the top, but a
#: server may (re)announce later; cap generously rather than read all.
_MAX_READ = 2 * 1024 * 1024

_URL_RE = re.compile(
    r"""https?://
        (?P<host>\[[0-9a-fA-F:]+\] | [A-Za-z0-9][A-Za-z0-9.\-]*)   # host or [ipv6]
        (?::(?P<port>\d{1,5}))?                                     # :port
        (?P<path>/[^\s'"<>)\]]*)?                                   # /path
    """,
    re.VERBOSE,
)

_AGENT_LOG_RE = re.compile(r"muscle3_agent_(?P<host>.+)\.log$")
_STARTING_RE = re.compile(r"Starting process (?P<instance>\S+)")
_PEER_RE = re.compile(
    r"Connecting to peer (?P<instance>\S+) at tcp:(?P<host>[^,:\s]+):"
)


@dataclass
class HarvestedURL:
    instance: str
    original: str
    host: str
    port: int | None
    path: str
    node: str | None  # resolved node, or None if still loopback
    source: str  # which resolver supplied the node

    @property
    def reachable_url(self) -> str:
        host = self.node or self.host
        netloc = host if self.port is None else f"{host}:{self.port}"
        return f"http://{netloc}{self.path or '/'}"

    @property
    def resolved(self) -> bool:
        return self.host.lower() not in _LOOPBACK or self.node is not None

    def to_dict(self) -> dict:
        return {
            "instance": self.instance,
            "original": self.original,
            "reachable_url": self.reachable_url,
            "node": self.node,
            "port": self.port,
            "resolved": self.resolved,
            "source": self.source,
        }


def _read_head(path: Path) -> str:
    try:
        with path.open("rb") as f:
            return f.read(_MAX_READ).decode("utf-8", errors="replace")
    except OSError:
        return ""


def instance_nodes_from_agents(run_dir: Path) -> dict[str, str]:
    """Map instance -> node from per-node agent logs."""
    mapping: dict[str, str] = {}
    logs = run_dir / "logs"
    if not logs.is_dir():
        return mapping
    for log in logs.glob("muscle3_agent_*.log"):
        m = _AGENT_LOG_RE.search(log.name)
        if not m:
            continue
        host = m.group("host")
        for sm in _STARTING_RE.finditer(_read_head(log)):
            mapping.setdefault(sm.group("instance"), host)
    return mapping


def sender_nodes_from_manager(run_dir: Path) -> dict[str, str]:
    """Map instance -> node from manager 'Connecting to peer' lines."""
    mapping: dict[str, str] = {}
    text = _read_head(run_dir / "muscle3_manager.log")
    for m in _PEER_RE.finditer(text):
        mapping.setdefault(m.group("instance"), m.group("host"))
    return mapping


def _instance_base(instance_id: str) -> str:
    """Strip a libmuscle index suffix, e.g. 'macro[3]' -> 'macro'."""
    return instance_id.split("[", 1)[0]


def harvest_run(run_dir: Path, fallback_node: str | None = None) -> list[HarvestedURL]:
    """Find served-UI URLs in a run's instance logs and resolve nodes."""
    instances_dir = run_dir / "instances"
    if not instances_dir.is_dir():
        return []
    agents = instance_nodes_from_agents(run_dir)
    senders = sender_nodes_from_manager(run_dir)

    def resolve(instance: str, host: str) -> tuple[str | None, str]:
        if host.lower() not in _LOOPBACK:
            return host, "url"
        for table, name in ((agents, "agent-log"), (senders, "manager-log")):
            node = table.get(instance) or table.get(_instance_base(instance))
            if node:
                return node, name
        if fallback_node:
            return fallback_node, "run-node"
        return None, "unresolved"

    found: dict[tuple, HarvestedURL] = {}
    for inst_dir in sorted(instances_dir.iterdir()):
        if not inst_dir.is_dir():
            continue
        instance = inst_dir.name
        for fname in ("stdout.txt", "stderr.txt"):
            for m in _URL_RE.finditer(_read_head(inst_dir / fname)):
                host = m.group("host")
                port = int(m.group("port")) if m.group("port") else None
                path = m.group("path") or ""
                node, source = resolve(instance, host)
                key = (instance, host, port, path)
                if key not in found:
                    found[key] = HarvestedURL(
                        instance=instance,
                        original=m.group(0),
                        host=host,
                        port=port,
                        path=path,
                        node=node,
                        source=source,
                    )
    return list(found.values())
