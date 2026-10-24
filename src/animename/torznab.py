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

# "... S01E05", "... S01E05-E06", "... S02", "... 1x05", "... Season 2"
TRAILING_EP_RE = re.compile(
    r"(?:[\s.+]+(?:S\d{1,2}(?:E\d{1,4}(?:-?E?\d{1,4})?)?|E\d{1,4}|\d{1,2}x\d{2,3}|Season\s*\d{1,2}))+\s*$",
    re.IGNORECASE,
)
# Для аниме Sonarr шлёт "Title 05": абсолютный номер серии, минимум две цифры.
TRAILING_NUM_RE = re.compile(r"\s+\d{2,4}\s*$")

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


def clean_query(q: str, *, search_type: str) -> str:
    q = " ".join(q.split())
    q = TRAILING_EP_RE.sub("", q)
    if search_type == "search":
        q = TRAILING_NUM_RE.sub("", q)
    return q.strip()


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
