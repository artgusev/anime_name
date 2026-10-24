"""HTTP-прокси на стандартной библиотеке: Sonarr -> animename -> Prowlarr."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlsplit
from urllib.request import Request, urlopen

from . import __version__
from .cache import TTLCache
from .config import Settings
from .render import Converter
from .torznab import SEARCH_TYPES, empty_feed, query_param, query_type, rewrite_feed, rewrite_query

log = logging.getLogger("animename")

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}
SKIP_REQUEST_HEADERS = HOP_BY_HOP | {"host", "accept-encoding", "content-length"}
SKIP_RESPONSE_HEADERS = HOP_BY_HOP | {"content-length", "content-encoding"}
CACHE_HEADER = "X-Animename-Cache"
SKIP_HEADER = "X-Animename-Skip"
RSS_CONTENT_TYPE = "application/rss+xml; charset=utf-8"


@dataclass(frozen=True)
class Response:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes

    def with_header(self, name: str, value: str) -> "Response":
        return replace(self, headers=self.headers + ((name, value),))


class ProxyApp:
    """Логика проксирования без привязки к серверу: удобно тестировать."""

    def __init__(self, settings: Settings, converter: Converter) -> None:
        self.settings = settings
        self.converter = converter
        self.link_rewrite = (
            (settings.upstream_url, settings.public_url) if settings.public_url else None
        )
        self.cache: TTLCache[tuple, Response] = TTLCache(settings.cache_ttl, settings.cache_size)
        self.query_filter = settings.query_filter()

    def handle_get(self, raw_path: str, headers: dict[str, str]) -> Response:
        parts = urlsplit(raw_path)
        if parts.path in ("/", "/health", "/healthz"):
            body = json.dumps(
                {"status": "ok", "service": "animename", "version": __version__,
                 "upstream": self.settings.upstream_url, "cache_entries": len(self.cache)}
            ).encode()
            return Response(200, (("Content-Type", "application/json"),), body)

        is_api = parts.path.endswith("/api")
        query = parts.query
        search_type = query_type(query) if is_api else ""
        is_search = is_api and search_type in SEARCH_TYPES
        if is_api:
            query = rewrite_query(query, forward_season=self.settings.forward_season)
            if query != parts.query:
                log.debug("query: %s -> %s", parts.query, query)

        q = query_param(query, "q") if is_search else None
        reason = self.query_filter.reason(q) if q else None
        if reason:
            log.info("skip: %r (%s)", q, reason)
            return Response(
                200,
                (("Content-Type", RSS_CONTENT_TYPE), (CACHE_HEADER, "SKIP"), (SKIP_HEADER, reason)),
                empty_feed(f"no results: {reason}"),
            )

        if is_search and q and self.cache.enabled:
            # Ключ: индексер (путь) и очищенные параметры. RSS без q не кэшируем, чтобы не задерживать новинки.
            key = (parts.path, tuple(sorted(parse_qsl(query, keep_blank_values=True))))
            response, hit = self.cache.get_or_fetch(
                key,
                lambda: self._fetch(parts.path, query, headers, is_search),
                should_cache=lambda r: r.status == 200,
            )
            if hit:
                log.debug("cache hit: %s?%s", parts.path, query)
            return response.with_header(CACHE_HEADER, "HIT" if hit else "MISS")

        return self._fetch(parts.path, query, headers, is_search)

    def _fetch(self, path: str, query: str, headers: dict[str, str], is_search: bool) -> Response:
        url = self.settings.upstream_url + path + (f"?{query}" if query else "")
        fwd_headers = {k: v for k, v in headers.items() if k.lower() not in SKIP_REQUEST_HEADERS}
        fwd_headers.setdefault("User-Agent", f"animename/{__version__}")

        try:
            with urlopen(Request(url, headers=fwd_headers), timeout=self.settings.upstream_timeout) as resp:
                status, resp_headers, body = resp.status, resp.headers.items(), resp.read()
        except HTTPError as exc:
            status, resp_headers, body = exc.code, exc.headers.items(), exc.read()
        except (URLError, TimeoutError, OSError) as exc:
            log.error("upstream %s недоступен: %s", url, exc)
            return Response(502, (("Content-Type", "text/plain; charset=utf-8"),),
                            f"animename: upstream unavailable: {exc}".encode())

        if status == 200 and is_search:
            body = rewrite_feed(body, self.converter.convert,
                                link_rewrite=self.link_rewrite, on_result=self._log_result)

        out_headers = tuple((k, v) for k, v in resp_headers if k.lower() not in SKIP_RESPONSE_HEADERS)
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

    def _respond(self, send_body: bool) -> None:
        response = self.app.handle_get(self.path, dict(self.headers.items()))
        self.send_response(response.status)
        for key, value in response.headers:
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(response.body)))
        self.end_headers()
        if send_body:
            self.wfile.write(response.body)

    def do_GET(self) -> None:  # noqa: N802 (имя задаёт BaseHTTPRequestHandler)
        self._respond(send_body=True)

    def do_HEAD(self) -> None:  # noqa: N802
        self._respond(send_body=False)

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
    if settings.cache_ttl > 0:
        log.info("кэш ответов: %.0f с, до %d записей", settings.cache_ttl, settings.cache_size)
    log.info("языки запросов: %s", settings.query_languages or "any")
    if settings.query_skip:
        log.info("QUERY_SKIP: %s", settings.query_skip)
    if settings.query_allow:
        log.info("QUERY_ALLOW: %s", settings.query_allow)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
