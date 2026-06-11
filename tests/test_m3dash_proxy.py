"""Tests for the per-target subdomain proxy token scheme."""

import re

import pytest

from muscle3_dashboard.m3dash import proxy


@pytest.mark.parametrize(
    "host,port",
    [
        ("localhost", 53711),
        ("127.0.0.1", 8050),
        ("nodeB.iter.org", 14000),
        ("10.20.30.40", 9000),
    ],
)
def test_token_roundtrip(host, port):
    token = proxy.encode_target(host, port)
    assert proxy.decode_target(token) == (host, port)


def test_token_is_a_single_dns_label():
    token = proxy.encode_target("nodeB.iter.org", 14000)
    # one label: lowercase, no dots/colons/uppercase, fits in 63 chars
    assert "." not in token and ":" not in token
    assert token == token.lower()
    assert len(token) <= 63
    assert re.fullmatch(r"t[a-z2-7]+", token)


def test_decode_rejects_garbage():
    for bad in ["", "x", "tnotbase32!!", "abcdef"]:
        with pytest.raises(ValueError):
            proxy.decode_target(bad)


def test_subdomain_host():
    sub = proxy.subdomain_host("127.0.0.1", 8050, "localhost:4333")
    assert sub.endswith(".localhost:4333")
    token = sub.split(".", 1)[0]
    assert proxy.decode_target(token) == ("127.0.0.1", 8050)


def test_host_pattern_matches_only_subdomains():
    token = proxy.encode_target("127.0.0.1", 8050)
    assert re.match(proxy.PROXY_HOST_PATTERN, f"{token}.localhost:4333")
    assert re.match(proxy.PROXY_HOST_PATTERN, f"{token}.localhost")
    # the dashboard's own host must NOT be caught by the proxy route
    assert not re.match(proxy.PROXY_HOST_PATTERN, "localhost:4333")
    assert not re.match(proxy.PROXY_HOST_PATTERN, "node.iter.org:4333")
