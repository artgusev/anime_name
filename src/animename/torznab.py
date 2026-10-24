"""Переписывание Torznab-запросов Sonarr и Torznab-ответов Prowlarr.

Запросы: Sonarr добавляет к названию номер серии или ``S01E05``; RuTracker по таким
строкам ничего не находит, поэтому хвост отрезается, а ``season``/``ep`` по умолчанию
не передаются дальше.

Ответы: меняется только текст ``<title>`` внутри каждого ``<item>``; остальной XML
отдаётся байт в байт, как его прислал Prowlarr.
"""

from __future__ import annotations

import html
import re
from typing import Callable
from urllib.parse import parse_qsl, urlencode
from xml.sax.saxutils import escape

SEARCH_TYPES = frozenset({"search", "tvsearch"})

# "S01E05", "S01E05-E06", "S02", "1x05", "Season 2", "2nd Season", "Part 2",
# в том числе в скобках: "(Season 2)", "[S02]". Хвост может состоять из нескольких таких токенов.
_EP_TOKEN = (
    r"(?:S\d{1,2}(?:E\d{1,4}(?:-?E?\d{1,4})?)?|E\d{1,4}|\d{1,2}x\d{2,3}"
    r"|Season\s*\d{1,2}|\d{1,2}(?:st|nd|rd|th)\s+Season|(?:Part|Cour)\s*\d{1,2})"
)
TRAILING_EP_RE = re.compile(
    rf"(?:[\s.+\-–:]+(?:{_EP_TOKEN}|[(\[]\s*{_EP_TOKEN}\s*[)\]]))+\s*$",
    re.IGNORECASE,
)
# Для аниме Sonarr шлёт "Title 05": абсолютный номер серии, минимум две цифры.
TRAILING_NUM_RE = re.compile(r"\s+\d{2,4}\s*$")

EMPTY_FEED_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" '
    'xmlns:torznab="http://torznab.com/schemas/2015/feed">'
    "<channel><title>animename</title><description>{reason}</description>"
    '<torznab:response offset="0" total="0"/></channel></rss>\n'
)

ITEM_RE = re.compile(r"<item\b[^>]*>.*?</item>", re.S)
TITLE_RE = re.compile(r"(<title\b[^>]*>)(.*?)(</title>)", re.S)
CDATA_RE = re.compile(r"^\s*<!\[CDATA\[(.*)\]\]>\s*$", re.S)
LINK_RE = re.compile(r"(<link>)(.*?)(</link>)", re.S)
ENCLOSURE_URL_RE = re.compile(r'(<enclosure\b[^>]*\burl=")([^"]*)(")')

Convert = Callable[[str], "str | None"]
OnResult = Callable[[str, "str | None"], None]


def query_type(query: str) -> str:
    for key, value in parse_qsl(query, keep_blank_values=True):
        if key == "t":
            return value.lower()
    return ""


def query_param(query: str, name: str) -> str | None:
    for key, value in parse_qsl(query, keep_blank_values=True):
        if key == name:
            return value
    return None


def clean_query(q: str, *, search_type: str) -> str:
    q = " ".join(q.split())
    # Номер серии Sonarr дописывает последним, поэтому сначала он, потом S02/Season 2.
    if search_type == "search":
        q = TRAILING_NUM_RE.sub("", q)
    q = TRAILING_EP_RE.sub("", q)
    return q.strip()


def empty_feed(reason: str) -> bytes:
    """Пустой Torznab-ответ: Sonarr видит канал без элементов и считает, что результатов нет."""
    return EMPTY_FEED_TEMPLATE.format(reason=escape(reason)).encode("utf-8")


def rewrite_query(query: str, *, forward_season: bool = False) -> str:
    params = parse_qsl(query, keep_blank_values=True)
    t = next((v.lower() for k, v in params if k == "t"), "")
    if t not in SEARCH_TYPES:
        return query
    out = []
    for key, value in params:
        if key == "q":
            value = clean_query(value, search_type=t)
        elif key in ("season", "ep") and not forward_season:
            continue
        out.append((key, value))
    return urlencode(out)


def rewrite_feed(
    body: bytes,
    convert: Convert,
    *,
    link_rewrite: tuple[str, str] | None = None,
    on_result: OnResult | None = None,
) -> bytes:
    """Переписать заголовки ``<item><title>`` в RSS/Torznab-ответе."""
    text = body.decode("utf-8", errors="surrogateescape")

    def fix_title(m: re.Match[str]) -> str:
        inner = m.group(2)
        cdata = CDATA_RE.match(inner)
        raw = cdata.group(1) if cdata else html.unescape(inner)
        new = convert(raw)
        if on_result:
            on_result(raw, new)
        if not new or new == raw:
            return m.group(0)
        return m.group(1) + escape(new) + m.group(3)

    def fix_links(item: str) -> str:
        if not link_rewrite:
            return item
        old, new = link_rewrite
        item = LINK_RE.sub(lambda m: m.group(1) + m.group(2).replace(old, new) + m.group(3), item)
        return ENCLOSURE_URL_RE.sub(lambda m: m.group(1) + m.group(2).replace(old, new) + m.group(3), item)

    def fix_item(m: re.Match[str]) -> str:
        return fix_links(TITLE_RE.sub(fix_title, m.group(0), count=1))

    return ITEM_RE.sub(fix_item, text).encode("utf-8", errors="surrogateescape")
