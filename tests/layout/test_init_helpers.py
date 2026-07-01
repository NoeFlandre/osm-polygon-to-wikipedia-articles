"""Tests for the shared ``_init_helpers.union_all`` helper.

This helper consolidates the boilerplate that was previously
duplicated across the 5 subpackage ``__init__.py`` files.
"""
from __future__ import annotations

from types import ModuleType

import pytest

from osm_polygon_to_wikipedia_articles.wikipedia._init_helpers import union_all


def _mod(name: str, all_: list[str]) -> ModuleType:
    m = ModuleType(name)
    m.__all__ = all_
    return m


def test_union_empty() -> None:
    assert union_all() == []


def test_union_single() -> None:
    m = _mod("a", ["x", "y"])
    assert union_all(m) == ["x", "y"]


def test_union_preserves_module_order() -> None:
    a = _mod("a", ["a1", "a2"])
    b = _mod("b", ["b1"])
    assert union_all(a, b) == ["a1", "a2", "b1"]


def test_union_dedupes_keeping_first_occurrence() -> None:
    a = _mod("a", ["x", "y"])
    b = _mod("b", ["y", "z"])
    assert union_all(a, b) == ["x", "y", "z"]


def test_union_skips_annotations_name() -> None:
    """Some modules inject ``annotations`` as a public name when
    they use ``from __future__ import annotations``.  It is not a
    real export, so the helper filters it out.
    """
    a = _mod("a", ["annotations", "x"])
    assert union_all(a) == ["x"]


def test_union_module_without_dunder_all_yields_nothing() -> None:
    """A module without ``__all__`` contributes nothing.

    Python's ``import *`` will still bind its public names into the
    importer's namespace, but the helper only re-exports symbols
    that are explicitly declared.
    """
    m = ModuleType("a")
    # no __all__
    assert union_all(m) == []


def test_union_module_with_empty_dunder_all() -> None:
    m = _mod("a", [])
    assert union_all(m) == []


@pytest.mark.parametrize("mix", [
    # real-world shape: subpackage with multiple modules
    [("layout._paths", ["RootPaths", "CountryPaths"]),
     ("layout._manifest", ["write_manifest_json"]),
     ("layout.full_layout", ["build_all_europe"])],
])
def test_union_realistic_layout_shape(mix: list[tuple[str, list[str]]]) -> None:
    mods = [_mod(name, all_) for name, all_ in mix]
    assert union_all(*mods) == [
        "RootPaths", "CountryPaths",
        "write_manifest_json",
        "build_all_europe",
    ]
