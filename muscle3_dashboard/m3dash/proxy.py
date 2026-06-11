"""Reverse-proxy harvested actor UIs under per-target subdomains.

A harvested URL points at ``http://<node>:<port>`` on some compute
node, which the browser cannot reach directly. m3dash exposes each
target under its own subdomain of the address the browser already uses,
e.g. ``http://<token>.localhost:4333``. Because browsers resolve any
``*.localhost`` name to loopback (RFC 6761), this needs no DNS and no
extra SSH forward -- it rides the same socket/`connect` tunnel as the
dashboard.

A subdomain is used (rather than a path prefix) because Bokeh/Panel
apps emit absolute ``/static`` and ``/ws`` URLs that a path prefix would
break; a subdomain keeps the path space intact.

The token is a stateless, reversible base32 encoding of ``host:port``,
so no shared registry is needed between the page that builds links and
the handler that serves them.

Origin rewriting: the target's Bokeh server checks the WebSocket
``Origin`` against its own allowlist, which defaults to
``localhost:<target-port>``. The proxy therefore rewrites ``Origin``
(and ``Host``) to that, so the upstream check passes.
"""

import base64
import logging

import tornado.httpclient
import tornado.web
import tornado.websocket

logger = logging.getLogger(__name__)

#: Hop-by-hop headers that must not be forwarded by a proxy.
_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "content-encoding",
}


def encode_target(host: str, port: int) -> str:
    """Reversibly encode host:port into a single DNS label."""
    raw = f"{host}:{port}".encode()
    return "t" + base64.b32encode(raw).decode().rstrip("=").lower()


def decode_target(token: str) -> tuple[str, int]:
    """Inverse of :func:`encode_target`. Raises ValueError if malformed."""
    if not token.startswith("t"):
        raise ValueError("bad token prefix")
    b32 = token[1:].upper()
    b32 += "=" * (-len(b32) % 8)
    raw = base64.b32decode(b32).decode()
    host, _, port = raw.rpartition(":")
    if not host or not port.isdigit():
        raise ValueError("bad target")
    return host, int(port)


def subdomain_host(host: str, port: int, base_host: str) -> str:
    """The proxy host (e.g. 't....localhost:4333') for a target."""
    return f"{encode_target(host, port)}.{base_host}"


def _token_from_host(http_host: str) -> str:
    """First label of the Host header (drops any :port)."""
    return http_host.split(":", 1)[0].split(".", 1)[0]


def _upstream_origin(host: str, port: int) -> str:
    # Bokeh's default websocket-origin allowlist is localhost:<port>.
    return f"http://localhost:{port}"


class _ProxyBase:
    def target(self) -> tuple[str, int]:
        return decode_target(_token_from_host(self.request.host))


class HTTPProxyHandler(_ProxyBase, tornado.web.RequestHandler):
    """Relay plain HTTP requests to the decoded target."""

    SUPPORTED_METHODS = ("GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS")

    async def _proxy(self, *args) -> None:
        try:
            host, port = self.target()
        except ValueError:
            self.set_status(404)
            self.finish("m3dash proxy: unknown target")
            return
        url = f"http://{host}:{port}{self.request.uri}"
        headers = {
            k: v
            for k, v in self.request.headers.items()
            if k.lower() not in _HOP_BY_HOP
        }
        headers["Host"] = f"{host}:{port}"
        if "Origin" in headers:
            headers["Origin"] = _upstream_origin(host, port)
        body = self.request.body or None
        client = tornado.httpclient.AsyncHTTPClient()
        try:
            resp = await client.fetch(
                tornado.httpclient.HTTPRequest(
                    url,
                    method=self.request.method,
                    headers=headers,
                    body=body,
                    follow_redirects=False,
                    request_timeout=300,
                    allow_nonstandard_methods=True,
                )
            )
        except tornado.httpclient.HTTPClientError as exc:
            if exc.response is not None:
                resp = exc.response
            else:
                self.set_status(502)
                self.finish(f"m3dash proxy: upstream error: {exc}")
                return
        except OSError as exc:
            self.set_status(502)
            self.finish(f"m3dash proxy: cannot reach {host}:{port}: {exc}")
            return
        self.set_status(resp.code)
        for k, v in resp.headers.get_all():
            if k.lower() not in _HOP_BY_HOP:
                self.add_header(k, v)
        if resp.body:
            self.write(resp.body)
        self.finish()

    # All methods funnel through _proxy.
    get = post = put = delete = head = options = _proxy


class WebSocketProxyHandler(_ProxyBase, tornado.websocket.WebSocketHandler):
    """Relay a WebSocket to the decoded target, both directions."""

    def check_origin(self, origin: str) -> bool:
        # The browser-facing origin is our own subdomain; we enforce
        # nothing here (the unix socket / tunnel already gates access)
        # and rewrite Origin for the upstream check.
        return True

    def select_subprotocol(self, subprotocols):
        # Bokeh negotiates "bokeh" and carries a token as a second
        # value; remember the originals to replay them upstream, and
        # echo "bokeh" back to the client as the upstream will.
        self._subprotocols = subprotocols
        if not subprotocols:
            return None
        return "bokeh" if "bokeh" in subprotocols else subprotocols[0]

    async def open(self, *args):
        self._upstream = None
        self._closed = False
        try:
            host, port = self.target()
        except ValueError:
            self.close(code=4040, reason="unknown target")
            return
        ws_url = f"ws://{host}:{port}{self.request.uri}"
        headers = {"Origin": _upstream_origin(host, port)}
        proto = getattr(self, "_subprotocols", None)
        if proto:
            headers["Sec-WebSocket-Protocol"] = ", ".join(proto)
        try:
            self._upstream = await tornado.websocket.websocket_connect(
                tornado.httpclient.HTTPRequest(ws_url, headers=headers),
                on_message_callback=self._on_upstream,
                subprotocols=list(proto) if proto else None,
            )
        except Exception as exc:  # noqa: BLE001 - report any upstream failure
            logger.warning("proxy ws connect failed %s:%s: %s", host, port, exc)
            self.close(code=4502, reason="upstream connect failed")

    def _on_upstream(self, message) -> None:
        if message is None:  # upstream closed
            if not self._closed:
                self.close()
            return
        self.write_message(message, binary=isinstance(message, bytes))

    async def on_message(self, message) -> None:
        if self._upstream is not None:
            await self._upstream.write_message(
                message, binary=isinstance(message, bytes)
            )

    def on_close(self) -> None:
        self._closed = True
        if self._upstream is not None:
            self._upstream.close()


#: Host pattern for subdomain proxying over the loopback access path.
PROXY_HOST_PATTERN = r"^t[a-z2-7]+\.localhost(:\d+)?$"


def proxy_handlers():
    """tornado handler list for the proxy host (ws first, then http)."""
    return [
        (r"/ws", WebSocketProxyHandler),
        (r"/.*", HTTPProxyHandler),
    ]
