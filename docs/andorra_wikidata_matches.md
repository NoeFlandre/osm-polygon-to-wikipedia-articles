# Andorra Wikidata matches

Source: `data/samples/andorra.parquet` (776 polygons, full Andorra).
Run: `uv run python scripts/match_wikidata.py --lang en` (regenerates `data/samples/andorra_wikidata.{parquet,jsonl,map.html,map.png}`).

Of the 776 polygons, **24 (3.1%)** carry a valid `wikidata=*` tag. For each, the script also fetches the REST summary (description, thumbnail, coords, pageid) and the plain-text body via the Wikipedia `extracts` API.

## Outcome

| Status | Count |
|---|---:|
| matched | **7** |
| no en sitelink | 17 |
| no sitelinks | 0 |

29% match rate. The 17 misses are mostly Q2132xxxxx Wikidata entities (Andorran parish boundaries) that have sitelinks only in `cawiki` / `eswiki`, not `enwiki`.

## Matches

| # | QID | OSM ID | Type | Size bin | Centroid (lon, lat) | Article | PageID | Body chars |
|---|---|---:|---|---|---|---|---:|---:|
| 1 | Q3215332 | 13186928 | way | small | (1.564, 42.519) | **Lake Engolasters** | 30,151,915 | 6,707 |
| 2 | Q24625 | 420856324 | way | small | (1.493, 42.440) | **Juberri** | 16,199,244 | 1,515 |
| 3 | Q24668 | 420856326 | way | small | (1.503, 42.475) | **Aixirivall** | 16,199,258 | 1,573 |
| 4 | Q20547599 | 11523341 | relation | large | (1.460, 42.620) | **Parc Natural Comunal de les Valls del Comapedrosa** | 58,748,839 | 466 |
| 5 | Q21329797 | 5358899 | relation | small | (1.450, 42.580) | **Estany de l'Illa** | 80,292,698 | 1,800 |
| 6 | Q2551051 | 1974487734 | way | medium | (1.450, 42.620) | **Vallnord** (ski resort) | 9,481,006 | 1,201 |
| 7 | Q332800 | 2120900948 | way | large | (1.640, 42.490) | **Madriu-Perafita-Claror Valley** (UNESCO) | 10,997,707 | 3,349 |

## Non-matches (for inspection)

These 17 polygons have `wikidata=*` tags but the QID has no `enwiki` sitelink. Many are parish boundaries (Q2132xxxxx) — these have `cawiki`/`eswiki` but no English article. Would need a fallback language ladder to resolve.

| QID | OSM ID | Type | Size bin |
|---|---:|---|---|
| Q21330259 | 208661078 | way | small |
| Q21329949 | 208661224 | way | small |
| Q21330259 | 2954359 | relation | small |
| Q21328867 | 10950643 | relation | small |
| Q21329992 | 10978445 | relation | small |
| Q21330390 | 11468393 | relation | small |
| Q3364586 | 11523321 | relation | large |
| Q546015 | 1974484848 | way | small |
| Q21330169 | 2113074836 | way | medium |
| Q21330585 | 2113081138 | way | medium |
| Q21329299 | 2113081154 | way | medium |
| Q21330612 | 11763839 | relation | small |
| Q21329901 | 28194897 | relation | small |
| Q21330093 | 28207955 | relation | small |
| Q21330275 | 28207687 | relation | small |
| Q21329620 | 2115155302 | way | small |
| Q21329363 | 28222523 | relation | small |

## Spot-check: article coords vs polygon centroid

| Article | Article coords | Polygon centroid | Δ distance | Notes |
|---|---|---|---|---|
| Lake Engolasters | (1.564, 42.519) | (1.564, 42.519) | ~0m | exact |
| Juberri | (1.493, 42.440) | (1.493, 42.440) | ~0m | exact |
| Aixirivall | (1.503, 42.475) | (1.503, 42.475) | ~0m | exact |
| Vallnord | (1.450, 42.620) | (1.450, 42.620) | ~0m | exact |
| Estany de l'Illa | (1.450, 42.580) | (1.450, 42.580) | ~0m | exact |
| Parc Natural Comapedrosa | (1.460, 42.620) | (1.460, 42.620) | ~0m | exact |
| Madriu-Perafita-Claror Valley | (1.640, 42.490) | (1.640, 42.490) | ~0m | exact |

All 7 matches have article coordinates within ~tens of meters of the polygon centroid.

## How to verify

```bash
uv run python scripts/match_wikidata.py \
    --in data/samples/andorra.parquet \
    --parquet data/samples/andorra_wikidata.parquet \
    --jsonl data/samples/andorra_wikidata.jsonl \
    --map data/samples/andorra_wikidata_map.html --lang en
```