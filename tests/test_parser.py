import pytest

from animename.parser import parse_title
from animename.render import RenderOptions, render

SEASON = RenderOptions(pack_style="season")
RANGE = RenderOptions(pack_style="range")


def convert(raw, opts=SEASON, **kwargs):
    rel = parse_title(raw, **kwargs)
    return render(rel, opts) if rel else None


@pytest.mark.parametrize(
    "raw, expected",
    [
        # полная раздача -> сезон-пак
        (
            "Атака титанов / Shingeki no Kyojin [TV-1] [1-25 из 25] [RUS(int), JAP+Sub] "
            "[2013, приключения, фэнтези, драма, BDRip] [1080p]",
            "Shingeki no Kyojin S01 [BDRip 1080p]",
        ),
        # "N из N" без диапазона
        (
            "Клинок, рассекающий демонов / Kimetsu no Yaiba [TV] [26 из 26] [RUS(int), JAP+Sub] "
            "[2019, приключения, BDRip] [1080p]",
            "Kimetsu no Yaiba S01 [BDRip 1080p]",
        ),
        # сезон из хвоста названия и из скобки, хвост убирается
        (
            "Магическая битва (ТВ-2) / Jujutsu Kaisen 2nd Season [TV-2] [1-23 из 23] [RUS(ext), JAP+Sub] "
            "[2023, экшен, фэнтези, WEBRip] [1080p]",
            "Jujutsu Kaisen S02 [WEBRip 1080p]",
        ),
        # онгоинг -> диапазон
        (
            "Фрирен, провожающая в последний путь / Sousou no Frieren [TV] [1-17 из 28] [RUS(int), JAP+Sub] "
            "[2023, приключения, фэнтези, WEB-DL] [1080p]",
            "Sousou no Frieren S01E01-E17 [WEB-DL 1080p]",
        ),
        # одна серия
        (
            "Дандадан / Dandadan [TV] [01 из 12] [RUS(int), JAP+Sub] [2024, комедия, WEB-DL] [1080p]",
            "Dandadan S01E01 [WEB-DL 1080p]",
        ),
        # вторая половина сезона, номер части убирается из названия
        (
            "Атака титанов (ТВ-3, часть 2) / Shingeki no Kyojin Season 3 Part 2 [TV-3 Part 2] [13-22 из 22] "
            "[RUS(int), JAP+Sub] [2019, BDRip] [1080p]",
            "Shingeki no Kyojin S03E13-E22 [BDRip 1080p]",
        ),
        # название в квадратных скобках
        (
            "Звёздное дитя / [Oshi no Ko] [TV-1] [1-11 из 11] [RUS(int), JAP+Sub] [2023, драма, WEBRip] [1080p]",
            "Oshi no Ko S01 [WEBRip 1080p]",
        ),
        # римская цифра и HEVC
        (
            "Повелитель IV / Overlord IV [TV-4] [1-13 из 13] [RUS(int), JAP+Sub] [2022, фэнтези, WEB-DL] [1080p HEVC]",
            "Overlord S04 [WEB-DL 1080p x265]",
        ),
        # римская цифра даёт сезон, если в скобке его нет
        (
            "Мастера меча онлайн II / Sword Art Online II [TV] [1-24 из 24] [RUS(int), JAP+Sub] "
            "[2014, приключения, BDRip] [720p]",
            "Sword Art Online S02 [BDRip 720p]",
        ),
        # режиссёр в скобках убирается, год в названии остаётся
        (
            "Охотник х Охотник / Hunter x Hunter (2011) (Кодзима Хироси) [TV] [1-62 из 62] [RUS(int), JAP+Sub] "
            "[2011, приключения, BDRip] [1080p]",
            "Hunter x Hunter (2011) S01 [BDRip 1080p]",
        ),
        # разрешение в пикселях, 10 бит, x264
        (
            "Твоя апрельская ложь / Shigatsu wa Kimi no Uso [TV] [22 из 22] [JAP+Sub] [2014, драма, BDRip] "
            "[1920x1080, x264, 10bit]",
            "Shigatsu wa Kimi no Uso S01 [BDRip 1080p x264 10bit]",
        ),
        # BDRemux
        (
            "Ковбой Бибоп / Cowboy Bebop [TV] [26 из 26] [RUS(int), JAP+Sub] [1998, BDRemux] [1080p]",
            "Cowboy Bebop S01 [BluRay Remux 1080p]",
        ),
        # Second Season словами, несколько разрешений -> максимальное
        (
            "Моя геройская академия / Boku no Hero Academia Second Season [TV-2] [1-25 из 25] [RUS(int), JAP+Sub] "
            "[2017, HDTVRip] [720p, 1080p]",
            "Boku no Hero Academia S02 [HDTV 1080p]",
        ),
        # обычный сериал в формате "Сезон: / Серии:"
        (
            "Твин Пикс / Twin Peaks / Сезон: 1 / Серии: 1-8 из 8 (Дэвид Линч) [1990, США, драма, BDRip 1080p] "
            "MVO + Original + Sub",
            "Twin Peaks S01 [BDRip 1080p]",
        ),
        (
            "Очень странные дела / Stranger Things / Сезон: 4 / Серии: 1-7 из 9 [2022, США, WEB-DL 2160p HEVC HDR]",
            "Stranger Things S04E01-E07 [WEB-DL 2160p x265]",
        ),
        # без скобки с качеством
        (
            "Евангелион / Shinseiki Evangelion [TV] [26 из 26]",
            "Shinseiki Evangelion S01",
        ),
        # "+ Special" в скобке серий не делает раздачу бесконечной
        (
            "Ванпанчмен / One Punch Man [TV-1] [12 из 12 + Special] [RUS(int), JAP+Sub] [2015, BDRip] [1080p]",
            "One Punch Man S01 [BDRip 1080p]",
        ),
    ],
)
def test_rewrites(raw, expected):
    assert convert(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        # фильмы и OVA не трогаем
        "Твоё имя / Kimi no Na wa [Movie] [RUS(int), JAP+Sub] [2016, романтика, BDRip] [1080p]",
        "Хеллсинг / Hellsing Ultimate [OVA] [10 из 10] [RUS(int), JAP+Sub] [2006, BDRip] [1080p]",
        # нет латинского названия
        "Слово пацана. Кровь на асфальте / Сезон: 1 / Серии: 1-6 из 8 [2023, Россия, драма, WEB-DL 1080p]",
        # не раздача сериала вовсе
        "Linux Mint 21.3 Virginia [amd64] [2 x ISO]",
        "Some Show [TVRip] [720p]",
        "",
        "   ",
    ],
)
def test_pass_through(raw):
    assert convert(raw) is None


@pytest.mark.parametrize(
    "raw, expected",
    [
        # Strip Russian letters + Add RUS: кириллица выкинута, (ТВ-2) стало (S2), [12 из 12] стало E12 of 12
        (
            "(S2) / Shingeki no Kyojin Season 2 / Attack on Titan 2nd Season [TV] E12 of 12 "
            "[2017, BDRip 1080p, 60 FPS] AniLibria RUS",
            "Shingeki no Kyojin S02 [BDRip 1080p]",
        ),
        (
            "(S1) / Shingeki no Kyojin / Attack on Titan [TV] E25 of 25 [2013, BDRip 1080p, 60 FPS] AniDUB RUS",
            "Shingeki no Kyojin S01 [BDRip 1080p]",
        ),
        (
            "(S3) / Shingeki no Kyojin Season 3 / Attack on Titan 3rd Season [TV] E22 of 22 "
            "[2018, 2019, BDRip 1080p, 60 FPS] RUS",
            "Shingeki no Kyojin S03 [BDRip 1080p]",
        ),
        # (ТВ-4, часть 2) -> (S4, 2)
        (
            "(S4, 2) / Shingeki no Kyojin: The Final Season / Attack on Titan: 4th Season Part 2 [TV] E12 of 12 "
            "[2023, WEB-DL 1080p] RUS",
            "Shingeki no Kyojin: The Final Season S04 [WEB-DL 1080p]",
        ),
        # без Strip: S/E-замены Prowlarr есть всегда, кириллица на месте
        (
            "Атака Титанов (S2) / Shingeki no Kyojin Season 2 / Attack on Titan 2nd Season [TV] E12 of 12 "
            "[2017, приключения, триллер, фантастика, BDRip 1080p, 60 FPS] AniLibria",
            "Shingeki no Kyojin S02 [BDRip 1080p]",
        ),
        # онгоинг в форме Prowlarr
        (
            "Фрирен / Sousou no Frieren [TV] E17 of 28 [2023, WEB-DL] [1080p]",
            "Sousou no Frieren S01E01-E17 [WEB-DL 1080p]",
        ),
        ("Dandadan [TV] E1 of 12 [2024, WEB-DL 1080p] RUS", "Dandadan S01E01 [WEB-DL 1080p]"),
        # диапазон после Strip: "из" выкинуто
        (
            "Shingeki no Kyojin / Attack on Titan [TV] [1-25 25] [2013, BDRip] [1080p] RUS",
            "Shingeki no Kyojin S01 [BDRip 1080p]",
        ),
        ("Sousou no Frieren [TV] [1-17 28] [2023, WEB-DL] [1080p]", "Sousou no Frieren S01E01-E17 [WEB-DL 1080p]"),
        ("Shingeki no Kyojin [TV-3] [13-22 22] [2019, BDRip] [1080p]", "Shingeki no Kyojin S03E13-E22 [BDRip 1080p]"),
        # [ТВ-1] -> [S1], скобки [TV] нет
        (
            "Shingeki no Kyojin / Attack on Titan [S1] E25 of 25 [2013, BDRip 1080p] RUS",
            "Shingeki no Kyojin S01 [BDRip 1080p]",
        ),
        # (S2) внутри латинской части
        ("Shingeki no Kyojin (S2) / Attack on Titan [TV] E12 of 12 [2017, BDRip 1080p]", "Shingeki no Kyojin S02 [BDRip 1080p]"),
        # обычные сериалы после Prowlarr
        ("Twin Peaks S1E1-8 of 8 [1990, BDRip 1080p] RUS", "Twin Peaks S01 [BDRip 1080p]"),
        (
            "Stranger Things S4E1-7 of 9 [2022, WEB-DL 2160p HEVC HDR] RUS",
            "Stranger Things S04E01-E07 [WEB-DL 2160p x265]",
        ),
        ("Twin Peaks S2 E1-10 [1990, BDRip 1080p] RUS", "Twin Peaks S02E01-E10 [BDRip 1080p]"),
        # теги перенесены в конец (Move all tags to end)
        (
            "Shingeki no Kyojin Season 2 / Attack on Titan 2nd Season E12 of 12 [2017, BDRip 1080p] [TV]",
            "Shingeki no Kyojin S02 [BDRip 1080p]",
        ),
    ],
)
def test_prowlarr_processed_titles(raw, expected):
    assert convert(raw) == expected


def test_prowlarr_open_ended_long_runner():
    rel = parse_title("One Piece [TV] [1-1122 >1122] [1999, WEBRip] [1080p] RUS")
    assert rel.open_ended and rel.episode_count == 1122
    assert render(rel, SEASON) is None


def test_prowlarr_part_is_recorded():
    rel = parse_title("(S4, 2) / Shingeki no Kyojin: The Final Season [TV] E12 of 12 [2023, WEB-DL 1080p] RUS")
    assert (rel.season, rel.part, rel.first, rel.last) == (4, 2, 1, 12)


@pytest.mark.parametrize(
    "raw",
    [
        # фильм после Prowlarr: только год и качество, без серий
        "Kimi no Na wa [2016, BDRip 1080p] RUS",
        "Shingeki no Kyojin: The Last Attack / Attack on Titan: The Last Attack [Movie] [2024, BDRip] RUS",
        # оставшийся от шапки один маркер сезона без названия
        "(S2) [TV] E12 of 12 [2017, BDRip 1080p] RUS",
    ],
)
def test_prowlarr_pass_through(raw):
    assert convert(raw) is None


def test_long_runner_is_not_rewritten_by_default():
    raw = "Ван-Пис / One Piece [TV] [1-1122 из >1122] [RUS(int), JAP+Sub] [1999, приключения, WEBRip] [1080p]"
    rel = parse_title(raw)
    assert rel.open_ended and not rel.complete and rel.episode_count == 1122
    assert render(rel, SEASON) is None
    assert render(rel, RenderOptions(max_episodes=2000)) == "One Piece S01E01-E1122 [WEBRip 1080p]"


def test_range_style():
    raw = "Атака титанов / Shingeki no Kyojin [TV-1] [1-25 из 25] [2013, BDRip] [1080p]"
    assert convert(raw, RANGE) == "Shingeki no Kyojin S01E01-E25 [BDRip 1080p]"


def test_release_group_suffix():
    raw = "Атака титанов / Shingeki no Kyojin [TV-1] [1-25 из 25] [2013, BDRip] [1080p]"
    assert convert(raw, RenderOptions(release_group="RuTracker")) == "Shingeki no Kyojin S01 [BDRip 1080p]-RuTracker"


def test_title_pick():
    raw = "Атака титанов / Shingeki no Kyojin / Attack on Titan [TV-1] [1-25 из 25] [2013, BDRip] [1080p]"
    assert convert(raw) == "Shingeki no Kyojin S01 [BDRip 1080p]"
    assert convert(raw, title_pick="last") == "Attack on Titan S01 [BDRip 1080p]"


def test_parsed_fields():
    rel = parse_title(
        "Атака титанов (ТВ-3, часть 2) / Shingeki no Kyojin Season 3 Part 2 [TV-3 Part 2] [13-22 из 22] "
        "[RUS(int), JAP+Sub] [2019, BDRip] [1080p]"
    )
    assert rel.kind == "TV"
    assert (rel.season, rel.part) == (3, 2)
    assert (rel.first, rel.last, rel.total) == (13, 22, 22)
    assert rel.complete
    assert rel.languages == "RUS(int), JAP+Sub"
    assert (rel.source, rel.resolution) == ("BDRip", "1080p")


def test_no_episode_bracket_becomes_season_pack():
    assert convert("Берсерк / Berserk [TV] [RUS(int), JAP+Sub] [1997, DVDRip] [480p]") == "Berserk S01 [DVDRip 480p]"


def test_invalid_pack_style():
    with pytest.raises(ValueError):
        RenderOptions(pack_style="weird")
