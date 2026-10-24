"""Разбор заголовков раздач RuTracker в структуру Release.

Поддерживаются три формы заголовков:

* аниме-разделы как на сайте:
  ``Атака титанов / Shingeki no Kyojin [TV-1] [1-25 из 25] [RUS(int), JAP+Sub] [2013, ..., BDRip] [1080p]``
* обычные сериалы как на сайте:
  ``Твин Пикс / Twin Peaks / Сезон: 1 / Серии: 1-8 из 8 (Дэвид Линч) [1990, США, BDRip 1080p]``
* то, что отдаёт индексер RuTracker в Prowlarr. Его парсер для TV-категорий всегда
  переписывает ``(ТВ-2)`` в ``(S2)``, ``[12 из 12]`` в ``E12 of 12`` и ``Сезон: 1 / Серии: 1-8 из 8``
  в ``S1E1-8 of 8``, а с опцией Strip Russian letters ещё и выкидывает кириллицу: ``[1-25 из 25]``
  становится ``[1-25 25]``, ``[ТВ]`` исчезает совсем, ``(ТВ-4, часть 2)`` превращается в ``(S4, 2)``:
  ``(S2) / Shingeki no Kyojin Season 2 / Attack on Titan 2nd Season [TV] E12 of 12 [2017, BDRip 1080p, 60 FPS] AniLibria RUS``

Всё, что не распознано, возвращается как ``None`` и проксируется без изменений.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_RE = re.compile(r"[A-Za-z]")

# [TV], [TV-1], [ТВ-2], [TV-3 Part 2], [TV-1 + Special], [Movie], [OVA], [ONA], [Special]
TYPE_RE = re.compile(
    r"\[\s*(?P<kind>TV|ТВ|Movie|Фильм|Film|OVA|ОВА|OAD|ONA|Special|Спешл|Спэшл|Music|Clip)"
    r"(?![A-Za-zА-Яа-яЁё])"
    r"(?:\s*[-–]?\s*(?P<num>\d{1,2})(?!\d))?(?P<rest>[^\]]*)\]",
    re.IGNORECASE,
)
# [ТВ-1] после Prowlarr: [S1]
PROWLARR_TYPE_RE = re.compile(r"\[\s*S(?P<num>\d{1,2})\s*\]")
KIND_MAP = {
    "tv": "TV", "тв": "TV",
    "movie": "Movie", "фильм": "Movie", "film": "Movie",
    "ova": "OVA", "ова": "OVA", "oad": "OVA",
    "ona": "ONA",
    "special": "Special", "спешл": "Special", "спэшл": "Special",
    "music": "Music", "clip": "Music",
}

# (ТВ-2), (S2), [S1], (S4, 2) в шапке: номер сезона и, возможно, часть
HEAD_SEASON_RE = re.compile(
    r"[(\[]\s*(?:S|ТВ\s*-?\s*)(?P<n>\d{1,2})(?P<rest>[^)\]]*)[)\]]", re.IGNORECASE
)
# Сезон без серий после Prowlarr: "Сезон: 3" -> "S3" отдельным словом. Не внутри скобок:
# "(S2)" и "[S1]" разбирают HEAD_SEASON_RE и PROWLARR_TYPE_RE.
STANDALONE_SEASON_RE = re.compile(r"(?<![A-Za-z0-9(\[])S(?P<n>\d{1,2})(?![A-Za-z0-9)\]])")

# [1-25 из 25], [25 из 25], [01-13 из 13], [1-1122 из >1122], [12 из 12 + Special], [1-12 of 12]
_TOTAL = r"(?P<open>[>+~]\s*)?(?P<total>\d{1,4}(?:\+\d{1,3})?|\?+|x+|х+)?(?P<plus>\+)?"
_EP_CORE = r"(?P<a>\d{1,4})(?:\+\d{1,3})?(?:\s*[-–—]\s*(?P<b>\d{1,4}))?\s*(?:из|of)\s*" + _TOTAL
EP_BRACKET_RE = re.compile(
    r"\[\s*(?:(?:eps?\.?|episodes?|серии|серия)\s*:?\s*)?" + _EP_CORE + r"[^\]]*\]",
    re.IGNORECASE,
)
EP_PLAIN_RE = re.compile(r"(?:Серии|Серия|Episodes?)\s*:?\s*" + _EP_CORE, re.IGNORECASE)
SEASON_PLAIN_RE = re.compile(r"(?:Сезон|Season)\s*:\s*(?P<n>\d{1,2})", re.IGNORECASE)
# Формы Prowlarr: "S1E1-8 of 8", "S1E1-8", "E12 of 12", "E13-22 of 22", "E1-8"
PROWLARR_SE_RE = re.compile(
    r"(?<![A-Za-z0-9])S(?P<s>\d{1,2})E(?P<a>\d{1,4})(?:-(?P<b>\d{1,4}))?(?:\s+of\s+" + _TOTAL + r")?(?![A-Za-z0-9])",
    re.IGNORECASE,
)
PROWLARR_E_RE = re.compile(
    r"(?<![A-Za-z0-9])E(?P<a>\d{1,4})(?:\+\d{1,3})?(?:-(?P<b>\d{1,4}))?\s+of\s+"
    r"(?P<open>[>+~]\s*)?(?P<total>\d{1,4}(?:\+\d{1,3})?|\?+|x+|х+|\w)(?P<plus>\+)?(?![A-Za-z0-9])",
    re.IGNORECASE,
)
PROWLARR_E_RANGE_RE = re.compile(r"(?<![A-Za-z0-9])E(?P<a>\d{1,4})-(?P<b>\d{1,4})(?![A-Za-z0-9])", re.IGNORECASE)
# [1-25 из 25] после Strip Russian letters: [1-25 25]
STRIPPED_EP_BRACKET_RE = re.compile(
    r"\[\s*(?P<a>\d{1,4})\s*[-–—]\s*(?P<b>\d{1,4})\s+(?P<open>[>+~]\s*)?(?P<total>\d{1,4})(?P<plus>\+)?\s*\]"
)
EPISODE_RES = (EP_BRACKET_RE, EP_PLAIN_RE, PROWLARR_SE_RE, PROWLARR_E_RE, PROWLARR_E_RANGE_RE, STRIPPED_EP_BRACKET_RE)
# [2017, ...] — скобка с годом и качеством; нужна только чтобы не считать её частью названия
YEAR_BRACKET_RE = re.compile(r"\[\s*(?:19|20)\d{2}(?![\d])")

# Источник видео -> токен, который Sonarr уверенно распознаёт.
SOURCE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bDVD[-\s]?Remux\b", re.I), "DVDRip"),
    (re.compile(r"\b(?:BD|Blu-?Ray)[-\s]?(?:Remux|Mux)\b|\bRemux\b", re.I), "BluRay Remux"),
    (re.compile(r"\bBD-?Rip\b|\bBRRip\b|\bBlu-?Ray(?:Rip)?\b|\bBD\b", re.I), "BDRip"),
    (re.compile(r"\bWEB[-\s]?DL(?:Rip)?\b|\bWEBDL\b", re.I), "WEB-DL"),
    (re.compile(r"\bWEB[-\s]?Rip\b", re.I), "WEBRip"),
    (re.compile(r"\bHDTV(?:Rip)?\b|\bTVRip\b|\bSATRip\b|\bDVBRip\b|\bIPTVRip\b|\bPDTV(?:Rip)?\b|\bHDRip\b", re.I), "HDTV"),
    (re.compile(r"\bDVD(?:Rip|[59])?\b", re.I), "DVDRip"),
]
RES_RE = re.compile(r"\b(?P<p>2160|1440|1080|720|576|480|360)[pi]\b", re.I)
DIM_RE = re.compile(r"\b(?P<w>\d{3,4})\s*[x×х]\s*(?P<h>\d{3,4})\b", re.I)
UHD_RE = re.compile(r"\b(?:4K|UHD)\b", re.I)
CODEC_RE = re.compile(
    r"\b(?P<x265>x265|HEVC|H\.?265)\b|\b(?P<x264>x264|AVC|H\.?264)\b|\b(?P<av1>AV1)\b", re.I
)
BITS_RE = re.compile(r"\b(?:10[-\s]?bit|Hi10P?)\b", re.I)
LANG_RE = re.compile(r"\[([^\]]*\b(?:RUS|JAP|JPN|ENG|Sub|Dub|RAW)\b[^\]]*)\]", re.I)

# Хвосты названий, которые дублируют номер сезона.
SEASON_WORD_RE = re.compile(
    r"[\s:,\-–]*\b(?:(?P<ord>\d{1,2})(?:st|nd|rd|th)|(?P<word>second|third|fourth|fifth|sixth|seventh))\s+Season\b"
    r"|[\s:,\-–]*\bSeason\s+(?P<n>\d{1,2})\b",
    re.IGNORECASE,
)
ORDINAL_WORDS = {"second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7}
PART_RE = re.compile(r"[\s:,\-–]*\b(?:Part|Cour|Часть)\s*(?P<n>\d{1,2})\b", re.IGNORECASE)
ROMAN_RE = re.compile(r"\s+(?P<r>II|III|IV|VI|VII|VIII|IX)$")
ROMAN = {"II": 2, "III": 3, "IV": 4, "VI": 6, "VII": 7, "VIII": 8, "IX": 9}
# "(Режиссёр)" в конце шапки убираем, "(2011)" оставляем: год — часть названия в TVDB.
TRAILING_PAREN_RE = re.compile(r"\s*\((?!\d{4}\))[^()]*\)\s*$")
CYRILLIC_PAREN_RE = re.compile(r"\s*\([^)]*[А-Яа-яЁё][^)]*\)")
LEADING_BRACKET_RE = re.compile(r"^\[([^\]]+)\]")


@dataclass
class Release:
    """Распознанная раздача."""

    raw: str
    title: str
    kind: str
    season: int | None = None
    first: int | None = None
    last: int | None = None
    total: int | None = None
    open_ended: bool = False
    part: int | None = None
    source: str | None = None
    resolution: str | None = None
    codec: str | None = None
    bits: str | None = None
    languages: str | None = None

    @property
    def complete(self) -> bool:
        """Раздача содержит все серии (``[1-25 из 25]``, ``[25 из 25]``, ``E12 of 12``)."""
        if self.last is None or self.total is None or self.open_ended:
            return False
        return self.last >= self.total

    @property
    def episode_count(self) -> int | None:
        if self.first is None or self.last is None:
            return None
        return self.last - self.first + 1


@dataclass
class _Episodes:
    first: int | None = None
    last: int | None = None
    total: int | None = None
    open_ended: bool = False
    season: int | None = None


def parse_title(raw: str, *, title_pick: str = "first") -> Release | None:
    """Разобрать заголовок RuTracker. ``title_pick`` выбирает латинскую часть: ``first`` или ``last``."""
    text = " ".join(raw.split())
    if not text:
        return None

    type_match = TYPE_RE.search(text)
    prowlarr_type = None if type_match else PROWLARR_TYPE_RE.search(text)
    season_plain = SEASON_PLAIN_RE.search(text)
    standalone_season = STANDALONE_SEASON_RE.search(text)
    episode_matches = [m for m in (rx.search(text) for rx in EPISODE_RES) if m]
    year_bracket = YEAR_BRACKET_RE.search(text)

    markers = [
        m for m in (type_match, prowlarr_type, season_plain, standalone_season, year_bracket, *episode_matches) if m
    ]
    if not markers:
        return None
    cut = min(m.start() for m in markers)
    head, tail = text[:cut], text[cut:]

    bracket_season: int | None = None
    part: int | None = None
    if type_match:
        kind = KIND_MAP[type_match.group("kind").lower()]
        bracket_season = int(type_match.group("num")) if type_match.group("num") else None
        part = _find_part(type_match.group("rest"))
    elif prowlarr_type:
        kind = "TV"
        bracket_season = int(prowlarr_type.group("num"))
    elif episode_matches or season_plain or standalone_season:
        kind = "TV"
    else:
        # только год и качество: скорее всего фильм, не трогаем
        return None

    head_season, head_part = _head_season(head)
    latin = _latin_parts(head)
    if not latin:
        return None
    title, title_season, title_part = _clean_title(latin[-1] if title_pick == "last" else latin[0])
    if not title:
        return None

    eps = _parse_episodes(tail)
    season = _first_not_none(
        bracket_season,
        head_season,
        title_season,
        eps.season,
        int(season_plain.group("n")) if season_plain else None,
        int(standalone_season.group("n")) if standalone_season else None,
    )

    return Release(
        raw=raw,
        title=title,
        kind=kind,
        season=season,
        first=eps.first,
        last=eps.last,
        total=eps.total,
        open_ended=eps.open_ended,
        part=_first_not_none(part, head_part, title_part),
        source=_find_source(tail),
        resolution=_find_resolution(tail),
        codec=_find_codec(tail),
        bits="10bit" if BITS_RE.search(tail) else None,
        languages=_find_languages(tail),
    )


def _first_not_none(*values: int | None) -> int | None:
    for value in values:
        if value is not None:
            return value
    return None


def _head_season(head: str) -> tuple[int | None, int | None]:
    m = HEAD_SEASON_RE.search(head)
    if not m:
        return None, None
    rest = m.group("rest")
    part_match = PART_RE.search(rest) or re.search(r",\s*(?P<n>\d{1,2})\s*$", rest)
    return int(m.group("n")), int(part_match.group("n")) if part_match else None


def _latin_parts(head: str) -> list[str]:
    head = HEAD_SEASON_RE.sub(" ", head).strip()
    for _ in range(3):
        stripped = TRAILING_PAREN_RE.sub("", head)
        if stripped == head:
            break
        head = stripped
    parts = []
    for part in re.split(r"\s+/\s+", head):
        part = CYRILLIC_PAREN_RE.sub("", part).strip(" /")
        if part and LATIN_RE.search(part) and not CYRILLIC_RE.search(part):
            parts.append(part)
    return parts


def _clean_title(part: str) -> tuple[str, int | None, int | None]:
    title = LEADING_BRACKET_RE.sub(r"\1", part.strip())
    season: int | None = None
    part_no: int | None = None

    m = SEASON_WORD_RE.search(title)
    if m:
        if m.group("ord"):
            season = int(m.group("ord"))
        elif m.group("word"):
            season = ORDINAL_WORDS[m.group("word").lower()]
        else:
            season = int(m.group("n"))
        title = title[: m.start()] + title[m.end():]

    m = PART_RE.search(title)
    if m:
        part_no = int(m.group("n"))
        title = title[: m.start()] + title[m.end():]

    title = " ".join(title.split()).strip(" :,-–")
    m = ROMAN_RE.search(title)
    if m:
        if season is None:
            season = ROMAN[m.group("r")]
        title = title[: m.start()]

    return title.strip(" :,-–"), season, part_no


def _find_part(rest: str | None) -> int | None:
    if not rest:
        return None
    m = PART_RE.search(rest)
    return int(m.group("n")) if m else None


def _parse_episodes(tail: str) -> _Episodes:
    for rx in EPISODE_RES:
        m = rx.search(tail)
        if not m:
            continue
        groups = m.groupdict()
        a = int(groups["a"])
        b = int(groups["b"]) if groups.get("b") else None
        first, last = (a, b) if b is not None else (1, a)
        if first > last:
            first, last = last, first
        total_text = groups.get("total")
        total = int(total_text) if total_text and total_text.isdigit() else None
        return _Episodes(
            first=first,
            last=last,
            total=total,
            open_ended=bool(groups.get("open") or groups.get("plus")),
            season=int(groups["s"]) if groups.get("s") else None,
        )
    return _Episodes()


def _find_source(tail: str) -> str | None:
    for pattern, name in SOURCE_PATTERNS:
        if pattern.search(tail):
            return name
    return None


def _height_to_res(height: int) -> str | None:
    if height >= 1600:
        return "2160p"
    if height >= 1000:
        return "1080p"
    if height >= 700:
        return "720p"
    if height >= 560:
        return "576p"
    if height >= 400:
        return "480p"
    return None


def _find_resolution(tail: str) -> str | None:
    heights = [int(m.group("p")) for m in RES_RE.finditer(tail)]
    heights += [int(m.group("h")) for m in DIM_RE.finditer(tail)]
    if UHD_RE.search(tail):
        heights.append(2160)
    if not heights:
        return None
    return _height_to_res(max(heights))


def _find_codec(tail: str) -> str | None:
    m = CODEC_RE.search(tail)
    if not m:
        return None
    if m.group("x265"):
        return "x265"
    if m.group("x264"):
        return "x264"
    return "AV1"


def _find_languages(tail: str) -> str | None:
    m = LANG_RE.search(tail)
    return m.group(1).strip() if m else None
