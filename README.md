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
`$HOME`) and serves a landing page plus per-run dashboards on a single
per-user unix socket: `~/.m3dash.sock` (mode 0600).

On your own machine, add to `~/.ssh/config`. The `%r` token expands to
the remote username, so the same line works for every user:

```
Host hpc
    HostName <login-node-fqdn>
    LocalForward 127.0.0.1:4333 /home/ITER/%r/.m3dash.sock
    ExitOnForwardFailure no
```

Pin one specific login node: unix sockets are host-local even on a
shared filesystem, so sshd and m3dash must be on the same machine.

On the cluster, add to `~/.bashrc`:

```bash
command -v m3dash >/dev/null && m3dash ensure
```

Then every `ssh hpc` doubles as the tunnel and http://localhost:4333 is a
permanent bookmark. If you forward a different local port, pass
`--local-port` to `m3dash serve` so the websocket origin check matches.

Other commands: `m3dash ls [--json]` lists discovered runs;
`m3dash serve --tcp 5006` also serves on loopback TCP for debugging;
extra run roots can be added in the UI, with `--root`, or in
`~/.config/m3dash/roots`.
