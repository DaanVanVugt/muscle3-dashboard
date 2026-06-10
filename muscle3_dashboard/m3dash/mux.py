"""A tiny stream multiplexer for tunnelling over one ssh exec channel.

``m3dash connect`` can either spawn one ``ssh <host> m3dash pipe`` per
browser connection (relying on an ssh ControlMaster to make that cheap)
or, with multiplexing, run a single ``ssh <host> m3dash pipe --mux`` and
carry every browser connection over that one channel. Multiplexing
needs neither a ControlMaster nor repeated authentication, and avoids
per-connection ssh channel setup latency.

Wire format, over the single bidirectional byte stream:

    1 byte   frame type   (OPEN=1, DATA=2, CLOSE=3)
    4 bytes  stream id     (uint32, big-endian)
    4 bytes  length        (uint32, big-endian; payload length)
    N bytes  payload       (DATA only)

The server writes a one-line handshake (:data:`HANDSHAKE`) before any
frame, so the client can skip login banners that a remote shell startup
might print to stdout.
"""

import os
import struct
import threading

OPEN, DATA, CLOSE = 1, 2, 3
HANDSHAKE = b"M3DASHMUX1\n"
_HEADER = struct.Struct(">BII")
_CHUNK = 65536


def _read_exact(fd: int, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = os.read(fd, n - len(buf))
        if not chunk:
            raise EOFError
        buf += chunk
    return bytes(buf)


class FrameWriter:
    """Serialises frame writes to one fd across threads."""

    def __init__(self, fd: int) -> None:
        self._fd = fd
        self._lock = threading.Lock()

    def send(self, ftype: int, stream_id: int, payload: bytes = b"") -> None:
        header = _HEADER.pack(ftype, stream_id, len(payload))
        with self._lock:
            os.write(self._fd, header)
            if payload:
                os.write(self._fd, payload)


def _read_frame(fd: int) -> tuple[int, int, bytes]:
    ftype, stream_id, length = _HEADER.unpack(_read_exact(fd, _HEADER.size))
    payload = _read_exact(fd, length) if length else b""
    return ftype, stream_id, payload


def serve(in_fd: int, out_fd: int, connect_backend) -> None:
    """Server side: demultiplex frames, one backend connection per stream.

    Args:
        in_fd: fd to read frames from (stdin).
        out_fd: fd to write frames to (stdout).
        connect_backend: callable returning a connected socket.socket for
            a new stream, or raising on failure.
    """
    writer = FrameWriter(out_fd)
    os.write(out_fd, HANDSHAKE)
    backends: dict[int, "socket.socket"] = {}  # noqa: F821
    lock = threading.Lock()

    def pump(stream_id: int, sock) -> None:
        try:
            while True:
                chunk = sock.recv(_CHUNK)
                if not chunk:
                    break
                writer.send(DATA, stream_id, chunk)
        except OSError:
            pass
        finally:
            writer.send(CLOSE, stream_id)
            with lock:
                backends.pop(stream_id, None)
            try:
                sock.close()
            except OSError:
                pass

    try:
        while True:
            ftype, stream_id, payload = _read_frame(in_fd)
            if ftype == OPEN:
                try:
                    sock = connect_backend()
                except OSError:
                    writer.send(CLOSE, stream_id)
                    continue
                with lock:
                    backends[stream_id] = sock
                threading.Thread(
                    target=pump, args=(stream_id, sock), daemon=True
                ).start()
            elif ftype == DATA:
                with lock:
                    sock = backends.get(stream_id)
                if sock is not None:
                    try:
                        sock.sendall(payload)
                    except OSError:
                        pass
            elif ftype == CLOSE:
                with lock:
                    sock = backends.pop(stream_id, None)
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
    except EOFError:
        pass


class MuxClient:
    """Client side: map local sockets onto multiplexed streams."""

    def __init__(self, in_fd: int, out_fd: int) -> None:
        self._writer = FrameWriter(out_fd)
        self._in_fd = in_fd
        self._streams: dict[int, "socket.socket"] = {}  # noqa: F821
        self._lock = threading.Lock()
        self._next_id = 0
        # Skip the handshake line (and any preceding banner noise).
        self._await_handshake()
        threading.Thread(target=self._demux, daemon=True).start()

    def _await_handshake(self) -> None:
        window = bytearray()
        while True:
            byte = os.read(self._in_fd, 1)
            if not byte:
                raise EOFError("remote closed before handshake")
            window += byte
            if window.endswith(HANDSHAKE):
                return
            if len(window) > 4096:
                del window[:-len(HANDSHAKE)]

    def add(self, conn) -> None:
        """Register a new local connection as a fresh stream."""
        with self._lock:
            stream_id = self._next_id
            self._next_id += 1
            self._streams[stream_id] = conn
        self._writer.send(OPEN, stream_id)
        threading.Thread(
            target=self._pump_local, args=(stream_id, conn), daemon=True
        ).start()

    def _pump_local(self, stream_id: int, conn) -> None:
        try:
            while True:
                chunk = conn.recv(_CHUNK)
                if not chunk:
                    break
                self._writer.send(DATA, stream_id, chunk)
        except OSError:
            pass
        finally:
            self._writer.send(CLOSE, stream_id)
            with self._lock:
                self._streams.pop(stream_id, None)

    def _demux(self) -> None:
        try:
            while True:
                ftype, stream_id, payload = _read_frame(self._in_fd)
                with self._lock:
                    conn = self._streams.get(stream_id)
                if ftype == DATA and conn is not None:
                    try:
                        conn.sendall(payload)
                    except OSError:
                        pass
                elif ftype == CLOSE and conn is not None:
                    with self._lock:
                        self._streams.pop(stream_id, None)
                    try:
                        conn.close()
                    except OSError:
                        pass
        except EOFError:
            pass
