"""HTTP-прокси на стандартной библиотеке: Sonarr -> animename -> Prowlarr."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from . import __version__
from .config import Settings
from .render import Converter
from .torznab import SEARCH_TYPES, query_type, rewrite_feed, rewrite_query

log = logging.getLogger("animename")

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}
SKIP_REQUEST_HEADERS = HOP_BY_HOP | {"host", "accept-encoding", "content-length"}
SKIP_RESPONSE_HEADERS = HOP_BY_HOP | {"content-length", "content-encoding"}


@dataclass
class Response:
    status: int
    headers: list[tuple[str, str]]
    body: bytes


class ProxyApp:
    """Логика проксирования без привязки к серверу: удобно тестировать."""

    def __init__(self, settings: Settings, converter: Converter) -> None:
        self.settings = settings
        self.converter = converter
        self.link_rewrite = (
            (settings.upstream_url, settings.public_url) if settings.public_url else None
        )

    def handle_get(self, raw_path: str, headers: dict[str, str]) -> Response:
        parts = urlsplit(raw_path)
        if parts.path in ("/", "/health", "/healthz"):
            body = json.dumps(
                {"status": "ok", "service": "animename", "version": __version__,
                 "upstream": self.settings.upstream_url}
            ).encode()
            return Response(200, [("Content-Type", "application/json")], body)

        is_api = parts.path.endswith("/api")
        query = parts.query
        t = query_type(query) if is_api else ""
        if is_api:
            query = rewrite_query(query, forward_season=self.settings.forward_season)
            if query != parts.query:
                log.debug("query: %s -> %s", parts.query, query)

        url = self.settings.upstream_url + parts.path + (f"?{query}" if query else "")
        fwd_headers = {k: v for k, v in headers.items() if k.lower() not in SKIP_REQUEST_HEADERS}
        fwd_headers.setdefault("User-Agent", f"animename/{__version__}")

        try:
            with urlopen(Request(url, headers=fwd_headers), timeout=self.settings.upstream_timeout) as resp:
                status, resp_headers, body = resp.status, resp.headers.items(), resp.read()
        except HTTPError as exc:
            status, resp_headers, body = exc.code, exc.headers.items(), exc.read()
        except (URLError, TimeoutError, OSError) as exc:
            log.error("upstream %s недоступен: %s", url, exc)
            return Response(502, [("Content-Type", "text/plain; charset=utf-8")],
                            f"animename: upstream unavailable: {exc}".encode())

        if status == 200 and t in SEARCH_TYPES:
            body = rewrite_feed(body, self.converter.convert,
                                link_rewrite=self.link_rewrite, on_result=self._log_result)

        out_headers = [(k, v) for k, v in resp_headers if k.lower() not in SKIP_RESPONSE_HEADERS]
        return Response(status, out_headers, body)

    @staticmethod
    def _log_result(raw: str, new: str | None) -> None:
        if new and new != raw:
            log.info("rewrite: %s  ->  %s", raw, new)
        else:
            log.debug("pass-through: %s", raw)


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = f"animename/{__version__}"

    def __init__(self, *args, app: ProxyApp, **kwargs) -> None:
        self.app = app
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:  # noqa: N802 (имя задаёт BaseHTTPRequestHandler)
        response = self.app.handle_get(self.path, dict(self.headers.items()))
        self.send_response(response.status)
        for key, value in response.headers:
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(response.body)))
        self.end_headers()
        self.wfile.write(response.body)

    def do_HEAD(self) -> None:  # noqa: N802
        response = self.app.handle_get(self.path, dict(self.headers.items()))
        self.send_response(response.status)
        for key, value in response.headers:
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(response.body)))
        self.end_headers()

    def log_message(self, fmt: str, *args) -> None:
        log.debug("%s %s", self.address_string(), fmt % args)


def make_server(settings: Settings, converter: Converter | None = None) -> ThreadingHTTPServer:
    app = ProxyApp(settings, converter or settings.converter())
    server = ThreadingHTTPServer(
        (settings.listen_host, settings.listen_port), partial(ProxyHandler, app=app)
    )
    server.daemon_threads = True
    return server


def serve(settings: Settings) -> None:
    server = make_server(settings)
    host, port = server.server_address[:2]
    log.info("animename %s: слушаю http://%s:%s, upstream %s", __version__, host, port, settings.upstream_url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
