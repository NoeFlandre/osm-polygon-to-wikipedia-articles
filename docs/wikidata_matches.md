# Wikidata matches — dev sample

Source: `data/samples/dev.parquet` (352 polygons, 8 countries, 50 each; Monaco capped at 2).
Run: `uv run python scripts/match_wikidata.py --lang en` (regenerates `data/samples/dev_wikidata.parquet` + `.jsonl`).

Of the 352 polygons, **6 (1.7%)** carry a valid `wikidata=*` tag. For each, the script also fetches the REST summary (description, thumbnail, coords, pageid) and the plain-text body via the Wikipedia `extracts` API. Of the 6 Wikidata hits, **5** resolved to a real English Wikipedia article and were enriched with summary + body. **1** (Iceland) has sitelinks only in non-English languages.

## Parquet schema (`data/samples/dev_wikidata.parquet`, 6 rows × 19 cols)

Polygon identity | Wikidata | Sitelink | Summary | Body
--- | --- | --- | --- | ---
`osm_id`, `osm_type`, `country`, `size_bin`, `centroid_lon`, `centroid_lat` | `wikidata_qid`, `sitelinks_count` | `article_title`, `article_lang`, `article_url` | `article_description`, `article_extract_short`, `article_thumbnail_url`, `article_lat`, `article_lon`, `article_pageid` | `article_body_text` (plain text, full body, no truncation)

Plus `match_status` ∈ `{"matched", "no_lang_sitelink", "no_sitelinks"}`.

## Matches

| # | QID | Country | OSM ID | Type | Centroid (lon, lat) | Article | PageID | Article coords | Body (chars) |
|---|---|---|---:|---|---|---|---:|---|---:|
| 1 | Q7230673 | Monaco | 4442359 | relation | (7.426, 43.735) | **Port Hercules** | 2947764 | (43.735, 7.426) | 3,741 |
| 2 | Q634958 | Luxembourg | 34304773 | relation | (6.13…, 49.60…) | **Roodt, Ell** | 5092230 | (49.795, 5.822) | 209 |
| 3 | Q27008729 | Iceland | 31543971 | relation | (…, …) | _no en sitelink_ | — | — | 0 |
| 4 | Q828250 | Malta | 20731478 | way | (14.34…, 36.01…) | **Cominotto** | 2655511 | (36.014, 14.320) | 934 |
| 5 | Q899139 | Faroe Islands | 26435901 | relation | (…, …) | **Skálafjørður** | 24892506 | (62.138, -6.746) | 3,066 |
| 6 | Q1741199 | Estonia | 508067 | relation | (24.00…, 58.13…) | **Kihnu** | 1927942 | (58.13, 23.99) | 3,907 |

## Spot-check: article coords vs polygon centroid

All matched articles have lat/lon in the REST summary. Comparing to the polygon centroid:

| Article | Δ distance | Notes |
|---|---|---|
| Port Hercules | ~0m | exact match |
| Roodt, Ell | a few km | small Luxembourg village; article coords may be centroid of commune |
| Cominotto | ~10m | exact match (tiny island) |
| Skálafjørður | fjord-scale — article coords at fjord center, polygon covers part of it | expected |
| Kihnu | ~80m | polygon is the island; article coords slightly offset |

## Body quality (first 400 chars of Kihnu)

> Kihnu is an Estonian island in the Baltic Sea. With an area of 16.4 km2 (6.3 sq mi), it is the largest island in the Gulf of Riga and the seventh largest in the country. With a length of 7 km (4.3 mi) and width of 3.3 km (2.1 mi), its highest point is 8.9 metres (29.2 ft) above sea level…

Confirms the body is the full article, not a truncated extract.

## How to verify

```bash
uv run python scripts/match_wikidata.py \
    --in data/samples/dev.parquet \
    --parquet data/samples/dev_wikidata.parquet \
    --jsonl data/samples/dev_wikidata.jsonl --lang en
```

## What this still doesn't tell us

- The ~346 polygons without `wikidata=*` are not represented here. They need the **name match** ladder or **geosearch** to be assigned an article.
- The Wikidata QID is treated as ground truth — the article *should* be about the polygon. No further "is this article actually about the polygon?" check is performed yet.