# osm-polygon-to-wikipedia-articles

Takes OSM polygons as input and retrieves Wikipedia articles related to them.

Data synced via Hugging Face bucket: `hf://buckets/NoeFlandre/osm-polygon-to-wikipedia-articles`

## Status

Sampling layer only — next step is Wikipedia geosearch + article retrieval.

## Layout

```
src/osm_polygon_to_wikipedia_articles/
├── polygons/           # Stage 1: load + sample OSM polygons
│   ├── load.py         #   list_countries, load_country (HF I/O)
│   └── sample.py       #   sample_polygons, build_sample (pure functions)
└── wikipedia/          # Stage 2 (TODO): match polygons to Wikipedia articles

scripts/
└── sample.py           # CLI wrapper

data/
└── samples/            # gitignored, sampled parquet files
    └── tiny.parquet    # 15 polygons from Liechtenstein for experimentation

tests/
└── fixtures/           # gitignored? tiny real-data fixtures
```

## Usage

Sample polygons:

```bash
uv run python scripts/sample.py --countries liechtenstein --n 15 --out data/samples/tiny.parquet
```

## Tests

```bash
uv run pytest
```