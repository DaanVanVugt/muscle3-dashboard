import importlib.metadata


def test_version():
    version = importlib.metadata.version("muscle3-dashboard")
    assert "unknown" not in version
    assert version != ""
