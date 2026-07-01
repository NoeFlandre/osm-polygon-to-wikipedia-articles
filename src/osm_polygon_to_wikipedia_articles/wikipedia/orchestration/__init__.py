"""Per-country end-to-end orchestration.

Drives the full sample → match → validate → push loop for one country
at a time. Heavy intermediate files live under ``OSM_DATA_ROOT`` (the
external Seagate HDD) and slim outputs get copied into
``./data/samples/`` for the published dataset.

Modules
-------
process_countries
    :func:`process_one_country`, :func:`process_all`, plus the
    :class:`CountryPlan` / :class:`ValidationReport` dataclasses and
    the :func:`plan_country_run` / :func:`validate_country_outputs`
    helpers.

Public API
----------
- :class:`CountryPlan`, :class:`ValidationReport`
- :func:`discover_countries_with_wikidata`, :func:`plan_country_run`,
  :func:`validate_country_outputs`, :func:`process_one_country`,
  :func:`process_all`
"""
from __future__ import annotations

from .process_countries import (
    CountryPlan,
    ValidationReport,
    discover_countries_with_wikidata,
    plan_country_run,
    process_all,
    process_one_country,
    validate_country_outputs,
)

__all__ = [
    "CountryPlan",
    "ValidationReport",
    "discover_countries_with_wikidata",
    "plan_country_run",
    "process_all",
    "process_one_country",
    "validate_country_outputs",
]
