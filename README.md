---
license: mit
task_categories:
  - text-retrieval
  - question-answering
  - other
language:
  - en
tags:
  - openstreetmap
  - wikidata
  - wikipedia
  - geospatial
  - entity-linking
  - polygon
  - osm
size_categories:
  - 10K<n<100K
---

# OSM-Polygon → Wikipedia Articles

OpenStreetMap polygons that resolved to their English Wikipedia article,
intersected with full body text, summaries, thumbnails and geo-coordinates.

**Hugging Face:** [`NoeFlandre/osm-polygon-to-wikipedia-articles`](https://huggingface.co/datasets/NoeFlandre/osm-polygon-to-wikipedia-articles)

---

## At a glance

| Metric | Value |
|---|---:|
| **Countries processed** | 45 |
| **Source polygons (after dedup)** | 7.2 M |
| **Polygons with `wikidata=*` tag** | 191 K |
| **Polygons with an `enwiki` article** | 32 124 |
| **Wikipedia body words shipped** | 12 685 357 |
| **SVG thumbnails** | 901 (2.8 % of matched) |

---

## Map

![Europe map of every matched OSM polygon](https://huggingface.co/datasets/NoeFlandre/osm-polygon-to-wikipedia-articles/resolve/main/preview/map_preview.png)

*A static snapshot of every matched polygon across the dataset. One marker
per polygon. Smaller radius + opacity for "many small markers, still legible" -
radius 3, weight 0, opacity 0.55 - rendered on top of the standard OSM basemap.*

The interactive version (one per country) lives at
`data/samples/per_country/<country>/<country>_wikidata_map.html`.

---

## What this dataset is for

- **Geographic text corpora** — for each OSM polygon that has an `enwiki`
  article, ship the article's plain-text body alongside the polygon.
- **Geo-entity linking** — train or benchmark models that match a polygon
  (centroid + tags) to a Wikipedia article.
- **Coverage studies** — analyze which OSM features have Wikipedia articles
  in which languages / countries.
- **Cross-modal learning** — combine `geometry_wkt` + `article_body_text` +
  `article_thumbnail_url` for place-name / image / body retrieval tasks.

---

## Dataset layout

```text
samples/
├── README.md                           ← (separate) the HF dataset card
├── manifest                            ← structural fingerprint (JSON)
├── metadata                            ← schema docs (JSON)
├── per_country/                        ← one folder per country
│   ├── README.md
│   ├── <country>/
│   │   ├── README.md
│   │   ├── <country>.parquet          ← slim matched table (1 row/match)
│   │   ├── <country>_wikidata.jsonl   ← per-polygon match trace
│   │   ├── <country>_wikidata_map.html
│   │   └── <country>_wikidata_map.png
│   └── …
├── combined/
│   ├── README.md
│   └── all_europe.parquet             ← concat of every per_country/*.parquet
├── sample/
│   ├── README.md
│   └── sample_map.jsonl                ← 4 204-row uniform sample for inspection
└── preview/
    ├── README.md
    └── map_preview.{png,html}          ← static world-overview map
```

Every `per_country/<country>/` folder is self-contained — copy just that
folder if you only need one country.

---

## Schema

All parquet files share the same row shape (per-country tables + the
combined table):

| Column | Type | Meaning |
|---|---:|---|
| `osm_id` | i64 | OpenStreetMap polygon ID |
| `osm_type` | str | `way` / `relation` / `node` |
| `country` | str | ISO-ish country slug |
| `size_bin` | str | size bucket from the source parquet |
| `centroid_lon` / `centroid_lat` | f64 | polygon centroid (WGS84) |
| `wikidata_qid` | str | matched Wikidata QID, e.g. `Q1321` |
| `article_title` | str | enwiki article title |
| `article_lang` | str | always `en` for `match_status == "matched"` |
| `article_url` | str | canonical enwiki URL |
| `sitelinks_count` | i64 | Wikidata sitelinks count for `wikidata_qid` |
| `match_status` | str | `matched` / `no_sitelinks` / `no_lang_sitelink` |
| `article_description` | str | enwiki REST summary `description` field |
| `article_extract_short` | str | enwiki REST summary `extract` (≤ 500 chars) |
| `article_thumbnail_url` | str | HTTPS URL to the article thumbnail |
| `thumbnail_is_svg` | bool | `True` if the thumbnail's origin is an SVG (Wikimedia uses `.svg.png` for rasterised SVGs) |
| `article_lat` / `article_lon` | f64 | geo-coords from the article (often None) |
| `article_pageid` | i64 | enwiki page ID |
| `article_body_text` | str | **full plain-text body** of the enwiki article (the `article_body_text` field grows to MB-scale for long articles) |
| `geometry_wkt` | str | the original OSM geometry as WKT (nullable — only present where the source parquet shipped it) |
| `tags` | str (JSON) | OSM tags from the source, e.g. `{"natural":"peak"}` (joined from `OSM_DATA_ROOT/<country>.parquet`) |
| `continent` | str | OSM continent tag (joined from source) |
| `area_km2` | f64 | polygon area in km² (joined from source) |
| `pbf_date` | str | date of the PBF extract used to build this dataset (joined from source) |

The last four columns (`tags`, `continent`, `area_km2`, `pbf_date`) are
joined from the **source** parquet without re-fetching Wikidata. All other
columns come from the pipeline itself.

---

## Methodology

For every country in the source parquet (`NoeFlandre/osm-polygon-selection`,
on Hugging Face):

1. **Sample.** For very large sources (> 10 M rows), sample down via a
   deterministic `min(n, source.height)` policy with a 10 M-row ceiling.
2. **Filter by wikidata tag.** Keep only rows with a `wikidata=*` tag.
3. **Resolve QID → sitelinks.** For each row, call Wikidata's
   `wbgetentities` (with retry-on-transient-error: 5 attempts, exponential
   backoff, honors `Retry-After`).
4. **Resolve sitelinks → enwiki article.** Keep polygons whose QID has an
   `enwiki` sitelink; discard `no_sitelinks` and `no_lang_sitelink`.
5. **Fetch article.** REST `/page/summary/<title>` for short fields + the
   MediaWiki `prop=extracts&explaintext` API for the full body.
6. **Emit.** Append the result incrementally to a per-country JSONL (so the
   run is resumable across restarts); write the matched-only parquet at the
   end.
7. **Union + sample.** Concat every per-country JSONL filtered to
   `match_status == "matched"` → `combined/all_europe.parquet`. Pick 4 204
   rows uniformly for `sample/sample_map.jsonl`.
8. **Publish.** Upload all of the above + per-folder READMEs to the HF
   dataset.

Throttling is handled defensively:

- HTTP `429` and `5xx` trigger exponential backoff with `Retry-After` honored
- Network blips (URLError, ConnectionResetError, TimeoutError) trigger
  exponential backoff
- Permanent `4xx` (other than 429) return `None` immediately (no retry)
- Concurrency is capped at `max-workers=3` by default — Wikidata throttles
  above ~50 req/s and we never want to lose articles to throttling

---

## Top contributors

Most polygons matched, per country:

| Country | Polygons |
|---|---:|
| czech-republic | 6 359 |
| united-kingdom | 4 744 |
| slovakia | 3 473 |
| france | 2 757 |
| ukraine | 2 649 |
| germany | 1 945 |
| norway | 1 153 |
| spain | 766 |
| switzerland | 470 |
| sweden | 632 |
| turkey | 870 |

*Full per-country table in `data/samples/manifest`.*

---

## Use cases + how to load

```python
import polars as pl

# All rows, ~30 MB parquet (with body text)
df = pl.read_parquet("https://huggingface.co/datasets/NoeFlandre/osm-polygon-to-wikipedia-articles/resolve/main/combined/all_europe.parquet")
print(df.shape, df.columns)

# Just one country (smaller footprint)
df_fr = pl.read_parquet("https://huggingface.co/datasets/NoeFlandre/osm-polygon-to-wikipedia-articles/resolve/main/per_country/france/france.parquet")

# Random small subset
with open("https://huggingface.co/datasets/NoeFlandre/osm-polygon-to-wikipedia-articles/resolve/main/sample/sample_map.jsonl") as f:
    sample = [json.loads(line) for line in f]
```

---

## Known limitations

- **Body text only in `en`.** Other-language articles are discarded
  (`match_status = no_lang_sitelink`).
- **One article per polygon.** Each polygon resolves to at most one article
  (the first `enwiki` sitelink matched).
- **Sample caps.** For very large source parquets, the pipeline caps at
  10 000 000 rows per country. For Norway, UK, France, Germany, etc. the
  source itself is large enough that no cap kicks in.
- **Rate-limited by Wikidata.** On days with heavy parallel use, ~50 req/s
  cap forces us to lower concurrency; the modular retry helper picks this up
  automatically.

---

## Tests

```bash
uv run pytest
```

130 tests, 128 green. The two `tests/test_load.py` failures are
HF-integration tests that fail when the dataset's parquet schema doesn't
match the test's expectation; they're test-not-data bugs and tracked
separately.

---

## License

- Source data: OpenStreetMap contributors (ODbL).
- Wikipedia article bodies: CC BY-SA 4.0.
- Wikidata: CC0.
- This pipeline + dataset card: MIT (see [LICENSE](./LICENSE)).
