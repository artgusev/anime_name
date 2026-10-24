# animename

Torznab-прокси между Prowlarr и Sonarr. Переписывает заголовки раздач RuTracker в вид,
который Sonarr умеет разбирать, не трогая ни Sonarr, ни Prowlarr.

```
Атака титанов / Shingeki no Kyojin [TV-1] [1-25 из 25] [RUS(int), JAP+Sub] [2013, приключения, BDRip] [1080p]
  -> Shingeki no Kyojin S01 [BDRip 1080p]

Фрирен, провожающая в последний путь / Sousou no Frieren [TV] [1-17 из 28] [2023, WEB-DL] [1080p]
  -> Sousou no Frieren S01E01-E17 [WEB-DL 1080p]

Твин Пикс / Twin Peaks / Сезон: 1 / Серии: 1-8 из 8 (Дэвид Линч) [1990, США, BDRip 1080p]
  -> Twin Peaks S01 [BDRip 1080p]
```

Без прокси Sonarr видит такие релизы как `Unknown Series` и молча их отбрасывает.

## Как это работает

```
Sonarr  --Torznab-->  animename  --Torznab-->  Prowlarr  -->  RuTracker
        <--  RSS с переписанными <title>  <--  RSS как есть
```

* **Запросы.** Sonarr добавляет к названию номер серии (`Shingeki no Kyojin 05`, `Title S01E05`,
  `Title (Season 2)`) и параметры `season`/`ep`. RuTracker по таким строкам ничего не находит,
  поэтому прокси отрезает хвост и не передаёт `season`/`ep` дальше. Фильтрацию по сериям
  Sonarr делает сам.
* **Дедупликация.** Sonarr перебирает все алиасы сериала: `Attack on Titan S2`,
  `Attack on Titan Season 2`, `Attack on Titan`. После очистки это один и тот же запрос, и
  ответ на него берётся из кэша (`CACHE_TTL`, по умолчанию 5 минут). RSS-запросы без `q`
  не кэшируются, чтобы не задерживать новинки. Заголовок ответа `X-Animename-Cache`
  показывает `HIT`, `MISS` или `SKIP`.
* **Пропуск.** Алиасы с TVDB на других языках (`Ataque de los Titanes`, `L'Attaque des Titans`)
  на RuTracker бесполезны. Регулярное выражение в `QUERY_SKIP` отсекает такие запросы:
  прокси сразу отвечает пустым RSS, не трогая Prowlarr.
* **Ответы.** В каждом `<item>` меняется только текст `<title>`. Всё остальное, включая `guid`
  и ссылки на скачивание, уходит в Sonarr байт в байт. Заголовки, которые не удалось
  распознать, остаются как были.
* **Скачивание.** Ссылки в ответах по-прежнему ведут в Prowlarr, Sonarr качает `.torrent`
  напрямую у него. Если Sonarr не видит Prowlarr по сети, задайте `PUBLIC_URL`, и ссылки
  будут переписаны на адрес прокси, который проксирует и `/download`.

Зависимостей нет: только стандартная библиотека Python 3.11+.

## Быстрый старт

1. Добавьте сервис в `docker-compose.yml` (см. `docker-compose.example.yml`):

   ```yaml
   services:
     animename:
       build: ./AnimeName
       environment:
         UPSTREAM_URL: http://prowlarr:9696
       restart: unless-stopped
   ```

2. Узнайте id индексера RuTracker в Prowlarr: откройте индексер, в поле Torznab URL будет
   `http://prowlarr:9696/<id>/`.

3. В Sonarr: Settings → Indexers → Add → **Torznab (Custom)**:

   | Поле | Значение |
   |---|---|
   | URL | `http://animename:8080/<id>` |
   | API Path | `/api` |
   | API Key | API-ключ **Prowlarr** |
   | Categories | `5070` (TV/Anime); при желании добавьте `5000` |
   | Anime Categories | `5070` |

4. Если Prowlarr сам синхронизирует RuTracker в Sonarr, отключите у этого индексера
   синхронизацию (Prowlarr → индексер → Sync Profile / теги), иначе релизы будут дублироваться.

## Настройки

Все настройки задаются переменными окружения.

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `UPSTREAM_URL` | `http://prowlarr:9696` | Адрес Prowlarr |
| `LISTEN_HOST` / `LISTEN_PORT` | `0.0.0.0` / `8080` | Где слушать |
| `OVERRIDES_FILE` | | TOML с правилами для отдельных тайтлов (см. ниже) |
| `PACK_STYLE` | `season` | Как подписывать полную раздачу: `season` → `S01`, `range` → `S01E01-E25` |
| `MAX_EPISODES` | `100` | Раздачи с бо́льшим числом серий не переписываются |
| `RELEASE_GROUP` | | Суффикс релиз-группы, например `RuTracker` → `...-RuTracker` |
| `TITLE_PICK` | `first` | Какую латинскую часть брать за название: `first` (обычно ромадзи) или `last` (обычно английское) |
| `FORWARD_SEASON` | `false` | Передавать ли `season`/`ep` в Prowlarr. Для аниме на RuTracker это мешает |
| `PUBLIC_URL` | | Адрес прокси, на который переписывать ссылки скачивания |
| `CACHE_TTL` | `300` | Сколько секунд хранить ответы на поисковые запросы с `q`. `0` выключает кэш |
| `CACHE_SIZE` | `256` | Сколько ответов держать в кэше, старые вытесняются |
| `QUERY_SKIP` | | Регулярное выражение без учёта регистра, например `Ataque\|Attaque\|attacco`. Запросы с таким `q` получают пустой RSS без обращения к Prowlarr |
| `LOG_LEVEL` | `INFO` | `DEBUG` покажет каждый проксируемый запрос и нераспознанные заголовки |
| `UPSTREAM_TIMEOUT` | `60` | Таймаут запроса к Prowlarr, секунды |

### Overrides

Для тайтлов, у которых нумерация RuTracker не совпадает с TVDB или у Sonarr нет нужного
алиаса, есть файл правил (`config/overrides.example.toml`):

```toml
[[override]]
match = "^One Piece$"      # регулярное выражение по очищенному латинскому названию
skip = true                # не переписывать вовсе

[[override]]
match = "^Shingeki no Kyojin"
title = "Attack on Titan"  # подставить это название
season = 4                 # и этот номер сезона
```

## Что именно делает парсер

* Название берётся из латинской части шапки `Русское / Latin [TV-1] ...`. Хвосты вроде
  `2nd Season`, `Season 2`, `II`, `Part 2` убираются, а номер сезона из них используется,
  если в скобке `[TV]` его нет. Год в скобках (`Hunter x Hunter (2011)`) сохраняется,
  режиссёр в скобках убирается.
* Сезон: `[TV-N]` → `N`; без номера → хвост названия → `1`.
* Серии: `[1-25 из 25]` и `[25 из 25]` → полная раздача; `[1-17 из 28]` → `E01-E17`;
  `[13-22 из 22]` → `E13-E22`; `[1-1122 из >1122]` → онгоинг без конца, при превышении
  `MAX_EPISODES` не переписывается.
* Качество: источник (`BDRip`, `BluRay Remux`, `WEB-DL`, `WEBRip`, `HDTV`, `DVDRip`),
  разрешение (`1080p`, `1920x1080` → `1080p`, при нескольких берётся максимальное),
  кодек (`x264`, `x265`, `AV1`) и `10bit`.
* Языковые теги (`[RUS(int), JAP+Sub]`) в новый заголовок не попадают. Sonarr v4 в этом
  случае подставляет язык оригинала сериала.
* `[Movie]`, `[OVA]`, `[ONA]`, `[Special]` не переписываются: Sonarr не сопоставит их с сериями.

## Ограничения

* Номер `[TV-N]` на RuTracker не всегда равен номеру сезона на TVDB (разбиение на части,
  перезапуски, длинные онгоинги вроде One Piece или Naruto). Для таких сериалов нужны
  overrides, иначе Sonarr может взять не ту раздачу. `MAX_EPISODES` ограничивает ущерб.
* Если файлы внутри торрента названы по-русски, Sonarr может не разобрать их при импорте.
  Это за пределами прокси.

## CLI

Проверить, во что превратится заголовок, можно без запуска сервера:

```bash
animename convert "Атака титанов / Shingeki no Kyojin [TV-1] [1-25 из 25] [2013, BDRip] [1080p]"
```

```bash
animename convert --json --overrides config/overrides.toml < titles.txt
```

Запуск сервера без Docker:

```bash
UPSTREAM_URL=http://localhost:9696 animename serve --port 8080 --query-skip "Ataque|Attaque"
```

## Разработка

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]" && .venv/bin/pytest
```
