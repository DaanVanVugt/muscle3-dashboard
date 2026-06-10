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

Many sites prohibit unix-socket forwarding (the symptom is
`administratively prohibited: open failed` while normal `-L` port
forwards work). For those, m3dash also listens on a deterministic
per-user loopback TCP port (`20000 + uid % 10000`); run `m3dash
sshline` on the login node to print the matching ssh config block.
Note that unlike the 0600 socket, a loopback port is connectable by
other users on the same node.

## When all forwarding is prohibited

Some sites disable *both* TCP and unix-socket forwarding, so every
`ssh -L`/`-R`/`-D` fails with `administratively prohibited`. ssh
*exec* channels (running a command) are not forwarding and stay
allowed, so m3dash tunnels over one:

```bash
# on your machine (needs only python3 + ssh; no socat):
m3dash connect <login-node> --local-port 4333
```

By default `connect` runs a single `ssh <login-node> m3dash pipe
--mux` and multiplexes every browser connection over that one channel
(one authentication, no per-connection ssh setup) -- so it works well
even without an ssh ControlMaster.

With `--no-mux` it instead runs one `ssh <login-node> m3dash pipe` per
browser connection; for that mode add an ssh ControlMaster so each
connection reuses one authenticated session:

```
Host <login-node>
    ControlMaster auto
    ControlPath ~/.ssh/cm-%r@%h:%p
    ControlPersist 10m
```

Pass through a bastion with `--ssh 'ssh -J bastion'`, and target a
non-default remote socket with `--remote-socket`.

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


## Reaching live actor UIs (proxy)

When a run is active, m3dash harvests any `http://...` URL its actors
print and reverse-proxies each one under its own subdomain of the
address you already use, e.g. `http://t<token>.localhost:4333`. Because
browsers resolve any `*.localhost` name to loopback, this needs no DNS
and no extra forward -- it rides the same socket/`connect` tunnel as the
dashboard. The per-run page lists these links per component under a
"Web UIs" card.

A subdomain (not a path prefix) is used so the actor's absolute
`/static` and `/ws` URLs keep working, and the proxy rewrites the
WebSocket `Origin` to `localhost:<target-port>` so the target's Bokeh
origin check passes. Subdomain proxying works over the loopback access
path (socket or `m3dash connect`); set `--local-port` to match the port
you reach m3dash on so the generated links are correct.