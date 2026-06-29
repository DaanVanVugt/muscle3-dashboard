from muscle3_dashboard.dashboard import _dashboard_version


def test_version():
    # Resolves the installed distribution version, or falls back to
    # setuptools_scm when running from a source checkout.
    version = _dashboard_version()
    assert "unknown" not in version
    assert version != ""
    assert version != "dev"
