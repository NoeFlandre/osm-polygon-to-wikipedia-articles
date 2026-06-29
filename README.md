# osm-polygon-to-wikipedia-articles

Takes OSM polygons as input and retrieves Wikipedia articles related to them.

Data synced via Hugging Face bucket: `hf://buckets/NoeFlandre/osm-polygon-to-wikipedia-articles`

## Status

Sampling layer only. Pipeline:

1. `osm_polygon_to_wikipedia_articles.load` — `list_countries()`, `load_country(slug)` over the [`NoeFlandre/osm-polygon-selection`](https://huggingface.co/datasets/NoeFlandre/osm-polygon-selection) dataset.
2. `osm_polygon_to_wikipedia_articles.sample` — `sample_polygons(df, n, seed, stratify_by)` and `build_sample(countries, n_per_country, seed, out_path)`.

## Usage

```bash
uv run python scripts/sample.py --countries liechtenstein,monaco --n 20 --out data/sample.parquet
```

## Tests

```bash
uv run pytest
```