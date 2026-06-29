# Wikidata matches — dev sample

Source: `data/samples/dev.parquet` (352 polygons, 8 countries, 50 each; Monaco capped at 2).
Run: `uv run python scripts/match_wikidata.py --lang en` (regenerates `data/samples/dev_wikidata.jsonl`).

Of the 352 polygons, **6 (1.7%)** carry a valid `wikidata=*` tag. Of those, **5** have an English Wikipedia sitelink and resolve to a real article; **1** (Iceland) has sitelinks only in non-English languages.

## Matches

| # | Wikidata QID | Country | OSM ID | OSM type | Size bin | Centroid (lon, lat) | English article | URL |
|---|---|---|---:|---|---|---|---|---|
| 1 | Q7230673 | Monaco | 4442359 | relation | small | (7.42…, 43.73…) | **Port Hercules** | https://en.wikipedia.org/wiki/Port_Hercules |
| 2 | Q634958 | Luxembourg | 34304773 | relation | large | (6.13…, 49.60…) | **Roodt, Ell** | https://en.wikipedia.org/wiki/Roodt,_Ell |
| 3 | Q27008729 | Iceland | 31543971 | relation | large | (… , …) | _no English sitelink_ | — |
| 4 | Q828250 | Malta | 20731478 | way | small | (14.34…, 36.01…) | **Cominotto** | https://en.wikipedia.org/wiki/Cominotto |
| 5 | Q899139 | Faroe Islands | 26435901 | relation | large | (… , …) | **Skálafjørður** | https://en.wikipedia.org/wiki/Skálafj%C3%B8r%C3%B0ur |
| 6 | Q1741199 | Estonia | 508067 | relation | large | (24.00…, 58.13…) | **Kihnu** | https://en.wikipedia.org/wiki/Kihnu |

## What this tells us

- **The Wikidata path works**: every polygon with a `wikidata=*` tag (5/6) was resolved to a real, topically-relevant English Wikipedia article (a port, a town, a Maltese islet, a Faroese fjord, an Estonian island).
- **Coverage is the bottleneck, not accuracy**: only ~1–3% of OSM polygons have the tag. Scaling this to all 5k polygons in `osm-polygon-selection` would yield roughly 50–150 hits — useful as a seed, not a corpus.
- **Q27008729 (Iceland)** is the first failure mode worth tracking. The entity exists on Wikidata (1+ non-en sitelink) but has no English Wikipedia article. Re-running with `--lang is` would likely succeed. Worth adding a "fallback to other lang" rule in a future iteration if multilingual coverage matters.
- **Distance sanity check not yet applied**: we trust the sitelink 1:1, but for the next stage (geosearch fallback) we'll want to compare the article's reported coordinates against the polygon's centroid within ~1km. Wikidata QIDs are reliable enough to skip that check here.

## How to verify

```bash
# regenerate the JSONL
uv run python scripts/match_wikidata.py \
    --in data/samples/dev.parquet \
    --out data/samples/dev_wikidata.jsonl --lang en

# inspect raw records
cat data/samples/dev_wikidata.jsonl | head -6
```

## What this doesn't tell us

- The remaining ~346 polygons without `wikidata=*` are not represented here. They will need the **name match** ladder (next stage) or **geosearch** to be assigned an article.
- No spot-check has been done yet on whether e.g. "Port Hercules" is actually *about* the OSM polygon or about something else with the same name. Manual review of the 5 URLs is the next step.