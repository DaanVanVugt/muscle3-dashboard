# Panel dashboard for MUSCLE3 simulations
muscle_dashboard is a Panel based dashboard for log parsing and debugging of MUSCLE3 simulations.

# Installation
Quick developer installation guide

```bash
git clone git@github.com:multiscale/muscle3-dashboard.git
cd muscle3-dashboard
python3 -m venv ./venv
. venv/bin/activate
pip install -e .[dev]
pytest
```

The per-run **simulation graph** is drawn from the run's `configuration.ymmsl`
by [`ymmsl2svg`](https://github.com/multiscale/ymmsl2svg), an optional
dependency. Install it with the `graph` extra (without it the rest of the
dashboard works and the graph card is simply hidden):

```bash
pip install -e .[dev,graph]
```

# How to use
```bash
# make sure your virtual environment is activated
muscle_dashboard path/to/my/muscle/simulation/workdir
```

# Legal

Copyright 2026 ITER Organization. The code in this repository is licensed under the
[Apache-2.0 license](LICENSE.txt)

# m3dash: all your runs behind one SSH forward

`m3dash` finds your MUSCLE3 runs (via SLURM, local `muscle_manager`
processes, and a filesystem scan of configurable run roots, default
`$HOME`) and serves a landing page that lists them plus a per-run
dashboard for each, on a single per-user unix socket: `~/.m3dash.sock`
(mode 0600).

On your own machine, add to `~/.ssh/config`. The `%r` token expands to
the remote username, so the same line works for every user (ITER SDCC
example):

```
Host sdcc1
    HostName sdcc1.iter.org
    LocalForward 127.0.0.1:4333 /home/ITER/%r/.m3dash.sock
    ExitOnForwardFailure no
```

Then http://localhost:4333 is a permanent bookmark for the runs index.
Pin one specific login node: unix sockets are host-local even on a
shared filesystem, so sshd and m3dash must be on the same machine.

**Start the server** where the environment is set up. On a module-based
cluster the `m3dash` command lives behind `module load`, which a
non-interactive ssh shell does *not* run, so start it from an
interactive context — add to `~/.bashrc`:

```bash
module load IMAS-MUSCLE3        # whatever puts m3dash on PATH
command -v m3dash >/dev/null && m3dash ensure
```

(for always-on without an interactive login, run the same from a
`cron @reboot` or a `systemd --user` unit instead).

## TCP access

Many sites prohibit unix-socket forwarding (the symptom is
`administratively prohibited: open failed` while normal `-L` port
forwards work). For those, m3dash also listens on a deterministic
per-user loopback TCP port (`20000 + uid % 10000`); forward it with a
plain `LocalForward 127.0.0.1:<port> 127.0.0.1:<port>`. Disable it with
`m3dash serve --no-tcp`, or pick a port with `--tcp <port>`. Note that
unlike the 0600 socket, a loopback port is connectable by other users
on the same node.

When serving on TCP from a desktop session (e.g. NoMachine, detected
via `$DISPLAY`), `m3dash serve` opens a browser at the page
automatically; force it on/off with `--open-browser` / `--no-open-browser`.

## Commands

* `m3dash serve` — run the server (blocking). `--tcp`/`--no-tcp`,
  `--socket`, `--address`, `--ws-origin`, `--open-browser`.
* `m3dash ensure` — start `serve` in the background unless it is already
  running; idempotent and quiet, for `~/.bashrc`.
* `m3dash ls [--json]` — list discovered runs on the terminal.

Run roots are configured in `~/.config/m3dash/roots` (one path per
line, default `$HOME`); the server re-reads it on every rescan, so
edits apply without a restart.

## The per-run dashboard

Clicking a run opens its dashboard, a single page top to bottom:

* a **simulation graph** of the coupling (from `configuration.ymmsl` via
  the optional `graph` extra), with components coloured by status
  (running / finished / crashed) and the likely-responsible component on
  a crash outlined and its log opened automatically; click any component
  to inspect it;
* a **component summary** for the clicked component — a port block plus
  its program, settings and description, with referenced text files as
  inline links that open in a read-only viewer (with copy-path and
  copy-contents buttons);
* the **log files** — the manager log and each component's stdout/stderr,
  with an instance selector for multiplicity (vector-port) components.
