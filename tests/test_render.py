import re

import pytest

from animename.config import Settings, load_overrides
from animename.render import Converter, Override, RenderOptions

AOT = "Атака титанов / Shingeki no Kyojin [TV-1] [1-25 из 25] [RUS(int), JAP+Sub] [2013, BDRip] [1080p]"
AOT_PART = "Атака титанов (ТВ-4, часть 3) / Shingeki no Kyojin: The Final Season Part 3 [TV-4 Part 3] [1-2 из 2] [2023, WEB-DL] [1080p]"


def test_override_skip():
    conv = Converter(overrides=[Override(re.compile("shingeki", re.I), skip=True)])
    assert conv.convert(AOT) is None


def test_override_title_and_season():
    conv = Converter(overrides=[Override(re.compile("^Shingeki no Kyojin"), title="Attack on Titan", season=4)])
    assert conv.convert(AOT) == "Attack on Titan S04 [BDRip 1080p]"


def test_override_first_match_wins():
    conv = Converter(
        overrides=[
            Override(re.compile("Final Season"), skip=True),
            Override(re.compile("Shingeki"), title="Attack on Titan"),
        ]
    )
    assert conv.convert(AOT_PART) is None
    assert conv.convert(AOT) == "Attack on Titan S01 [BDRip 1080p]"


def test_override_from_dict_requires_match():
    with pytest.raises(ValueError):
        Override.from_dict({"skip": True})


def test_load_overrides(tmp_path):
    path = tmp_path / "overrides.toml"
    path.write_text(
        """
[[override]]
match = "^One Piece"
skip = true

[[override]]
match = "^Shingeki no Kyojin"
title = "Attack on Titan"
season = 2
""",
        encoding="utf-8",
    )
    overrides = load_overrides(path)
    assert [o.skip for o in overrides] == [True, False]
    assert overrides[1].title == "Attack on Titan"
    assert overrides[1].season == 2
    conv = Converter(overrides=overrides)
    assert conv.convert(AOT) == "Attack on Titan S02 [BDRip 1080p]"


def test_settings_from_env(tmp_path):
    path = tmp_path / "o.toml"
    path.write_text('[[override]]\nmatch = "x"\nskip = true\n', encoding="utf-8")
    s = Settings.from_env(
        {
            "UPSTREAM_URL": "http://prowlarr:9696/",
            "LISTEN_PORT": "9000",
            "MAX_EPISODES": "50",
            "FORWARD_SEASON": "yes",
            "PACK_STYLE": "range",
            "RELEASE_GROUP": "RuTracker",
            "PUBLIC_URL": "http://animename:8080/",
            "OVERRIDES_FILE": str(path),
            "CACHE_TTL": "600",
            "CACHE_SIZE": "32",
            "QUERY_SKIP": "Ataque|Attaque",
            "QUERY_ALLOW": "Chevalier",
            "QUERY_LANGUAGES": "ru",
        }
    )
    assert s.upstream_url == "http://prowlarr:9696"
    assert s.public_url == "http://animename:8080"
    assert (s.listen_port, s.max_episodes, s.forward_season) == (9000, 50, True)
    assert (s.cache_ttl, s.cache_size, s.query_skip) == (600.0, 32, "Ataque|Attaque")
    qf = s.query_filter()
    assert qf.languages == frozenset({"ru"})
    assert qf.reason("Attack on Titan") == "language=en not in ru"
    assert qf.reason("Le Chevalier DEon") is None
    conv = s.converter()
    assert conv.options == RenderOptions(pack_style="range", max_episodes=50, release_group="RuTracker")
    assert len(conv.overrides) == 1


def test_settings_defaults():
    s = Settings.from_env({})
    assert s.upstream_url == "http://prowlarr:9696"
    assert s.listen_port == 8080
    assert (s.cache_ttl, s.cache_size, s.query_skip) == (300.0, 256, "")
    assert s.query_languages == "ru,en"
    assert s.query_filter().languages == frozenset({"ru", "en"})
    assert s.converter().overrides == []
