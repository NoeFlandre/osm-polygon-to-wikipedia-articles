#!/usr/bin/env python
"""Re-run a country pipeline through batched-sitelinks for speed.

Uses Wikidata's batched ``wbgetentities`` (up to 50 QIDs/request) to fetch
sitelinks, then runs the standard summary + extract fetch for matched rows.

Outputs:
    data/samples/per_country/<slug>/<slug>.parquet (with thumbnail_is_svg)
    data/samples/per_country/<slug>/<slug>_wikidata.jsonl

Usage:
    uv run python scripts/rerun_country_batched.py <country>
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

import polars as pl

from osm_polygon_to_wikipedia_articles.wikipedia.fetch._adaptive_fetcher import (
    AdaptiveFetcher,
)
from osm_polygon_to_wikipedia_articles.wikipedia.fetch._rate_limiter import (
    RateLimiter,
)
from osm_polygon_to_wikipedia_articles.wikipedia.fetch._resilient_sitelinks import (
    fetch_sitelinks_resilient,
)
from osm_polygon_to_wikipedia_articles.wikipedia.fetch._sitelinks_checkpoint import (
    SitelinksCheckpoint,
)
from osm_polygon_to_wikipedia_articles.wikipedia.fetch._title_cache import (
    TitleCache,
)
from osm_polygon_to_wikipedia_articles.wikipedia.fetch.batched_sitelinks import (
    fetch_sitelinks_batched,
)
from osm_polygon_to_wikipedia_articles.wikipedia.fetch.extracts import fetch_extract
from osm_polygon_to_wikipedia_articles.wikipedia.fetch.http_client import (
    fetch_wikipedia_summary,
)
from osm_polygon_to_wikipedia_articles.wikipedia.fetch.summary import fetch_summary
from osm_polygon_to_wikipedia_articles.wikipedia.pipeline.thumbnail import (
    add_thumbnail_columns,
)
from osm_polygon_to_wikipedia_articles.wikipedia.pipeline.types import MatchResult


# How many parallel fetch_summary + fetch_extract workers.
# With HTTP/2 multiplexing (see PooledHttpClient) the per-request
# round-trip is paid once, so many workers just pipeline the I/O
# while the shared RateLimiter caps the actual API budget.
# 8 is a good default — enough to saturate the budget without
# triggering per-IP connection limits at Wikidata.
DEFAULT_WORKERS = 8
PROGRESS_EVERY = 20  # print progress every N QIDs

# Default rate limit for batched sitelinks.  Wikidata's anonymous
# budget is officially "low" (5 req/s) but the API frequently
# tolerates 10-15 req/s for short bursts; the adaptive
# :class:`RateLimiter` halves on every 429, so we start at the
# higher end and let the limiter back off automatically.  The
# shared sitelinks + summary/extract limiters stay independent so
# throttling on one doesn't slow the other.
DEFAULT_WIKIDATA_RATE = 15.0


def _detect_polygon_centroid(row: dict) -> tuple[float | None, float | None]:
    """Pull a (lon, lat) from whatever centroid columns the source has."""
    for lon_name in ("centroid_lon", "lon", "longitude"):
        if lon_name in row and row[lon_name] is not None:
            try:
                lon = float(row[lon_name])
            except (ValueError, TypeError):
                lon = None
            if lon is not None:
                lat_name = "centroid_lat" if "centroid_lat" in row else "lat" if "lat" in row else "latitude"
                lat = row.get(lat_name)
                try:
                    return lon, float(lat) if lat is not None else None
                except (ValueError, TypeError):
                    return lon, None
    return None, None


def _retry_forever(fn, *args, max_attempts: int = 30, **kwargs):
    """Call ``fn`` until it returns a truthy value.

    Wikipedia is occasionally rate-limited (HTTP 429) or briefly
    unavailable.  The lower-level :func:`get_json_with_retry` gives up
    after 5 attempts; for the per-country batch run we must not lose
    any polygon, so this helper wraps it in a *bounded* retry loop
    with exponential backoff capped at 60s.

    ``max_attempts`` bounds the total wait time so a permanently
    missing article (e.g. deleted Wikipedia page returning 404) does
    not block the whole run.  After the cap is reached, the function
    returns ``(None, attempts)`` so the caller can record the polygon
    with a non-``matched`` status — the polygon is **never** dropped
    silently; it just gets flagged for follow-up.

    Parameters
    ----------
    fn
        Callable that returns the article payload (or ``None`` on
        transient failure).
    *args, **kwargs
        Forwarded to ``fn``.
    max_attempts
        Hard cap on retries (default 30, ≈10 minutes total worst case).

    Returns
    -------
    ``(result, attempts)`` — ``result`` is whatever ``fn`` returned
    (possibly ``None`` if the cap was hit) and ``attempts`` is the
    number of calls made.
    """
    delay = 1.0
    attempts = 0
    while attempts < max_attempts:
        attempts += 1
        try:
            r = fn(*args, **kwargs)
        except Exception:
            r = None
        if r is not None:
            return r, attempts
        # 429 / 5xx usually clear in 1-30 s; back off exponentially but
        # never block for more than a minute.
        time.sleep(delay)
        delay = min(delay * 2, 60.0)
    return None, attempts


def _parse_workers() -> int:
    """Read --workers N from sys.argv (default 3)."""
    workers = DEFAULT_WORKERS
    if "--workers" in sys.argv:
        idx = sys.argv.index("--workers")
        if idx + 1 < len(sys.argv):
            try:
                workers = max(1, int(sys.argv[idx + 1]))
            except ValueError:
                pass
    return workers


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    country = args[0] if args else None
    if not country:
        print("usage: rerun_country_batched.py <country> [--workers N]"); return 2
    workers = _parse_workers()

    samples = Path("data/samples")
    folder = samples / "per_country" / country
    folder.mkdir(parents=True, exist_ok=True)
    parquet_out = folder / f"{country}.parquet"
    jsonl_out = folder / f"{country}_wikidata.jsonl"

    # Load source polygons from the source dataset
    print(f"[{country}] loading source polygons …", flush=True)
    src_url = f"hf://datasets/NoeFlandre/osm-polygon-selection/per_country/{country}/{country}.parquet"
    df_src = pl.read_parquet(src_url)
    n_src = df_src.height
    print(f"[{country}] source rows: {n_src:,}", flush=True)

    # Filter to wikidata-tagged polygons
    # The source parquet has a ``tags`` column (List[String] of "k=v" pairs).
    # Older sources had a direct ``wikidata`` column.
    wikidata_col = None
    if "wikidata" in df_src.columns:
        wikidata_col = "wikidata"
    elif "tags.wikidata" in df_src.columns:
        wikidata_col = "tags.wikidata"
    if wikidata_col:
        df_wd = df_src.filter(
            pl.col(wikidata_col).is_not_null() & (pl.col(wikidata_col) != "")
        )
    elif "tags" in df_src.columns:
        # Vectorised tag extraction: the ``tags`` column is a List<String>
        # of "k=v" pairs.  We delegate to ``extract_wikidata_qids`` which
        # filters to entries with the *direct* ``wikidata=`` key (no
        # namespace prefixes) and returns the QID value.  ~50x faster
        # than a per-row Python loop.
        from osm_polygon_to_wikipedia_articles.wikipedia.pipeline._wikidata_tags import (
            extract_wikidata_qids,
        )
        df_wd = extract_wikidata_qids(df_src).filter(
            pl.col("wikidata").is_not_null()
        )
    else:
        print(f"[{country}] no wikidata column", flush=True); return 1

    n_wd = df_wd.height if df_wd is not None else 0
    print(f"[{country}] wikidata-tagged: {n_wd:,}", flush=True)

    # Build qid -> row mapping.  Both branches (wikidata column or
    # extracted from tags) produce a ``wikidata`` column on ``df_wd``
    # so we can iterate the full rows once and bucket by QID.
    rows_by_qid: dict[str, list[dict]] = {}
    qid_col = wikidata_col if wikidata_col else "wikidata"
    for r in df_wd.iter_rows(named=True):
        qid = r.get(qid_col)
        if not qid:
            continue
        if not isinstance(qid, str):
            qid = str(qid)
        rows_by_qid.setdefault(qid, []).append(r)
    print(f"[{country}] unique QIDs: {len(rows_by_qid):,}", flush=True)

    # Resilient batched sitelinks fetch (rate-limited + checkpointed).
    # The checkpoint lives next to the JSONL so a kill / crash resumes
    # cleanly without re-fetching QIDs we already have.
    qids = sorted(rows_by_qid.keys())
    sitelinks_ckpt_path = folder / f"{country}_sitelinks.jsonl"
    rate_limiter = RateLimiter(max_per_second=DEFAULT_WIKIDATA_RATE)
    sitelinks_ckpt = SitelinksCheckpoint(sitelinks_ckpt_path)
    print(f"[{country}] resilient sitelinks fetch ({len(qids)} qids, "
          f"~{len(qids)//50 + 1} batches, rate={DEFAULT_WIKIDATA_RATE}/s)…",
          flush=True)
    t0 = time.time()
    last_log = [t0]

    def _progress(done: int, total: int) -> None:
        # Throttle progress to once every 10 s to keep the log readable
        # for the largest countries.
        now = time.time()
        if now - last_log[0] < 10 and done < total:
            return
        elapsed = now - t0
        qps = done / elapsed if elapsed > 0 else 0
        snap = rate_limiter.snapshot()
        print(f"[{country}]   sitelinks: {done}/{total} "
              f"({100*done/total:.0f}%, {qps:.1f} qids/s, "
              f"rate={snap['max_per_second']:.1f}/s, "
              f"429s={snap['throttle_events']}, "
              f"elapsed={elapsed:.0f}s)", flush=True)
        last_log[0] = now

    sitelinks_dict = fetch_sitelinks_resilient(
        qids,
        rate_limiter=rate_limiter,
        checkpoint=sitelinks_ckpt,
        progress=_progress,
        batch_size=50,
        max_workers=workers,
    )
    sitelinks_ckpt.close()
    # Count only "real" sitelinks (excluding _missing markers).
    real = {q: sl for q, sl in sitelinks_dict.items() if "_missing" not in sl}
    missing = [q for q, sl in sitelinks_dict.items() if "_missing" in sl]
    print(f"[{country}] sitelinks: {len(real)} resolved, "
          f"{len(missing)} missing/failed, "
          f"in {time.time()-t0:.1f}s", flush=True)

    # Walk each polygon: decide matched/no_sitelinks/no_lang_sitelink.
    # The fetch_summary + fetch_extract for matched QIDs is parallelised
    # across ``DEFAULT_WORKERS`` threads (the Wikipedia API is independent
    # per article title). Without this, sequential fetching takes ~9s
    # per polygon; with 8 workers, the same 782 polygons finish in
    # under 2 minutes.
    matched: list[dict] = []
    total = 0
    matches = 0
    nsl = 0
    nll = 0

    # Pre-compute per-QID status + the (title, lang) tuple to fetch.
    # QIDs that the resilient layer marked as ``_missing`` (e.g. the
    # Wikidata API was throttled past our safety valve) are recorded
    # as ``no_sitelinks`` so they are never silently dropped.
    qid_plan: list[tuple[str, list[dict], str, str | None, int]] = []
    for qid, rows in rows_by_qid.items():
        sl = sitelinks_dict.get(qid)
        if not sl or "_missing" in sl:
            qid_plan.append((qid, rows, "no_sitelinks", None, 0))
            nsl += 1
            continue
        en = sl.get("enwiki")
        if not en:
            qid_plan.append((qid, rows, "no_lang_sitelink", None, len(sl)))
            nll += 1
            continue
        qid_plan.append((qid, rows, "matched", en.get("title", ""), len(sl)))
        matches += 1

    print(f"[{country}] planning: matched={matches}, no_sitelinks={nsl}, no_lang={nll}", flush=True)

    # Shared RateLimiter for all summary + extract fetches.  This is
    # distinct from the sitelinks rate limiter — Wikipedia and
    # Wikidata have separate per-IP budgets.
    wiki_rl = RateLimiter(max_per_second=10.0, burst=10)

    # AdaptiveFetcher wraps the raw fetcher with rate-limited retry.
    # TitleCache wraps AdaptiveFetcher (not the other way around!) so
    # failed fetches (None) are NOT cached — the AdaptiveFetcher's
    # retry loop then issues real HTTP requests instead of just
    # hitting the cache.
    summary_adaptive = AdaptiveFetcher(
        fn=fetch_summary, rate_limiter=wiki_rl, max_attempts=10,
    )
    extract_adaptive = AdaptiveFetcher(
        fn=fetch_extract, rate_limiter=wiki_rl, max_attempts=10,
    )
    summary_cache = TitleCache(
        fetcher=lambda lang, t: summary_adaptive.run(lang, t)[0],
    )
    extract_cache = TitleCache(
        fetcher=lambda lang, t: extract_adaptive.run(lang, t)[0],
    )

    def _fetch_one(plan_item: tuple) -> dict:
        """Fetch summary + extract for one matched QID; return its result dict.

        TitleCache deduplicates across QIDs that map to the same
        article — a country with 5 matched articles and 277 k
        polygons issues ~10 fetch_summary calls instead of ~277 k.

        If the summary ultimately returns ``None`` (e.g. a deleted
        Wikipedia page), the polygon is recorded with status
        ``"no_summary"`` rather than ``"matched"`` — never silently
        dropped.
        """
        qid, rows, status, title, sl_count = plan_item
        if status != "matched":
            return {
                "qid": qid, "rows": rows, "status": status, "title": None,
                "summary": None, "body": None, "url": None, "pageid": None,
                "thumb": None, "lat": None, "lon": None, "description": None,
                "extract_short": None, "sitelinks_count": sl_count,
                "summary_attempts": 0, "extract_attempts": 0,
            }
        summary_obj = summary_cache.get("en", title)
        if summary_obj is None:
            # Permanently failed (deleted article, 404, etc.).  Still
            # record the polygon — the user's contract is "no silent
            # drops" — but flag it so it does not pollute the
            # ``matched`` count in the dataset.
            return {
                "qid": qid, "rows": rows, "status": "no_summary", "title": title,
                "summary": None, "body": "", "url": None, "pageid": None,
                "thumb": None, "lat": None, "lon": None, "description": None,
                "extract_short": None, "sitelinks_count": sl_count,
                "summary_attempts": summary_adaptive._max_attempts,
                "extract_attempts": 0,
            }
        body = extract_cache.get("en", title) or ""
        url = (summary_obj.url if summary_obj
               else f"https://en.wikipedia.org/wiki/{title}")
        return {
            "qid": qid, "rows": rows, "status": status, "title": title,
            "summary": summary_obj, "body": body, "url": url,
            "pageid": summary_obj.pageid if summary_obj else None,
            "thumb": summary_obj.thumbnail_url if summary_obj else None,
            "lat": summary_obj.lat if summary_obj else None,
            "lon": summary_obj.lon if summary_obj else None,
            "description": summary_obj.description if summary_obj else None,
            "extract_short": summary_obj.extract if summary_obj else None,
            "sitelinks_count": sl_count,
            "summary_attempts": 0,
            "extract_attempts": 0,
        }

    # Skip QIDs already processed (resumability).
    done_qids: set[str] = set()
    if jsonl_out.exists():
        with jsonl_out.open() as jf:
            for line in jf:
                line = line.strip()
                if line:
                    try:
                        done_qids.add(json.loads(line)["wikidata_qid"])
                    except Exception:
                        pass
    pending = [item for item in qid_plan if item[0] not in done_qids]
    print(f"[{country}] {len(done_qids)} already done, {len(pending)} to fetch ({workers} workers)", flush=True)

    # Append-mode JSONL: keep existing records, stream new ones in.
    jf = jsonl_out.open("a")
    try:
        t_fetch = time.time()
        completed = 0

        def _process_one(item: tuple) -> dict:
            return _fetch_one(item)

        def _emit(r: dict) -> None:
            """Write the JSONL rows for this QID and accumulate ``matched``."""
            nonlocal total
            status = r["status"]
            for row in r["rows"]:
                total += 1
                centroid_lon, centroid_lat = _detect_polygon_centroid(row)
                geom = row.get("geometry_wkt") or None
                result = MatchResult(
                    osm_id=int(row.get("osm_id") or 0),
                    osm_type=str(row.get("osm_type") or "way"),
                    country=country,
                    size_bin=str(row.get("size_bin") or ""),
                    centroid_lon=centroid_lon,
                    centroid_lat=centroid_lat,
                    wikidata_qid=r["qid"],
                    article_title=r["title"] or "",
                    article_lang="en" if status == "matched" else "",
                    article_url=r["url"] or "",
                    sitelinks_count=int(r["sitelinks_count"]),
                    match_status=status,
                    article_description=r["description"],
                    article_extract_short=r["extract_short"],
                    article_thumbnail_url=r["thumb"],
                    article_lat=r["lat"],
                    article_lon=r["lon"],
                    article_pageid=r["pageid"],
                    article_body_text=r["body"] or "",
                    geometry_wkt=geom,
                )
                rec = asdict(result)
                jf.write(json.dumps(rec) + "\n")
                if status == "matched":
                    matched.append(rec)

        if len(pending) <= workers:
            for item in pending:
                r = _process_one(item)
                _emit(r)
                completed += 1
                if completed % PROGRESS_EVERY == 0:
                    print(f"[{country}]   ... {completed}/{len(pending)} QIDs done", flush=True)
        else:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futures = {ex.submit(_process_one, item): item[0] for item in pending}
                for fut in as_completed(futures):
                    r = fut.result()
                    _emit(r)
                    completed += 1
                    if completed % PROGRESS_EVERY == 0:
                        print(f"[{country}]   ... {completed}/{len(pending)} QIDs done "
                              f"({time.time()-t_fetch:.0f}s elapsed)", flush=True)
        jf.flush()
        print(f"[{country}] per-QID fetch done in {time.time()-t_fetch:.1f}s "
              f"({completed} QIDs)", flush=True)
    finally:
        jf.close()

    # Tally the final status counts from the on-disk JSONL so we can
    # confirm no polygons were dropped (every source polygon must
    # appear in the JSONL with *some* status).
    status_counts: dict[str, int] = {}
    polygon_count = 0
    with jsonl_out.open() as jf:
        for line in jf:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            polygon_count += 1
            s = rec.get("match_status", "unknown")
            status_counts[s] = status_counts.get(s, 0) + 1
    print(f"[{country}] polygon status breakdown: {status_counts}", flush=True)

    expected = n_wd  # every wikidata-tagged polygon should be in JSONL
    if polygon_count != expected:
        print(f"[{country}] WARNING: expected {expected} polygons in JSONL, "
              f"got {polygon_count}. Missing: {expected - polygon_count}",
              flush=True)
    else:
        print(f"[{country}] all {polygon_count} wikidata-tagged polygons "
              f"are recorded in JSONL (no drops)", flush=True)

    if matched:
        df = pl.DataFrame(matched)
        df = add_thumbnail_columns(df)
        df.write_parquet(parquet_out)
        print(f"[{country}] wrote {df.height} matched rows -> {parquet_out}", flush=True)
    else:
        # Write empty with right schema
        df = pl.DataFrame(schema={
            "osm_id": pl.Int64, "osm_type": pl.String, "country": pl.String,
            "size_bin": pl.String, "centroid_lon": pl.Float64, "centroid_lat": pl.Float64,
            "wikidata_qid": pl.String, "article_title": pl.String, "article_lang": pl.String,
            "article_url": pl.String, "sitelinks_count": pl.Int64, "match_status": pl.String,
            "article_description": pl.String, "article_extract_short": pl.String,
            "article_thumbnail_url": pl.String, "article_lat": pl.Float64,
            "article_lon": pl.Float64, "article_pageid": pl.Int64,
            "article_body_text": pl.String, "geometry_wkt": pl.String,
            "thumbnail_is_svg": pl.Boolean,
        })
        df.write_parquet(parquet_out)
        print(f"[{country}] no matches; wrote empty {parquet_out}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
