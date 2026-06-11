"""Tests for harvesting served-UI URLs and resolving their nodes."""

from pathlib import Path

from muscle3_dashboard.m3dash import harvest


def _make_run(root: Path, *, instances, agents=None, manager_lines=()):
    """Build a synthetic run dir.

    instances: {name: {"stdout": str, "stderr": str}}
    agents:    {node_hostname: [instance, ...]}  -> agent log files
    manager_lines: extra lines for muscle3_manager.log
    """
    (root / "instances").mkdir(parents=True)
    for name, files in instances.items():
        d = root / "instances" / name
        d.mkdir()
        (d / "stdout.txt").write_text(files.get("stdout", ""))
        (d / "stderr.txt").write_text(files.get("stderr", ""))
    logs = root / "logs"
    logs.mkdir()
    for node, started in (agents or {}).items():
        body = "".join(f"2026 INFO Starting process {i}\n" for i in started)
        (logs / f"muscle3_agent_{node}.log").write_text(body)
    (root / "muscle3_manager.log").write_text("\n".join(manager_lines) + "\n")
    return root


def test_url_with_real_host_used_directly(tmp_path):
    run = _make_run(
        tmp_path / "r",
        instances={"viz": {"stdout": "UI at http://10.0.0.5:9000/dash"}},
    )
    (url,) = harvest.harvest_run(run)
    assert url.resolved
    assert url.source == "url"
    assert url.reachable_url == "http://10.0.0.5:9000/dash"


def test_localhost_resolved_via_agent_log(tmp_path):
    run = _make_run(
        tmp_path / "r",
        instances={"viz": {"stdout": "Launching server at http://localhost:53711"}},
        agents={"nodeA.iter.org": ["viz"]},
    )
    (url,) = harvest.harvest_run(run)
    assert url.source == "agent-log"
    assert url.node == "nodeA.iter.org"
    assert url.reachable_url == "http://nodeA.iter.org:53711/"


def test_localhost_resolved_via_manager_peer_line(tmp_path):
    run = _make_run(
        tmp_path / "r",
        instances={"src": {"stdout": "http://127.0.0.1:8050/"}},
        manager_lines=[
            "muscle_manager 2026 INFO libmuscle.communicator: "
            "Connecting to peer src at tcp:nodeB.iter.org:14000"
        ],
    )
    (url,) = harvest.harvest_run(run)
    assert url.source == "manager-log"
    assert url.node == "nodeB.iter.org"


def test_unresolved_without_node_info(tmp_path):
    run = _make_run(
        tmp_path / "r",
        instances={"viz": {"stdout": "http://localhost:7000/"}},
    )
    (url,) = harvest.harvest_run(run)
    assert not url.resolved
    assert url.node is None


def test_fallback_node(tmp_path):
    run = _make_run(
        tmp_path / "r",
        instances={"viz": {"stdout": "http://localhost:7000/"}},
    )
    (url,) = harvest.harvest_run(run, fallback_node="login01")
    assert url.resolved
    assert url.source == "run-node"
    assert url.node == "login01"


def test_no_urls_returns_empty(tmp_path):
    run = _make_run(tmp_path / "r", instances={"sink": {"stdout": "nothing here"}})
    assert harvest.harvest_run(run) == []


def test_agent_log_maps_real_asset():
    asset = Path(__file__).parent / "assets" / "run-accumulator"
    mapping = harvest.instance_nodes_from_agents(asset)
    # the asset's agent log is muscle3_agent_98dci4-srv-1005.iter.org.log
    assert mapping
    assert all(node.endswith("iter.org") for node in mapping.values())
