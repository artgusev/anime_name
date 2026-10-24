"""Настройки из переменных окружения и файл overrides (TOML)."""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Mapping

from .langfilter import QueryFilter
from .render import Converter, Override, RenderOptions

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]

TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass
class Settings:
    upstream_url: str = "http://prowlarr:9696"
    listen_host: str = "0.0.0.0"
    listen_port: int = 8080
    overrides_file: str | None = None
    pack_style: str = "season"
    max_episodes: int = 100
    release_group: str = ""
    title_pick: str = "first"
    # Передавать ли season/ep дальше в Prowlarr. Для аниме на RuTracker это только мешает поиску.
    forward_season: bool = False
    # Если задан, ссылки на скачивание в ответах переписываются с UPSTREAM_URL на этот адрес,
    # и Sonarr качает .torrent через прокси, а не напрямую из Prowlarr.
    public_url: str | None = None
    log_level: str = "INFO"
    upstream_timeout: float = 60.0
    # Кэш ответов на поисковые запросы с q: после очистки "Title S2", "Title Season 2" и "Title"
    # становятся одним запросом, и Prowlarr получает его один раз. 0 выключает кэш.
    cache_ttl: float = 300.0
    cache_size: int = 256
    # Языки, на которых запросы уходят в Prowlarr; остальные сразу получают пустой RSS.
    # en включает ромадзи. "any" выключает фильтр.
    query_languages: str = "ru,en"
    # Регулярное выражение (без учёта регистра): запросы с таким q всегда получают пустой RSS.
    query_skip: str = ""
    # Регулярное выражение: запросы с таким q всегда уходят в Prowlarr, минуя фильтр языков.
    query_allow: str = ""

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        kwargs = {}
        for f in fields(cls):
            key = f.name.upper()
            if key not in env or env[key] == "":
                continue
            value = env[key]
            if f.type in ("int", int):
                kwargs[f.name] = int(value)
            elif f.type in ("float", float):
                kwargs[f.name] = float(value)
            elif f.type in ("bool", bool):
                kwargs[f.name] = value.strip().lower() in TRUE_VALUES
            else:
                kwargs[f.name] = value
        settings = cls(**kwargs)
        settings.upstream_url = settings.upstream_url.rstrip("/")
        if settings.public_url:
            settings.public_url = settings.public_url.rstrip("/")
        return settings

    def render_options(self) -> RenderOptions:
        return RenderOptions(
            pack_style=self.pack_style,
            max_episodes=self.max_episodes,
            release_group=self.release_group,
        )

    def converter(self) -> Converter:
        overrides = load_overrides(self.overrides_file) if self.overrides_file else []
        return Converter(options=self.render_options(), overrides=overrides, title_pick=self.title_pick)

    def query_filter(self) -> QueryFilter:
        return QueryFilter.build(self.query_languages, self.query_skip, self.query_allow)


def load_overrides(path: str | os.PathLike[str]) -> list[Override]:
    """Прочитать overrides из TOML: массив таблиц ``[[override]]`` с полями match/skip/title/season."""
    if tomllib is None:
        raise RuntimeError("Для чтения overrides нужен Python 3.11+ (модуль tomllib)")
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    entries = data.get("override", [])
    if not isinstance(entries, list):
        raise ValueError("В файле overrides ожидается массив таблиц [[override]]")
    return [Override.from_dict(entry) for entry in entries]
