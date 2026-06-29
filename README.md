# osm-polygon-to-wikipedia-articles

Takes OSM polygons as input and retrieves Wikipedia articles related to them.

Data synced via Hugging Face bucket: `hf://buckets/NoeFlandre/osm-polygon-to-wikipedia-articles`

## Status

- **Stage 1 (polygons)**: load + sample from the [`NoeFlandre/osm-polygon-selection`](https://huggingface.co/datasets/NoeFlandre/osm-polygon-selection) dataset.
- **Stage 2 (Wikipedia match — partial)**: Wikidata golden path implemented. Name match and geosearch not yet started.

## Layout

```
src/osm_polygon_to_wikipedia_articles/
├── polygons/
│   ├── load.py             # list_countries, load_country (HF I/O)
│   └── sample.py           # sample_polygons, build_sample (pure)
└── wikipedia/
    ├── wikidata.py         # extract/resolve Wikidata QID -> Wikipedia article
    └── http_client.py      # thin urllib wrappers for Wikidata + Wikipedia REST

scripts/
├── sample.py               # sample polygons -> parquet
└── match_wikidata.py       # resolve Wikidata QIDs in a sample -> jsonl

data/samples/               # gitignored, local samples + match outputs
├── dev.parquet             # 352 polygons across 8 countries (50 each, monaco=2)
└── dev_wikidata.jsonl      # 6 matches: 5 matched + 1 no en sitelink
```

## Wikidata coverage

Across 8 small countries in the dataset:

| Country | Polygons | with `wikidata=*` | % |
|---|---:|---:|---:|
| monaco | 2 | 1 | 50.00% |
| malta | 620 | 21 | 3.39% |
| andorra | 776 | 24 | 3.09% |
| faroe-islands | 1,278 | 39 | 3.05% |
| luxembourg | 11,460 | 161 | 1.40% |
| estonia | 47,160 | 1,125 | 2.39% |
| iceland | 47,896 | 471 | 0.98% |
| liechtenstein | 565 | 5 | 0.88% |

When the tag is present it gives an exact, unambiguous match (e.g. `wikidata=Q1741199` → "Kihnu" Estonian island).

## Usage

Sample polygons:

```bash
uv run python scripts/sample.py \
    --countries liechtenstein,monaco,andorra,luxembourg,iceland,malta,faroe-islands,estonia \
    --n 50 --out data/samples/dev.parquet
```

Resolve Wikidata QIDs to Wikipedia article titles:

```bash
uv run python scripts/match_wikidata.py \
    --in data/samples/dev.parquet \
    --out data/samples/dev_wikidata.jsonl --lang en
```

## Tests

```bash
uv run pytest
```