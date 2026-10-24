"""Сборка заголовка в формате Sonarr из Release и применение overrides."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .parser import Release, parse_title

PACK_STYLES = ("season", "range")


@dataclass(frozen=True)
class RenderOptions:
    # season: полная раздача -> "Title S01"; range: "Title S01E01-E25".
    pack_style: str = "season"
    # Раздачи с бо́льшим числом серий не переписываются: у Sonarr такой «сезон» не совпадёт с TVDB.
    max_episodes: int = 100
    # Суффикс релиз-группы: "...-RuTracker". Пусто -> не добавлять.
    release_group: str = ""

    def __post_init__(self) -> None:
        if self.pack_style not in PACK_STYLES:
            raise ValueError(f"pack_style must be one of {PACK_STYLES}, got {self.pack_style!r}")


@dataclass
class Override:
    """Правило для конкретного тайтла. ``pattern`` ищется в латинском названии без учёта регистра."""

    pattern: re.Pattern[str]
    skip: bool = False
    title: str | None = None
    season: int | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "Override":
        try:
            pattern = re.compile(str(data["match"]), re.IGNORECASE)
        except KeyError:
            raise ValueError("override без поля 'match'") from None
        return cls(
            pattern=pattern,
            skip=bool(data.get("skip", False)),
            title=str(data["title"]) if data.get("title") else None,
            season=int(data["season"]) if data.get("season") is not None else None,
        )


def render(
    rel: Release,
    opts: RenderOptions = RenderOptions(),
    *,
    title: str | None = None,
    season: int | None = None,
) -> str | None:
    """Вернуть заголовок для Sonarr или ``None``, если раздачу лучше оставить как есть."""
    if rel.kind != "TV":
        return None
    title = title or rel.title
    season = season if season is not None else (rel.season or 1)

    if rel.first is None or rel.last is None:
        marker = f"S{season:02d}"
    else:
        if rel.episode_count > opts.max_episodes:
            return None
        if rel.complete and rel.first == 1 and opts.pack_style == "season":
            marker = f"S{season:02d}"
        elif rel.first == rel.last:
            marker = f"S{season:02d}E{rel.first:02d}"
        else:
            marker = f"S{season:02d}E{rel.first:02d}-E{rel.last:02d}"

    quality = " ".join(x for x in (rel.source, rel.resolution, rel.codec, rel.bits) if x)
    out = f"{title} {marker}"
    if quality:
        out += f" [{quality}]"
    if opts.release_group:
        out += f"-{opts.release_group}"
    return out


@dataclass
class Converter:
    """Полный конвейер: заголовок RuTracker -> заголовок Sonarr (или ``None``)."""

    options: RenderOptions = RenderOptions()
    overrides: list[Override] = field(default_factory=list)
    title_pick: str = "first"

    def parse(self, raw: str) -> Release | None:
        return parse_title(raw, title_pick=self.title_pick)

    def find_override(self, rel: Release) -> Override | None:
        for ov in self.overrides:
            if ov.pattern.search(rel.title):
                return ov
        return None

    def convert_release(self, rel: Release) -> str | None:
        ov = self.find_override(rel)
        if ov and ov.skip:
            return None
        return render(
            rel,
            self.options,
            title=ov.title if ov else None,
            season=ov.season if ov else None,
        )

    def convert(self, raw: str) -> str | None:
        rel = self.parse(raw)
        if rel is None:
            return None
        return self.convert_release(rel)
