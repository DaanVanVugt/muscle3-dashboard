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

**Start the server** where the environment is set up:

```bash
module load IMAS-MUSCLE3        # whatever puts m3dash on PATH
m3dash serve
```

`m3dash serve` runs in the foreground. Note that `m3dash` often lives
behind `module load`, which a non-interactive ssh shell does *not* run.

## TCP access

On a desktop session running on the node itself (e.g. NoMachine),
`m3dash open` serves on a loopback TCP port and opens a browser at the
page. Pick the port with `--port`; the default is a deterministic
per-user port (`20000 + uid % 10000`).

A loopback TCP port is also the fallback where sshd prohibits
unix-socket forwarding (the symptom is `administratively prohibited:
open failed` while normal `-L` port forwards work): run `m3dash open
--no-open-browser` and forward the port with a plain `LocalForward
127.0.0.1:<port> 127.0.0.1:<port>`. Note that unlike the 0600 socket, a
loopback port is connectable by other users on the same node.

## Commands

* `m3dash serve` — run the server on a unix socket (blocking).
  `--socket`, `--local-port`.
* `m3dash open` — serve on a loopback TCP port and open a browser
  (blocking). `--port`, `--open-browser`/`--no-open-browser`.
* `m3dash ls [--json]` — list discovered runs on the terminal.

Run roots are configured in `~/.config/m3dash/roots` (one path per
line, default `$HOME`); the server re-reads it on every rescan, so
edits apply without a restart.

Clicking a run opens its per-run dashboard (see "How to use" above).
