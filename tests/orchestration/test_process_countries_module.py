"""Tests that lock in the public API of
``wikipedia.orchestration.process_countries``.

Why
---
The 311-LOC module grew three pieces of dead / low-value code:

1. ``process_one_country`` — raises ``NotImplementedError``. The real
   per-country processing happens in ``scripts/per_country/process_countries.py``
   which calls ``scripts/match_wikidata.py``. So nothing imports this
   library function.

2. ``hf_upload`` + ``_hf_token_env`` — defined but never called. The
   scripts invoke ``hf upload`` themselves (subprocess) or use
   ``huggingface_hub.HfApi``.

3. The three ``_*_with_sleep`` closures (``_sitelinks_with_sleep``,
   ``_summary_with_sleep``, ``_extract_with_sleep``) — only ever used
   by ``process_one_country`` itself, which is dead code.

These tests assert the module shape so the dead code doesn't get
re-introduced by accident.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from osm_polygon_to_wikipedia_articles.wikipedia import orchestration as _orch
from osm_polygon_to_wikipedia_articles.wikipedia.orchestration import (
    process_countries as _pc,
)

MODULE_PATH = Path(_pc.__file__)


# ---------------------------------------------------------------------------
# File-level invariants
# ---------------------------------------------------------------------------

def test_module_lte_260_lines() -> None:
    """The module should stay compact after the dead-code removal +
    copy-helper extraction.  Was 311 LOC; the new helper adds ~25 LOC
    back so the cap is set generously at 260.
    """
    lines = sum(1 for _ in MODULE_PATH.read_text().splitlines())
    assert lines <= 260, f"{MODULE_PATH} is {lines} lines (cap=260)"


def test_module_does_not_define_dead_helpers() -> None:
    """The three ``_*_with_sleep`` closures and ``hf_upload`` /
    ``_hf_token_env`` must not exist in this module.
    """
    names = set(dir(_pc))
    forbidden = {
        "_sitelinks_with_sleep",
        "_summary_with_sleep",
        "_extract_with_sleep",
        "hf_upload",
        "_hf_token_env",
    }
    leftover = names & forbidden
    assert not leftover, f"dead helpers still defined: {sorted(leftover)}"


def test_module_does_not_define_unimplemented_country_processor() -> None:
    """``process_one_country`` only ever raised ``NotImplementedError``
    — the real implementation lives in scripts/.  It must not be
    re-introduced as a library function.
    """
    assert not hasattr(_pc, "process_one_country"), (
        "process_one_country was removed (it only raised NotImplementedError); "
        "use scripts/per_country/process_countries.py instead."
    )


# ---------------------------------------------------------------------------
# Public API contract
# ---------------------------------------------------------------------------

def test_orchestration_dunder_all_only_exposes_used_symbols() -> None:
    """The orchestration subpackage's ``__all__`` must not list
    symbols that don't actually exist or are no-ops.
    """
    for name in _orch.__all__:
        assert hasattr(_orch, name), f"{name!r} is in __all__ but missing"


def test_public_api_is_exactly_the_implemented_names() -> None:
    """The canonical public API of the orchestration subpackage.

    This is the regression guard: if you add a function to
    ``process_countries.py`` and add it to ``__all__``, add it to
    this set too.  If you delete one (and it's truly dead), remove
    it from this set.
    """
    expected = {
        "CountryPlan",
        "ValidationReport",
        "copy_country_outputs_to_samples",
        "discover_countries_with_wikidata",
        "plan_country_run",
        "process_all",
        "validate_country_outputs",
    }
    actual = set(_orch.__all__)
    missing = expected - actual
    extra = actual - expected
    assert not missing, f"missing from __all__: {sorted(missing)}"
    assert not extra, f"unexpected in __all__: {sorted(extra)}"


# ---------------------------------------------------------------------------
# Spot-check the surviving functions are real implementations
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "discover_countries_with_wikidata",
    "plan_country_run",
    "validate_country_outputs",
    "process_all",
])
def test_surviving_function_is_real(name: str) -> None:
    """Each surviving public function must be a real implementation
    (not a NotImplementedError stub).
    """
    fn = getattr(_pc, name)
    src = inspect.getsource(fn)
    assert "NotImplementedError" not in src, (
        f"{name}() body still contains NotImplementedError — "
        "should be deleted, not stubbed."
    )
