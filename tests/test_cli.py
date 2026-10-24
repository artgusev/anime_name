import json

from animename.cli import main

AOT = "Атака титанов / Shingeki no Kyojin [TV-1] [1-25 из 25] [2013, BDRip] [1080p]"


def test_convert_prints_rewritten(capsys):
    assert main(["convert", AOT, "Ubuntu 24.04 [amd64]"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out == ["Shingeki no Kyojin S01 [BDRip 1080p]", "Ubuntu 24.04 [amd64]"]


def test_convert_reads_stdin(capsys, monkeypatch):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(AOT + "\n\n"))
    main(["convert", "--pack-style", "range"])
    assert capsys.readouterr().out.strip() == "Shingeki no Kyojin S01E01-E25 [BDRip 1080p]"


def test_convert_json(capsys):
    main(["convert", "--json", AOT])
    payload = json.loads(capsys.readouterr().out)
    assert payload["rewritten"] is True
    assert payload["sonarr"] == "Shingeki no Kyojin S01 [BDRip 1080p]"
    assert payload["release"]["title"] == "Shingeki no Kyojin"
    assert payload["release"]["complete"] is True


def test_convert_with_overrides_file(capsys, tmp_path):
    path = tmp_path / "o.toml"
    path.write_text('[[override]]\nmatch = "Shingeki"\ntitle = "Attack on Titan"\n', encoding="utf-8")
    main(["convert", "--overrides", str(path), AOT])
    assert capsys.readouterr().out.strip() == "Attack on Titan S01 [BDRip 1080p]"
