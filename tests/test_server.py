import threading
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlsplit
from urllib.request import Request, urlopen

import pytest

from animename import __version__
from animename.config import Settings
from animename.render import Converter
from animename.server import make_server, proxy_user_agent

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


def test_health_counters(proxy):
    import json

    get(proxy + "/1/api?t=search&q=Ataque+a+los+Titanes+31&apikey=KEY")   # skip
    get(proxy + "/1/api?t=search&q=Attack+on+Titan+31&apikey=KEY")         # forward
    get(proxy + "/1/api?t=search&q=Attack+on+Titan+32&apikey=KEY")         # cache hit
    get(proxy + "/1/api?t=caps&apikey=KEY")                                # просто запрос
    stats = json.loads(get(proxy + "/health")[2])["stats"]
    assert stats == {"requests": 4, "forwarded": 1, "skipped": 1, "cache_hits": 1}


@pytest.mark.parametrize(
    "ua, expected",
    [
        ("Sonarr/4.0.1.929 (docker)", f"animename/{__version__} (via Sonarr 4.0.1.929 (docker))"),
        ("", f"animename/{__version__} (via unknown)"),
    ],
)
def test_proxy_user_agent(ua, expected):
    headers = {"user-agent": ua} if ua else {}
    assert proxy_user_agent(headers) == expected


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
    # Prowlarr покажет источник "animename": до первого "/" и без второго слэша
    assert req_headers["User-Agent"] == f"animename/{__version__} (via Sonarr 4.0)"
    assert req_headers["User-Agent"].count("/") == 1


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


def api_calls():
    return [params for path, params, _ in FakeProwlarr.requests if path == "/1/api"]


def test_cache_dedups_query_variants(proxy):
    seen = []
    for q in ("Attack+on+Titan+S2", "Attack+on+Titan+(Season+2)", "Attack+on+Titan"):
        status, headers, body = get(proxy + f"/1/api?t=tvsearch&q={q}&cat=5070&apikey=KEY")
        assert status == 200
        assert "<title>Shingeki no Kyojin S01 [BDRip 1080p]</title>" in body.decode()
        seen.append(headers["X-Animename-Cache"])
    assert seen == ["MISS", "HIT", "HIT"]
    assert api_calls() == [{"t": "tvsearch", "q": "Attack on Titan", "cat": "5070", "apikey": "KEY"}]


def test_cache_merges_season_and_episode_searches(proxy):
    # поиск сезона (tvsearch) и серий 1..3 (search) -> один запрос в Prowlarr
    get(proxy + "/1/api?t=tvsearch&q=Attack+on+Titan&season=1&cat=5070&apikey=KEY&limit=100&offset=0")
    seen = []
    for ep in (1, 2, 3):
        _, headers, _ = get(proxy + f"/1/api?t=search&q=Attack+on+Titan+{ep:02d}&cat=5070&apikey=KEY&limit=100&offset=0")
        seen.append(headers["X-Animename-Cache"])
    assert seen == ["HIT", "HIT", "HIT"]
    assert len(api_calls()) == 1
    # другая категория -> другой ключ
    get(proxy + "/1/api?t=search&q=Attack+on+Titan+01&cat=5000&apikey=KEY&limit=100&offset=0")
    assert len(api_calls()) == 2


def test_cache_separates_pages_and_skips_rss(proxy):
    get(proxy + "/1/api?t=tvsearch&q=Foo&offset=0&apikey=KEY")
    get(proxy + "/1/api?t=tvsearch&q=Foo&offset=100&apikey=KEY")
    _, headers, _ = get(proxy + "/1/api?t=tvsearch&cat=5070&apikey=KEY")  # RSS без q
    assert "X-Animename-Cache" not in headers
    get(proxy + "/1/api?t=tvsearch&cat=5070&apikey=KEY")
    assert len(api_calls()) == 4


def test_cache_disabled(upstream):
    server, url = make_proxy(upstream, cache_ttl=0)
    try:
        for _ in range(2):
            _, headers, _ = get(url + "/1/api?t=search&q=Foo&apikey=KEY")
            assert "X-Animename-Cache" not in headers
    finally:
        server.shutdown()
        server.server_close()
    assert len(api_calls()) == 2


def test_errors_are_not_cached(proxy):
    for _ in range(2):
        with pytest.raises(HTTPError) as exc:
            get(proxy + "/1/api?t=search&q=Foo&apikey=WRONG")
        assert exc.value.code == 401
    assert len(api_calls()) == 2


def test_query_skip_returns_empty_feed(upstream):
    import xml.etree.ElementTree as ET

    server, url = make_proxy(upstream, query_skip="Ataque|Attaque|attacco")
    try:
        status, headers, body = get(url + "/1/api?t=search&q=Ataque+de+los+Titanes+05&apikey=KEY")
        assert status == 200
        assert headers["Content-Type"].startswith("application/rss+xml")
        assert headers["X-Animename-Cache"] == "SKIP"
        assert ET.fromstring(body).find("channel").findall("item") == []
        assert api_calls() == []

        # обычный запрос проходит как раньше
        _, _, body = get(url + "/1/api?t=search&q=Attack+on+Titan+05&apikey=KEY")
        assert "Shingeki no Kyojin S01" in body.decode()
        assert len(api_calls()) == 1
        # caps не фильтруется
        _, _, body = get(url + "/1/api?t=caps&apikey=KEY")
        assert body == CAPS
    finally:
        server.shutdown()
        server.server_close()


def test_language_filter_default(proxy):
    import xml.etree.ElementTree as ET

    # испанский алиас с TVDB: пустой ответ, Prowlarr не вызывается
    status, headers, body = get(proxy + "/1/api?t=search&q=Ataque+de+los+Titanes+05&apikey=KEY")
    assert status == 200
    assert headers["X-Animename-Cache"] == "SKIP"
    assert headers["X-Animename-Skip"] == "language=es not in en,ru"
    assert ET.fromstring(body).find("channel").findall("item") == []
    assert api_calls() == []

    # японский иероглифами и украинский тоже
    get(proxy + "/1/api?t=search&q=%E9%80%B2%E6%92%83%E3%81%AE%E5%B7%A8%E4%BA%BA+05&apikey=KEY")
    get(proxy + "/1/api?t=search&q=%D0%90%D1%82%D0%B0%D0%BA%D0%B0+%D1%82%D0%B8%D1%82%D0%B0%D0%BD%D1%96%D0%B2&apikey=KEY")
    assert api_calls() == []

    # английский, ромадзи и русский уходят в Prowlarr
    for q in ("Attack+on+Titan+05", "Shingeki+no+Kyojin+05", "%D0%90%D1%82%D0%B0%D0%BA%D0%B0+%D1%82%D0%B8%D1%82%D0%B0%D0%BD%D0%BE%D0%B2"):
        _, headers, _ = get(proxy + f"/1/api?t=search&q={q}&apikey=KEY")
        assert headers["X-Animename-Cache"] == "MISS"
    assert [p["q"] for p in api_calls()] == ["Attack on Titan", "Shingeki no Kyojin", "Атака титанов"]


def test_language_filter_spanish_alias_with_year(proxy):
    # ровно тот запрос, что Sonarr шлёт для испанского алиаса с TVDB
    _, headers, _ = get(proxy + "/1/api?t=search&q=Ataque+a+los+Titanes+2013+37&cat=5070&apikey=KEY")
    assert headers["X-Animename-Skip"] == "language=es not in en,ru"
    assert api_calls() == []
    # английский вариант с годом уходит без года и без номера серии
    get(proxy + "/1/api?t=search&q=Attack+on+Titan+2013+37&cat=5070&apikey=KEY")
    assert [p["q"] for p in api_calls()] == ["Attack on Titan"]


def test_language_filter_disabled_and_allow(upstream):
    server, url = make_proxy(upstream, query_languages="any")
    try:
        get(url + "/1/api?t=search&q=Ataque+de+los+Titanes&apikey=KEY")
    finally:
        server.shutdown()
        server.server_close()
    assert [p["q"] for p in api_calls()] == ["Ataque de los Titanes"]

    FakeProwlarr.requests.clear()
    server, url = make_proxy(upstream, query_allow="Chevalier")
    try:
        get(url + "/1/api?t=search&q=Le+Chevalier+DEon&apikey=KEY")
        _, headers, _ = get(url + "/1/api?t=search&q=Les+Aventures+de+Tintin&apikey=KEY")
    finally:
        server.shutdown()
        server.server_close()
    assert [p["q"] for p in api_calls()] == ["Le Chevalier DEon"]
    assert headers["X-Animename-Skip"].startswith("language=fr")


def test_invalid_query_skip_fails_fast(upstream):
    with pytest.raises(ValueError, match="QUERY_SKIP"):
        make_proxy(upstream, query_skip="(")


def test_upstream_down_gives_502():
    server, url = make_proxy("http://127.0.0.1:9")  # discard-порт, никто не слушает
    try:
        with pytest.raises(HTTPError) as exc:
            get(url + "/1/api?t=caps")
        assert exc.value.code == 502
    finally:
        server.shutdown()
        server.server_close()
