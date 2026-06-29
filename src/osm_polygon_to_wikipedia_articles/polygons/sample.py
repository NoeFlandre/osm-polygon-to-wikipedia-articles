"""Polygon sampling: pure functions over polars DataFrames."""
from pathlib import Path
from typing import Iterable, Mapping

import polars as pl

from .load import load_country


def sample_polygons(
    df: pl.DataFrame,
    n: int,
    seed: int = 0,
    stratify_by: str | None = None,
) -> pl.DataFrame:
    """Return a random sample of up to ``n`` polygons from ``df``.

    With ``stratify_by`` (a column name), the sample is taken proportionally
    from each stratum using per-stratum seeds derived from ``seed``.
    """
    if stratify_by is not None:
        out_parts = []
        for stratum_value, group in df.group_by(stratify_by):
            k = max(1, round(n * group.height / df.height))
            out_parts.append(
                group.sample(n=min(k, group.height), seed=seed, with_replacement=False)
            )
        return pl.concat(out_parts)

    k = min(n, df.height)
    return df.sample(n=k, seed=seed, with_replacement=False)


def build_sample(
    countries: Iterable[str],
    n_per_country: int,
    seed: int = 0,
    out_path: Path | None = None,
    repo_id: str = "NoeFlandre/osm-polygon-selection",
    fixtures: Mapping[str, pl.DataFrame] | None = None,
) -> pl.DataFrame:
    """Sample ``n_per_country`` polygons from each country, concat, optionally write parquet.

    ``fixtures`` (test hook) bypasses HF I/O: pass ``{country_slug: DataFrame}``
    instead of hitting the network.
    """
    parts: list[pl.DataFrame] = []
    for i, slug in enumerate(countries):
        df = fixtures[slug] if fixtures is not None else load_country(slug, repo_id=repo_id)
        parts.append(sample_polygons(df, n=n_per_country, seed=seed + i))
    combined = pl.concat(parts, how="vertical")

    if out_path is not None:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        combined.write_parquet(out_path)

    return combined