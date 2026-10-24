"""Язык поискового запроса и правила, по которым запрос не уходит в Prowlarr.

Sonarr перебирает все альтернативные названия сериала с TVDB: испанские, французские,
японские иероглифами и так далее. На RuTracker они бесполезны, поэтому по умолчанию
дальше идут только запросы на русском и английском (ромадзи тоже латиница и считается
английским), а на остальные прокси отвечает, что результатов нет.

Определение языка без зависимостей:

* алфавит: кана, иероглифы, хангыль, греческий, арабский, иврит, тайский -> чужой язык;
* кириллица с буквами і ї є ґ ў ј љ њ ћ ђ џ -> не русский;
* латиница: считаются характерные служебные слова (``los``, ``des``, ``dei``, ``und``...),
  которых не бывает ни в английских названиях, ни в ромадзи. Английские служебные слова
  (``the``, ``of``, ``in``...) перевешивают, чтобы ``El Hazard: The Magnificent World``
  остался английским.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

SCRIPT_LANG = {
    "HIRAGANA": "ja", "KATAKANA": "ja", "CJK": "zh", "HANGUL": "ko", "GREEK": "el",
    "ARABIC": "ar", "HEBREW": "he", "THAI": "th", "DEVANAGARI": "hi", "ARMENIAN": "hy",
    "GEORGIAN": "ka",
}
SCRIPT_PREFIXES = ("LATIN", "CYRILLIC") + tuple(SCRIPT_LANG)

# Буквы, которых нет в русском алфавите.
CYRILLIC_MARKERS = {
    "uk": set("іїєґ"),
    "be": set("ў"),
    "sr": set("јљњћђџ"),
    "mk": set("ѕѓќ"),
    "kk": set("әғқңөұүһ"),
}

# Английские служебные слова. Без "a" и "no": они же испанские ("Ataque a los Titanes"),
# и один такой артикль уравновешивал бы настоящий испанский маркер.
EN_WORDS = frozenset(
    "the of and in on at to for with from by my your his her our their this that is are was "
    "be or not it its as an into over under up down out about after before who what "
    "when where why how".split()
)

# Характерные слова других языков на латинице. Сознательно пропущены слова, которые
# встречаются в английских названиях или в ромадзи: de, da, do, die, den, un, uma, os,
# non, et, ed, im, am, um, mi, sao, e, o, a, na, no.
MARKERS: dict[str, frozenset[str]] = {
    "es": frozenset("los las del el la una por para que y con sin sobre hacia entre cuando".split()),
    "fr": frozenset("les des du le la une aux au dans pour sur avec qui que cette ces chez vers sans sous".split()),
    "it": frozenset(
        "gli dei degli della delle dello del il lo le la nel nella nelle nei con per una uno che chi "
        "sono alla alle allo agli dalla sul sulla".split()
    ),
    "de": frozenset(
        "der das und ein eine einer eines dem des mit von zu zum zur auf fur ist nicht aus bei nach "
        "unter durch gegen ohne".split()
    ),
    "pt": frozenset("dos das aos pelo pela nao mais muito quando onde voce para por com".split()),
}

# Устойчивые сочетания, которые бывают в английских названиях и не должны считаться.
EXCEPTION_PHRASES = ("los angeles", "las vegas", "el paso", "el dorado", "la la land", "le mans")

LATIN_WORD_RE = re.compile(r"[a-z]+")
ANY_LANGUAGE = ("any", "all", "*", "off", "none")


def _script(ch: str) -> str:
    name = unicodedata.name(ch, "")
    for prefix in SCRIPT_PREFIXES:
        if name.startswith(prefix):
            return prefix
    return "OTHER"


def _strip_accents(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def _latin_language(query: str) -> str:
    text = _strip_accents(query.lower())
    for phrase in EXCEPTION_PHRASES:
        text = text.replace(phrase, " ")
    tokens = LATIN_WORD_RE.findall(text)
    english = sum(token in EN_WORDS for token in tokens)
    scores = {lang: sum(token in words for token in tokens) for lang, words in MARKERS.items()}
    lang, best = max(scores.items(), key=lambda item: item[1])
    if best == 0 or english >= best:
        return "en"
    return lang


def detect_language(query: str) -> str:
    """Код языка: ``en`` (включая ромадзи), ``ru``, ``es``/``fr``/``it``/``de``/``pt``,
    ``uk``/``be``/``sr``/``mk``/``kk``, ``ja``/``zh``/``ko``/..., ``other`` или ``none`` (нет букв)."""
    letters = [ch for ch in query if ch.isalpha()]
    if not letters:
        return "none"
    scripts = {_script(ch) for ch in letters}
    foreign = scripts - {"LATIN", "CYRILLIC"}
    if foreign:
        if foreign & {"HIRAGANA", "KATAKANA"}:
            return "ja"
        for prefix in SCRIPT_LANG:
            if prefix in foreign:
                return SCRIPT_LANG[prefix]
        return "other"
    if "CYRILLIC" in scripts:
        lower = {ch.lower() for ch in letters}
        for code, marks in CYRILLIC_MARKERS.items():
            if lower & marks:
                return code
        return "ru"
    return _latin_language(query)


def parse_languages(value: str | None) -> frozenset[str] | None:
    """``"ru,en"`` -> ``{"ru", "en"}``; ``any``/``all``/``*``/``off`` или пусто -> ``None`` (без фильтра)."""
    if value is None:
        return None
    codes = {code.strip().lower() for code in re.split(r"[,\s]+", value) if code.strip()}
    if not codes or codes & set(ANY_LANGUAGE):
        return None
    return frozenset(codes)


@dataclass(frozen=True)
class QueryFilter:
    """Решает, идёт ли очищенный запрос в Prowlarr. ``reason`` возвращает причину отказа или ``None``."""

    languages: frozenset[str] | None = frozenset({"ru", "en"})
    skip: re.Pattern[str] | None = None
    allow: re.Pattern[str] | None = None

    @classmethod
    def build(cls, languages: str | None = "ru,en", skip: str = "", allow: str = "") -> "QueryFilter":
        return cls(
            languages=parse_languages(languages),
            skip=_compile("QUERY_SKIP", skip),
            allow=_compile("QUERY_ALLOW", allow),
        )

    @property
    def active(self) -> bool:
        return bool(self.languages is not None or self.skip)

    def reason(self, q: str) -> str | None:
        if self.skip and self.skip.search(q):
            return "QUERY_SKIP"
        if self.allow and self.allow.search(q):
            return None
        if self.languages is None:
            return None
        lang = detect_language(q)
        if lang == "none" or lang in self.languages:
            return None
        return f"language={lang} not in {','.join(sorted(self.languages))}"


def _compile(name: str, pattern: str) -> re.Pattern[str] | None:
    if not pattern:
        return None
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise ValueError(f"{name}: некорректное регулярное выражение {pattern!r}: {exc}") from exc
