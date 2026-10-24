from urllib.parse import parse_qsl

import pytest

from animename.render import Converter
from animename.torznab import clean_query, empty_feed, query_param, rewrite_feed, rewrite_query

FEED = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <atom:link href="http://prowlarr:9696/1/" rel="self" type="application/rss+xml" />
    <title>RuTracker.org</title>
    <item>
      <title>Стальной алхимик: Братство / Fullmetal Alchemist: Brotherhood [TV] [1-64 из 64] [RUS(int), JAP+Sub] [2009, приключения &amp; драма, BDRip] [1080p]</title>
      <guid>https://rutracker.org/forum/viewtopic.php?t=111</guid>
      <link>http://prowlarr:9696/1/download?apikey=KEY&amp;link=abc&amp;file=x</link>
      <comments>https://rutracker.org/forum/viewtopic.php?t=111</comments>
      <enclosure url="http://prowlarr:9696/1/download?apikey=KEY&amp;link=abc&amp;file=x" length="1" type="application/x-bittorrent" />
      <torznab:attr name="category" value="5070" />
      <torznab:attr name="seeders" value="10" />
    </item>
    <item>
      <title><![CDATA[Дандадан / Dandadan [TV] [01 из 12] [2024, WEB-DL] [1080p]]]></title>
      <guid>https://rutracker.org/forum/viewtopic.php?t=222</guid>
      <link>http://prowlarr:9696/1/download?apikey=KEY&amp;link=def&amp;file=y</link>
      <enclosure url="http://prowlarr:9696/1/download?apikey=KEY&amp;link=def&amp;file=y" length="1" type="application/x-bittorrent" />
    </item>
    <item>
      <title>Ubuntu 24.04 LTS [amd64]</title>
      <guid>https://rutracker.org/forum/viewtopic.php?t=333</guid>
      <link>http://prowlarr:9696/1/download?apikey=KEY&amp;link=ghi&amp;file=z</link>
    </item>
  </channel>
</rss>
"""


@pytest.mark.parametrize(
    "query, expected_q, expect_season",
    [
        ("t=search&q=Shingeki+no+Kyojin+05&cat=5070&apikey=abc", "Shingeki no Kyojin", False),
        ("t=search&q=Mob+Psycho+100+07", "Mob Psycho 100", False),
        ("t=search&q=86+05", "86", False),
        ("t=search&q=Title+S01E05", "Title", False),
        ("t=search&q=Title+S02", "Title", False),
        ("t=search&q=Title+Season+2", "Title", False),
        ("t=tvsearch&q=Mob+Psycho+100&season=2&ep=3", "Mob Psycho 100", False),
        ("t=tvsearch&q=Shingeki%20no%20Kyojin%20S01E05-E06", "Shingeki no Kyojin", False),
        # скобки
        ("t=tvsearch&q=Shingeki+no+Kyojin+(Season+2)", "Shingeki no Kyojin", False),
        ("t=tvsearch&q=Attack+on+Titan+[S02]", "Attack on Titan", False),
        ("t=search&q=Shingeki+no+Kyojin+(Season+2)+05", "Shingeki no Kyojin", False),
        # порядковые сезоны, части, разделители
        ("t=search&q=Re%3AZero+2nd+Season+05", "Re:Zero", False),
        ("t=search&q=Attack+on+Titan+Season+3+Part+2+05", "Attack on Titan", False),
        ("t=tvsearch&q=Title+-+Season+2", "Title", False),
        ("t=tvsearch&q=Title.S01E05", "Title", False),
        # год в скобках не сезон
        ("t=search&q=Hunter+x+Hunter+(2011)+05", "Hunter x Hunter (2011)", False),
        # год, который Sonarr дописывает к алиасу, отрезается
        ("t=search&q=Ataque+a+los+Titanes+2013+37", "Ataque a los Titanes", False),
        ("t=search&q=Attack+on+Titan+2013+37", "Attack on Titan", False),
        ("t=tvsearch&q=Attack+on+Titan+2013", "Attack on Titan", False),
        ("t=tvsearch&q=Attack+on+Titan+2013+S02", "Attack on Titan", False),
        ("t=search&q=Mob+Psycho+100+2016+07", "Mob Psycho 100", False),
        # одно слово перед годом: год остаётся
        ("t=search&q=Space+1999+05", "Space 1999", False),
        ("t=tvsearch&q=Yellowstone+2018", "Yellowstone 2018", False),
        ("t=search&q=1983+05", "1983", False),
    ],
)
def test_rewrite_query_cleans_title(query, expected_q, expect_season):
    params = dict(parse_qsl(rewrite_query(query), keep_blank_values=True))
    assert params["q"] == expected_q
    assert ("season" in params) is expect_season
    assert "ep" not in params


def test_rewrite_query_keeps_other_params():
    out = dict(parse_qsl(rewrite_query("t=tvsearch&q=Title+05&cat=5070&limit=100&offset=0&apikey=k&extended=1")))
    assert out == {"t": "tvsearch", "q": "Title 05", "cat": "5070", "limit": "100", "offset": "0", "apikey": "k", "extended": "1"}


def test_rewrite_query_forward_season():
    out = dict(parse_qsl(rewrite_query("t=tvsearch&q=Title&season=2&ep=3", forward_season=True)))
    assert out["season"] == "2" and out["ep"] == "3"


@pytest.mark.parametrize("query", ["t=caps&apikey=x", "t=movie&q=Foo+05", "apikey=x", ""])
def test_rewrite_query_untouched_for_other_types(query):
    assert rewrite_query(query) == query


def test_rewrite_query_without_q():
    assert dict(parse_qsl(rewrite_query("t=tvsearch&cat=5070&limit=100&offset=0"))) == {
        "t": "tvsearch", "cat": "5070", "limit": "100", "offset": "0"
    }


def test_clean_query_tvsearch_keeps_trailing_number():
    assert clean_query("Mob Psycho 100", search_type="tvsearch") == "Mob Psycho 100"
    assert clean_query("Mob Psycho 100", search_type="search") == "Mob Psycho"


def test_clean_query_collapses_variants():
    variants = [
        "Attack on Titan S2", "Attack on Titan Season 2", "Attack on Titan (Season 2)",
        "Attack on Titan 2013", "Attack on Titan 2013 S02", "Attack on Titan",
    ]
    assert {clean_query(v, search_type="tvsearch") for v in variants} == {"Attack on Titan"}


def test_query_param():
    assert query_param("t=search&q=Foo+Bar&cat=5070", "q") == "Foo Bar"
    assert query_param("t=search&cat=5070", "q") is None


def test_empty_feed_is_valid_torznab():
    import xml.etree.ElementTree as ET

    root = ET.fromstring(empty_feed('skipped <by> "QUERY_SKIP" & co'))
    assert root.tag == "rss"
    channel = root.find("channel")
    assert channel.findall("item") == []
    assert channel.find("description").text == 'skipped <by> "QUERY_SKIP" & co'
    ns = {"torznab": "http://torznab.com/schemas/2015/feed"}
    assert channel.find("torznab:response", ns).get("total") == "0"


def test_rewrite_feed_rewrites_only_titles():
    results = []
    out = rewrite_feed(FEED.encode(), Converter().convert, on_result=lambda raw, new: results.append((raw, new))).decode()
    assert "<title>Fullmetal Alchemist: Brotherhood S01 [BDRip 1080p]</title>" in out
    assert "<title>Dandadan S01E01 [WEB-DL 1080p]</title>" in out
    assert "<title>Ubuntu 24.04 LTS [amd64]</title>" in out
    # заголовок канала не трогаем
    assert "<title>RuTracker.org</title>" in out
    # всё остальное байт в байт
    import re
    strip = lambda s: re.sub(r"<item>.*?</item>", "", s, flags=re.S)  # noqa: E731
    assert strip(out) == strip(FEED)
    for tag in ("<guid>", "<enclosure url=", "<torznab:attr", "&amp;link=abc"):
        assert out.count(tag) == FEED.count(tag)
    assert [new is not None for _, new in results] == [True, True, False]


def test_rewrite_feed_escapes_xml():
    feed = "<rss><channel><item><title>А и Б / Foo &amp; Bar [TV] [12 из 12] [2020, BDRip] [1080p]</title></item></channel></rss>"
    out = rewrite_feed(feed.encode(), Converter().convert).decode()
    assert "<title>Foo &amp; Bar S01 [BDRip 1080p]</title>" in out


def test_rewrite_feed_link_rewrite():
    out = rewrite_feed(
        FEED.encode(), Converter().convert, link_rewrite=("http://prowlarr:9696", "http://animename:8080")
    ).decode()
    assert out.count("http://animename:8080/1/download") == 5
    assert "<link>http://prowlarr:9696" not in out
    # guid и atom:link остаются
    assert 'href="http://prowlarr:9696/1/"' in out
    assert "<guid>https://rutracker.org" in out


def test_rewrite_feed_handles_non_xml_body():
    body = b"\xff\xfe not xml at all"
    assert rewrite_feed(body, Converter().convert) == body
