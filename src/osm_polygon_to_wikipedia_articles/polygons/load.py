"""Polygon loading from the osm-polygon-selection HF dataset."""
from pathlib import Path

import polars as pl
from huggingface_hub import HfApi

DATASET_REPO_ID = "NoeFlandre/osm-polygon-selection"


def list_countries(repo_id: str = DATASET_REPO_ID) -> list[str]:
    """Return the sorted list of country slugs available as parquet files."""
    api = HfApi()
    files = api.list_repo_files(repo_id=repo_id, repo_type="dataset")
    return sorted(
        Path(f).stem
        for f in files
        if f.endswith(".parquet") and "/" not in Path(f).stem
    )


def load_country(
    slug: str,
    repo_id: str = DATASET_REPO_ID,
    local_path: Path | None = None,
) -> pl.DataFrame:
    """Load a single country's polygon parquet.

    If ``local_path`` is given, read from disk (useful for tests/fixtures).
    Otherwise stream from the HF dataset repo via the ``hf://`` protocol.
    """
    if local_path is not None:
        if not Path(local_path).exists():
            raise FileNotFoundError(f"local parquet not found: {local_path}")
        return pl.read_parquet(local_path)

    path = f"hf://datasets/{repo_id}/{slug}.parquet"
    try:
        return pl.read_parquet(path)
    except Exception as exc:
        # polars wraps HF's 404 in a ComputeError; surface a clean FileNotFoundError
        if "does not exist" in str(exc) or "No such file" in str(exc):
            raise FileNotFoundError(f"country slug not in dataset: {slug!r}") from exc
        raise