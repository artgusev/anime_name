import threading
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlsplit
from urllib.request import Request, urlopen

import pytest

from animename.config import Settings
from animename.render import Converter
from animename.server import make_server

CAPS = b'<?xml version="1.0"?><caps><server title="Prowlarr"/></caps>'
FEED = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed"><channel><title>RuTracker.org</title>
<item><title>Атака титанов / Shingeki no Kyojin [TV-1] [1-25 из 25] [2013, BDRip] [1080p]</title>
<link>http://UPSTREAM/1/download?apikey=KEY&amp;link=abc</link>
<enclosure url="http://UPSTREAM/1/download?apikey=KEY&amp;link=abc" length="1" type="application/x-bittorrent" />
</item></channel></rss>"""
TORRENT = b"d8:announce3:abce"


class FakeProwlarr(BaseHTTPRequestHandler):
    requests: list[tuple[str, dict, dict]] = []

    def do_GET(self):
        parts = urlsplit(self.path)
        params = dict(parse_qsl(parts.query, keep_blank_values=True))
        FakeProwlarr.requests.append((parts.path, params, dict(self.headers.items())))
        if parts.path == "/1/api" and params.get("t") == "caps":
            body, ctype = CAPS, "application/xml; charset=utf-8"
        elif parts.path == "/1/api":
            if params.get("apikey") != "KEY":
                self.send_error(401, "Unauthorized")
                return
            host = self.headers["Host"]
            body = FEED.replace("UPSTREAM", host).encode()
            ctype = "application/rss+xml; charset=utf-8"
        elif parts.path == "/1/download":
            body, ctype = TORRENT, "application/x-bittorrent"
        else:
            self.send_error(404, "Not Found")
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Upstream", "prowlarr")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _run(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


@pytest.fixture
def upstream():
    FakeProwlarr.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeProwlarr)
    _run(server)
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def make_proxy(upstream, **overrides):
    settings = Settings(upstream_url=upstream, listen_host="127.0.0.1", listen_port=0, **overrides)
    server = make_server(settings, Converter())
    _run(server)
    return server, f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture
def proxy(upstream):
    server, url = make_proxy(upstream)
    yield url
    server.shutdown()
    server.server_close()


def get(url, headers=None):
    with urlopen(Request(url, headers=headers or {}), timeout=5) as resp:
        return resp.status, dict(resp.headers.items()), resp.read()


def test_health(proxy):
    status, headers, body = get(proxy + "/health")
    assert status == 200
    assert headers["Content-Type"] == "application/json"
    assert b'"status": "ok"' in body


def test_caps_pass_through(proxy):
    status, headers, body = get(proxy + "/1/api?t=caps&apikey=KEY")
    assert status == 200
    assert body == CAPS
    assert headers["X-Upstream"] == "prowlarr"


def test_search_rewrites_titles_and_query(proxy, upstream):
    status, headers, body = get(
        proxy + "/1/api?t=search&q=Shingeki+no+Kyojin+05&cat=5070&apikey=KEY&limit=100",
        headers={"Accept-Encoding": "gzip", "User-Agent": "Sonarr/4.0"},
    )
    assert status == 200
    assert "rss+xml" in headers["Content-Type"]
    assert int(headers["Content-Length"]) == len(body)
    text = body.decode()
    assert "<title>Shingeki no Kyojin S01 [BDRip 1080p]</title>" in text
    # ссылки на скачивание по умолчанию ведут прямо в Prowlarr
    assert f"<link>{upstream}/1/download" in text

    path, params, req_headers = FakeProwlarr.requests[-1]
    assert path == "/1/api"
    assert params == {"t": "search", "q": "Shingeki no Kyojin", "cat": "5070", "apikey": "KEY", "limit": "100"}
    # gzip от Sonarr не пробрасываем: тело должно прийти несжатым, чтобы его переписать
    assert req_headers.get("Accept-Encoding", "identity") == "identity"
    assert req_headers["User-Agent"] == "Sonarr/4.0"


def test_tvsearch_drops_season_and_ep(proxy):
    get(proxy + "/1/api?t=tvsearch&q=Shingeki+no+Kyojin&season=1&ep=5&apikey=KEY")
    _, params, _ = FakeProwlarr.requests[-1]
    assert params == {"t": "tvsearch", "q": "Shingeki no Kyojin", "apikey": "KEY"}


def test_upstream_error_status_passes_through(proxy):
    with pytest.raises(HTTPError) as exc:
        get(proxy + "/1/api?t=search&q=x&apikey=WRONG")
    assert exc.value.code == 401
    with pytest.raises(HTTPError) as exc:
        get(proxy + "/nope")
    assert exc.value.code == 404


def test_download_pass_through(proxy):
    status, headers, body = get(proxy + "/1/download?apikey=KEY&link=abc")
    assert status == 200
    assert body == TORRENT
    assert headers["Content-Type"] == "application/x-bittorrent"


def test_public_url_rewrites_links(upstream):
    server, url = make_proxy(upstream, public_url="http://animename:8080")
    try:
        _, _, body = get(url + "/1/api?t=search&q=x&apikey=KEY")
    finally:
        server.shutdown()
        server.server_close()
    text = body.decode()
    assert "<link>http://animename:8080/1/download" in text
    assert 'url="http://animename:8080/1/download' in text
    assert upstream not in text


def test_upstream_down_gives_502():
    server, url = make_proxy("http://127.0.0.1:9")  # discard-порт, никто не слушает
    try:
        with pytest.raises(HTTPError) as exc:
            get(url + "/1/api?t=caps")
        assert exc.value.code == 502
    finally:
        server.shutdown()
        server.server_close()
