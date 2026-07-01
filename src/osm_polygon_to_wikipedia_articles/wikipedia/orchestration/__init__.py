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

Public API (from each sub-module's own ``__all__``)
---------------------------------------------------
- :class:`CountryPlan`, :class:`ValidationReport`
- :func:`discover_countries_with_wikidata`, :func:`plan_country_run`,
  :func:`validate_country_outputs`, :func:`process_one_country`,
  :func:`process_all`
"""
from __future__ import annotations

from . import process_countries
from .._init_helpers import union_all
from .process_countries import *  # noqa: F401, F403

__all__ = union_all(process_countries)
