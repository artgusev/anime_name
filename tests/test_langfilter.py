import pytest

from animename.langfilter import QueryFilter, detect_language, parse_languages


@pytest.mark.parametrize(
    "query, lang",
    [
        # английский и ромадзи
        ("Attack on Titan", "en"),
        ("Shingeki no Kyojin", "en"),
        ("Shingeki no Kyōjin", "en"),
        ("Kimi no Na wa", "en"),
        ("Isekai de Cheat Skill", "en"),
        ("Uma Musume Pretty Derby", "en"),
        ("UN-GO", "en"),
        ("Non Non Biyori", "en"),
        ("Pokémon", "en"),
        ("Da Vincis Demons", "en"),
        ("Legend of the Galactic Heroes: Die Neue These", "en"),
        ("El Hazard: The Magnificent World", "en"),
        ("NCIS: Los Angeles", "en"),
        ("Fear the Walking Dead", "en"),
        ("No Game No Life", "en"),
        ("That Time I Got Reincarnated as a Slime", "en"),
        # русский
        ("Атака титанов", "ru"),
        ("Клинок, рассекающий демонов", "ru"),
        # романские и германские
        ("Ataque de los Titanes", "es"),
        ("Ataque a los Titanes", "es"),
        ("Ataque a los Titanes 2013", "es"),
        ("Guardianes de la Noche", "es"),
        ("No es la vida", "es"),
        ("LAttaque des Titans", "fr"),
        ("Les Aventures de Tintin", "fr"),
        ("Attacco dei Giganti", "it"),
        ("Il Sole Penetra le Illusioni", "it"),
        ("Der Angriff der Titanen", "de"),
        ("Die Abenteuer von Tim und Struppi", "de"),
        ("Ataque dos Titãs", "pt"),
        # другая кириллица
        ("Атака титанів", "uk"),
        ("Напад титана на љубав", "sr"),
        # другие алфавиты
        ("進撃の巨人", "ja"),
        ("进击的巨人", "zh"),
        ("진격의 거인", "ko"),
        ("Επίθεση των Τιτάνων", "el"),
        ("هجوم العمالقة", "ar"),
        # без букв
        ("86", "none"),
        ("", "none"),
    ],
)
def test_detect_language(query, lang):
    assert detect_language(query) == lang


def test_parse_languages():
    assert parse_languages("ru,en") == frozenset({"ru", "en"})
    assert parse_languages(" RU en ") == frozenset({"ru", "en"})
    assert parse_languages("any") is None
    assert parse_languages("ru,all") is None
    assert parse_languages("") is None
    assert parse_languages(None) is None


def test_filter_default_allows_ru_en_and_digits():
    qf = QueryFilter.build()
    for q in ("Attack on Titan", "Shingeki no Kyojin", "Атака титанов", "86"):
        assert qf.reason(q) is None, q


def test_filter_rejects_other_languages_with_reason():
    qf = QueryFilter.build()
    assert qf.reason("Ataque de los Titanes") == "language=es not in en,ru"
    assert qf.reason("進撃の巨人") == "language=ja not in en,ru"
    assert qf.reason("Атака титанів") == "language=uk not in en,ru"


def test_filter_custom_languages():
    qf = QueryFilter.build("ru")
    assert qf.reason("Attack on Titan") == "language=en not in ru"
    assert qf.reason("Атака титанов") is None
    assert QueryFilter.build("any").reason("進撃の巨人") is None
    assert not QueryFilter.build("any").active


def test_filter_skip_and_allow():
    qf = QueryFilter.build("ru,en", skip="^Attack on Titan$", allow="Chevalier|Titanes")
    assert qf.reason("Attack on Titan") == "QUERY_SKIP"
    # allow обходит фильтр языков
    assert qf.reason("Le Chevalier DEon") is None
    assert qf.reason("Ataque de los Titanes") is None
    assert qf.reason("LAttaque des Titans") == "language=fr not in en,ru"
    # явный запрет сильнее allow
    assert QueryFilter.build(skip="Titan", allow="Titan").reason("Attack on Titan") == "QUERY_SKIP"


def test_filter_invalid_regex():
    with pytest.raises(ValueError, match="QUERY_SKIP"):
        QueryFilter.build(skip="(")
    with pytest.raises(ValueError, match="QUERY_ALLOW"):
        QueryFilter.build(allow="[")
