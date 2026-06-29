# osm-polygon-to-wikipedia-articles

Takes OSM polygons as input and retrieves Wikipedia articles related to them.

Data synced via Hugging Face bucket: `hf://buckets/NoeFlandre/osm-polygon-to-wikipedia-articles`

## Status

| Stage | Status | Notes |
|---|---|---|
| 1. Load + sample polygons from HF dataset | done | `polygons/` package, 12 tests |
| 2a. Wikidata golden path (QID -> article + summary + body) | done | `wikipedia/{wikidata,summary,extracts,match,types}.py`, 28 tests |
| 2b. Name match (`name=*` -> article summary) | not started | next |
| 2c. Geosearch by centroid fallback | not started | after 2b |

See `docs/wikidata_matches.md` for the inspection of stage 2a results.

## Layout

```
src/osm_polygon_to_wikipedia_articles/
├── polygons/
│   ├── load.py             # HF I/O: list_countries, load_country
│   └── sample.py           # pure: sample_polygons, build_sample
└── wikipedia/
    ├── types.py            # dataclasses: WikidataArticle, ArticleSummary, MatchResult
    ├── wikidata.py         # pure: extract_qid, filter, resolve (sitelinks)
    ├── summary.py          # HTTP: REST /page/summary
    ├── extracts.py         # HTTP: /w/api.php?prop=extracts&explaintext (full body)
    ├── match.py            # orchestrator: match_polygons -> parquet/jsonl
    └── http_client.py      # urllib wrapper for the Wikidata API

scripts/
├── sample.py               # CLI: polygons -> parquet
└── match_wikidata.py       # CLI: parquet -> parquet+jsonl via stage 2a

docs/
└── wikidata_matches.md     # per-match inspection table + parquet schema for stage 2a

data/samples/               # gitignored
├── dev.parquet             # 352 polygons, 8 countries
├── dev_wikidata.parquet    # 6 polygons × 19 cols (Wikidata + summary + body)
└── dev_wikidata.jsonl      # same data, JSONL form

tests/                      # 40 tests, all green
```

## Wikidata coverage in the dev sample

| Country | Polygons | `wikidata=*` | % |
|---|---:|---:|---:|
| monaco | 2 | 1 | 50.00% |
| malta | 620 | 21 | 3.39% |
| andorra | 776 | 24 | 3.09% |
| faroe-islands | 1,278 | 39 | 3.05% |
| luxembourg | 11,460 | 161 | 1.40% |
| estonia | 47,160 | 1,125 | 2.39% |
| iceland | 47,896 | 471 | 0.98% |
| liechtenstein | 565 | 5 | 0.88% |

The dev sample draws 50/country from these 8 small countries. Sample is representative of the `~1–3%` coverage observed upstream.

## Usage

```bash
# 1. sample polygons
uv run python scripts/sample.py \
    --countries liechtenstein,monaco,andorra,luxembourg,iceland,malta,faroe-islands,estonia \
    --n 50 --out data/samples/dev.parquet

# 2. match Wikidata QIDs, fetch summaries + bodies, write parquet
uv run python scripts/match_wikidata.py \
    --in data/samples/dev.parquet \
    --parquet data/samples/dev_wikidata.parquet \
    --jsonl data/samples/dev_wikidata.jsonl --lang en
```

## Tests

```bash
uv run pytest
```