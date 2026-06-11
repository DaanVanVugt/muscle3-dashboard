"""Tests for the stdio multiplexer used by ``m3dash connect``/``pipe``."""

import os
import socket
import threading
import time

from muscle3_dashboard.m3dash import mux


def test_frame_roundtrip():
    r, w = os.pipe()
    try:
        writer = mux.FrameWriter(w)
        writer.send(mux.DATA, 7, b"hello")
        writer.send(mux.OPEN, 3)
        assert mux._read_frame(r) == (mux.DATA, 7, b"hello")
        assert mux._read_frame(r) == (mux.OPEN, 3, b"")
    finally:
        os.close(r)
        os.close(w)


def _echo_backend():
    """connect_backend that echoes everything, each stream isolated."""
    near, far = socket.socketpair()

    def echo():
        try:
            while True:
                chunk = far.recv(4096)
                if not chunk:
                    break
                far.sendall(chunk)
        except OSError:
            pass
        finally:
            far.close()

    threading.Thread(target=echo, daemon=True).start()
    return near


def test_mux_end_to_end_echo():
    # Two pipes form the single bidirectional channel a real ssh exec
    # would provide: client -> server and server -> client.
    c2s_r, c2s_w = os.pipe()
    s2c_r, s2c_w = os.pipe()

    server = threading.Thread(
        target=mux.serve, args=(c2s_r, s2c_w, _echo_backend), daemon=True
    )
    server.start()

    client = mux.MuxClient(s2c_r, c2s_w)  # reads handshake (skips banners)

    # Two independent logical streams over the one channel.
    results = {}

    def exercise(name, payload):
        local, app_side = socket.socketpair()
        client.add(app_side)
        local.sendall(payload)
        got = b""
        local.settimeout(5)
        while len(got) < len(payload):
            got += local.recv(4096)
        results[name] = got
        local.close()

    t1 = threading.Thread(target=exercise, args=("a", b"x" * 1000))
    t2 = threading.Thread(target=exercise, args=("b", b"y" * 2000))
    t1.start()
    t2.start()
    t1.join(10)
    t2.join(10)

    assert results["a"] == b"x" * 1000
    assert results["b"] == b"y" * 2000


def test_mux_client_skips_banner():
    # A login shell may print noise before the handshake; the client
    # must resync on the handshake marker.
    c2s_r, c2s_w = os.pipe()
    s2c_r, s2c_w = os.pipe()
    os.write(s2c_w, b"MOTD: welcome to the cluster\n")  # banner noise
    threading.Thread(
        target=mux.serve, args=(c2s_r, s2c_w, _echo_backend), daemon=True
    ).start()
    # If the handshake is not found, MuxClient(...) would block; guard it.
    done = threading.Event()
    threading.Thread(
        target=lambda: (mux.MuxClient(s2c_r, c2s_w), done.set()), daemon=True
    ).start()
    assert done.wait(5), "handshake not recognised past banner"
