"""CLI: ``animename convert`` для проверки заголовков, ``animename serve`` для прокси."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict

from . import __version__
from .config import Settings, load_overrides
from .render import Converter


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="animename",
        description="Torznab-прокси между Prowlarr и Sonarr, переписывающий заголовки RuTracker.",
    )
    p.add_argument("--version", action="version", version=f"animename {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("convert", help="преобразовать заголовки (аргументы или stdin, по одному в строке)")
    c.add_argument("titles", nargs="*", help="заголовки RuTracker; без аргументов читается stdin")
    c.add_argument("--json", action="store_true", help="вывести разобранные поля в JSON")
    c.add_argument("--overrides", metavar="FILE", help="TOML с правилами [[override]]")
    c.add_argument("--pack-style", choices=["season", "range"])
    c.add_argument("--max-episodes", type=int, metavar="N")
    c.add_argument("--title-pick", choices=["first", "last"])
    c.add_argument("--release-group", metavar="NAME")

    s = sub.add_parser("serve", help="запустить прокси (настройки из переменных окружения)")
    s.add_argument("--upstream", metavar="URL", help="адрес Prowlarr, например http://prowlarr:9696")
    s.add_argument("--host", metavar="HOST")
    s.add_argument("--port", type=int, metavar="PORT")
    s.add_argument("--overrides", metavar="FILE")
    s.add_argument("--cache-ttl", type=float, metavar="SECONDS", help="0 выключает кэш ответов")
    s.add_argument("--query-skip", metavar="REGEX", help="запросы с таким q получают пустой RSS")
    s.add_argument("--log-level", metavar="LEVEL")
    return p


def settings_from_args(args: argparse.Namespace) -> Settings:
    settings = Settings.from_env()
    mapping = {
        "overrides": "overrides_file", "pack_style": "pack_style", "max_episodes": "max_episodes",
        "title_pick": "title_pick", "release_group": "release_group", "upstream": "upstream_url",
        "host": "listen_host", "port": "listen_port", "log_level": "log_level",
        "cache_ttl": "cache_ttl", "query_skip": "query_skip",
    }
    for arg, attr in mapping.items():
        value = getattr(args, arg, None)
        if value is not None:
            setattr(settings, attr, value.rstrip("/") if attr == "upstream_url" else value)
    return settings


def cmd_convert(args: argparse.Namespace) -> int:
    settings = settings_from_args(args)
    converter = Converter(
        options=settings.render_options(),
        overrides=load_overrides(settings.overrides_file) if settings.overrides_file else [],
        title_pick=settings.title_pick,
    )
    titles = args.titles or [line.rstrip("\n") for line in sys.stdin]
    for raw in titles:
        if not raw.strip():
            continue
        rel = converter.parse(raw)
        result = converter.convert_release(rel) if rel else None
        if args.json:
            payload = {"raw": raw, "sonarr": result, "rewritten": result is not None}
            if rel:
                payload["release"] = {k: v for k, v in asdict(rel).items() if k != "raw"}
                payload["release"]["complete"] = rel.complete
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(result if result else raw)
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    settings = settings_from_args(args)
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    from .server import serve

    serve(settings)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "convert":
        return cmd_convert(args)
    return cmd_serve(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
