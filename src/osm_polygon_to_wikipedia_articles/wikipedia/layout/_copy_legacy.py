"""Copy legacy flat files into the canonical subfolder layout.

:func:`_discover_legacy_slugs` finds every country slug referenced by
the old flat file naming. :func:`_copy_country_legacy_files` copies
each country's flat files into its subfolder, never deleting at
source (the user must approve deletes explicitly).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from ._paths import PER_COUNTRY_DIR, country_paths_for
from ._slug_suffix import parse_legacy_stem

_LEGACY_FLAT_GLOBS = (
    "*_wikidata.{ext}",
    "*_wikidata_map.{ext}",
    "*_polygons_map.{ext}",
)
_LEGACY_EXTENSIONS = ("parquet", "jsonl", "html", "png")


def _discover_legacy_slugs(samples_root: Path) -> list[str]:
    """Return every country slug referenced by a legacy flat file."""
    slugs: set[str] = set()
    for ext in _LEGACY_EXTENSIONS:
        for glob in _LEGACY_FLAT_GLOBS:
            for p in samples_root.glob(glob.format(ext=ext)):
                slug, _ = parse_legacy_stem(p.stem)
                if slug and slug != "all":
                    slugs.add(slug)
    return sorted(slugs)


def _copy_country_legacy_files(samples_root: Path, slug: str) -> int:
    """Copy a single country's flat files into ``per_country/<slug>/``.

    Destination filename preserves the legacy naming so existing scripts
    that look for ``<slug>_wikidata.jsonl`` / ``<slug>_wikidata_map.html``
    etc. inside the per-country folder keep working.

    Returns the number of files copied.
    """
    copied = 0
    targets = country_paths_for(samples_root, slug)
    targets.folder.mkdir(parents=True, exist_ok=True)

    # The "main" parquet and jsonl: keep the same names (just relocated).
    for src, dst_name in (
        (samples_root / f"{slug}_wikidata.parquet", f"{slug}.parquet"),
        (samples_root / f"{slug}_wikidata.jsonl", f"{slug}_wikidata.jsonl"),
    ):
        if src.exists():
            dst = targets.folder / dst_name
            if not dst.exists():
                shutil.copy2(str(src), str(dst))
                copied += 1

    # Aux maps: variant preserved (_wikidata_map stays _wikidata_map).
    for src_suffix in ("_wikidata_map", "_polygons_map"):
        for ext in ("html", "png"):
            src = samples_root / f"{slug}{src_suffix}.{ext}"
            if not src.exists():
                continue
            dst = targets.folder / f"{slug}{src_suffix}.{ext}"
            if not dst.exists():
                shutil.copy2(str(src), str(dst))
                copied += 1

    return copied


__all__ = ["_copy_country_legacy_files", "_discover_legacy_slugs"]
