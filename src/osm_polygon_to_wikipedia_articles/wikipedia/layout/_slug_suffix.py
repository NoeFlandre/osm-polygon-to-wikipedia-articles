"""Slug / suffix parsers shared by the layout + safe-deletion code.

The published dataset went through a flat layout (``<slug>_wikidata.*``,
``<slug>_wikidata_map.*``, ``<slug>_polygons_map.*``) and then migrated
to a 4-subfolder layout. Two parsers live here:

- :func:`parse_legacy_stem` — map a *flat-file stem* to ``(slug, suffix)``
- :func:`parse_hf_root_filename` — map an *HF root filename* to
  ``(slug, canonic_HF_path)``

Both encodings are needed by ``migrate_full_layout``, ``delete_legacy``,
and ``delete_hf_duplicates`` — keeping them in one place prevents the
suffix-list from drifting between modules.
"""
from __future__ import annotations

# Order matters: longest first so "_wikidata_map" wins over "_wikidata"
# when both are valid (e.g. "poland_wikidata_map" must slug=poland).
_LEGACY_SUFFIXES: tuple[str, ...] = (
    "_wikidata_map",
    "_polygons_map",
    "_wikidata",
)


def parse_legacy_stem(stem: str) -> tuple[str | None, str | None]:
    """Map a flat-file stem to ``(slug, source_suffix)`` (or ``None``s).

    >>> parse_legacy_stem("poland_wikidata_map")
    ('poland', '_wikidata_map')
    >>> parse_legacy_stem("poland_wikidata")
    ('poland', '_wikidata')
    >>> parse_legacy_stem("foo")
    (None, None)
    """
    for suffix in _LEGACY_SUFFIXES:
        if stem.endswith(suffix):
            return stem[: -len(suffix)], suffix
    return None, None


# --- HF root filename → (slug, canonic path) -----------------------------


def parse_hf_root_filename(name: str) -> tuple[str, str] | None:
    """Map a legacy HF root filename to ``(slug, canonic_HF_path)``.

    Returns ``None`` for filenames we have no canonical mapping for;
    such files must be left untouched.
    """
    # Union aggregate MUST be checked BEFORE the suffix-based rules,
    # otherwise ``all_wikidata.parquet`` would resolve to
    # ``per_country/all/all.parquet``.
    if name == "all_wikidata.parquet":
        return "all", "combined/all_europe.parquet"
    if name in {"all_wikidata_map.png", "all_wikidata_map.html"}:
        ext = name.rsplit(".", 1)[1]
        return "all", f"preview/map_preview.{ext}"
    if name in {"map_preview.png", "map_preview.html"}:
        # map_preview.{png,html} pushed to root earlier — also exists at preview/
        return "all", f"preview/{name}"
    # <slug>_polygons_map.{html,png}
    for ext in ("html", "png"):
        if name.endswith(f"_polygons_map.{ext}"):
            slug = name[: -len(f"_polygons_map.{ext}")]
            return slug, f"per_country/{slug}/{slug}_polygons_map.{ext}"
    # <slug>_wikidata_map.{html,png}
    for ext in ("html", "png"):
        if name.endswith(f"_wikidata_map.{ext}"):
            slug = name[: -len(f"_wikidata_map.{ext}")]
            return slug, f"per_country/{slug}/{slug}_wikidata_map.{ext}"
    # <slug>_wikidata.jsonl
    if name.endswith("_wikidata.jsonl"):
        slug = name[: -len("_wikidata.jsonl")]
        return slug, f"per_country/{slug}/{slug}_wikidata.jsonl"
    # <slug>_wikidata.parquet
    if name.endswith("_wikidata.parquet"):
        slug = name[: -len("_wikidata.parquet")]
        return slug, f"per_country/{slug}/{slug}.parquet"
    # andorra.parquet (orphan, no _wikidata suffix)
    if name.endswith(".parquet") and "_" not in name:
        slug = name[: -len(".parquet")]
        return slug, f"per_country/{slug}/{slug}.parquet"
    return None


__all__ = ["parse_legacy_stem", "parse_hf_root_filename"]
