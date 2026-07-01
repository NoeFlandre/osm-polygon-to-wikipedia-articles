# Module map

The `osm_polygon_to_wikipedia_articles` package has two top-level
subpackages: `polygons` (raw data layer) and `wikipedia` (matching +
publication layer). The `wikipedia` subpackage grew to ~20 flat modules
during dataset construction; it is now organised into five
sub-subpackages, each with a single responsibility.

```
src/osm_polygon_to_wikipedia_articles/
├── __init__.py
├── polygons/                            # raw data layer
│   ├── __init__.py
│   ├── load.py                          # list_countries / load_country (HF)
│   ├── sample.py                        # sample_polygons / build_sample
│   └── geometry.py                      # geometry_wkt helpers
└── wikipedia/                           # matching + publication layer
    ├── __init__.py                      # back-compat re-export hub
    ├── fetch/                           # HTTP layer
    │   ├── __init__.py
    │   ├── _retry.py                    #   get_json_with_retry
    │   ├── http_client.py               #   fetch_wikidata_sitelinks (single QID)
    │   ├── batched_sitelinks.py         #   fetch_sitelinks_batched (≤50 QIDs/req)
    │   ├── summary.py                   #   fetch_summary (REST /page/summary)
    │   └── extracts.py                  #   fetch_extract (plain-text body)
    ├── pipeline/                        # pure logic + orchestrator
    │   ├── __init__.py
    │   ├── types.py                     #   MatchResult / ArticleSummary / WikidataArticle
    │   ├── wikidata.py                  #   pure: extract QID / filter / resolve
    │   ├── match.py                     #   match_polygons orchestrator (concurrent, resumable)
    │   ├── thumbnail.py                 #   is_svg_url + add_thumbnail_columns
    │   └── union.py                     #   union_jsonls
    ├── visualization/                   # folium maps + PNG renderer
    │   ├── __init__.py
    │   ├── map.py                       #   build_map (centroid markers)
    │   ├── geomap.py                    #   build_polygon_map (polygon outlines)
    │   └── render.py                    #   render_map_png (headless Chrome)
    ├── layout/                          # canonical 4-subfolder dataset layout
    │   ├── __init__.py
    │   ├── full_layout.py               #   builders: build_all_europe, sample_map, manifest, metadata
    │   ├── migrate_full_layout.py       #   copy legacy flat → new layout
    │   ├── delete_legacy.py             #   safe-delete local duplicates
    │   └── delete_hf_duplicates.py      #   safe-delete HF root duplicates
    └── orchestration/                   # per-country end-to-end driver
        ├── __init__.py
        └── process_countries.py         #   process_one_country / process_all
```

## Public API per subpackage

### `wikipedia.fetch` — HTTP layer

The only place in the codebase that does I/O. Every fetching function
is injectable (its network call is hidden behind a `_get` or `urlopen`
parameter) so tests can swap in a fake.

| Symbol | Purpose |
| ------ | ------- |
| `get_json_with_retry(url, ...)` | urllib JSON GET with retry-on-transient-error |
| `fetch_wikidata_sitelinks(qid)` | per-QID `wbgetentities` → sitelinks dict |
| `fetch_sitelinks_batched(qids, batch_size=50, ...)` | batched (≤50 QIDs/request) variant |
| `fetch_summary(lang, title)` | Wikipedia REST `/page/summary` |
| `fetch_extract(lang, title)` | Wikipedia `?prop=extracts&explaintext` plain-text body |

### `wikipedia.pipeline` — pure logic + orchestrator

I/O-free. `types` is dataclasses; `wikidata`/`thumbnail`/`union` are
pure; `match` is an orchestrator that takes its HTTP fetchers as
callables (see `wikipedia.fetch`).

| Symbol | Purpose |
| ------ | ------- |
| `MatchResult`, `ArticleSummary`, `WikidataArticle` | dataclasses |
| `extract_wikidata_qid(tags)` | parse `wikidata=Q<id>` from a tags list |
| `filter_polygons_with_wikidata(df)` | polars filter — keep rows with valid QID |
| `resolve_wikidata_to_article(qid, lang, *, sitelinks)` | pure: sitelinks → article |
| `match_polygons(df, ...)` | the orchestrator; concurrent + resumable |
| `is_svg_url(url)` | detect `.svg` / `.svg.png` thumbnail convention |
| `add_thumbnail_columns(df)` | attach `thumbnail_is_svg` column |
| `union_jsonls(jsonls, out_parquet)` | concat per-country JSONLs into one parquet |

### `wikipedia.visualization` — folium maps + PNG renderer

Three layers, increasing fidelity:

| Symbol | Purpose |
| ------ | ------- |
| `build_map(df, out_path)` | one CircleMarker per polygon, colored by country |
| `build_polygon_map(df, out_path)` | one GeoJson polygon per row, drawing real outlines |
| `render_map_png(html_path, png_path, ...)` | headless Chrome screenshot |

### `wikipedia.layout` — canonical 4-subfolder dataset layout

Owns the published dataset structure:

```
samples/
├── README.md / manifest / metadata
├── per_country/<slug>/<slug>.parquet  (46 country folders)
├── combined/all_europe.parquet         (single union)
├── sample/sample_map.jsonl             (small JSONL)
└── preview/map_preview.{png,html}      (static map)
```

| Symbol | Purpose |
| ------ | ------- |
| `RootPaths` / `CountryPaths` / `CombinedPaths` / `SamplePaths` / `PreviewPaths` | frozen dataclasses |
| `*_paths_for(samples_root, ...)` | path factories |
| `build_all_europe(samples_root)` | build `combined/all_europe.parquet` |
| `build_sample_map(samples_root, target_n=4204, seed=42)` | build `sample/sample_map.jsonl` |
| `write_manifest_json(samples_root, ...)` | write the structural fingerprint |
| `build_metadata_json(...)` | render the schema docs JSON |
| `migrate_to_full_layout(samples_root)` | copy legacy flat → new (no deletes) |
| `safe_delete_audited(samples_root, *, dry_run=False)` | survey + delete local duplicates |
| `classify_hf_file(filename)` | map legacy HF root filename → canonic destination |
| `is_safe_to_delete_hf_root_file(root, canonic)` | byte/row-equality check |

### `wikipedia.orchestration` — per-country end-to-end driver

Drives the full sample → match → validate → push loop for one country
at a time. Heavy intermediate files live under `OSM_DATA_ROOT`; slim
outputs get copied into `./data/samples/`.

| Symbol | Purpose |
| ------ | ------- |
| `CountryPlan` / `ValidationReport` | dataclasses |
| `discover_countries_with_wikidata(...)` | scan disk for source countries with `wikidata=*` |
| `plan_country_run(country, data_root, samples_root)` | build the path plan |
| `validate_country_outputs(plan)` | check parquet/jsonl/map correctness |
| `process_one_country(plan, ...)` | one-country end-to-end |
| `process_all(data_root, samples_root, hf_repo, ...)` | every country end-to-end |

## Back-compat shims

For each of the original top-level `wikipedia/` module paths, a thin
shim file is left in place. Each shim is two lines of substance:

```python
from .<subpackage>.<module> import *  # noqa: F401, F403
```

so legacy imports such as
`from osm_polygon_to_wikipedia_articles.wikipedia.match import match_polygons`
keep working. New code is encouraged to import from the subpackage
directly:

```python
from osm_polygon_to_wikipedia_articles.wikipedia.pipeline import match_polygons
```

The shim files are kept for a soft deprecation period; they can be
removed once all scripts (and any external consumers) have been
migrated.

## Scripts

All `scripts/*.py` continue to work unchanged because the back-compat
shims preserve the old import paths. New scripts should import from
the subpackages directly.
