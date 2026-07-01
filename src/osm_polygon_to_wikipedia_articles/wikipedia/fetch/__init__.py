"""HTTP layer: talk to Wikidata and Wikipedia.

This subpackage is the only place in the codebase that does I/O. Every
fetching function is injectable (its network call is hidden behind a
``_get`` or ``urlopen`` parameter) so tests can swap in a fake.

Modules
-------
_retry
    Reusable retry-on-transient-error helper (urllib + JSON).
http_client
    Thin convenience wrappers over the retry layer (legacy API).
batched_sitelinks
    Batched ``wbgetentities`` (up to 50 QIDs/request) — used for the
    per-country end-to-end re-process because the single-QID endpoint
    is rate-limited under sustained load.
summary
    ``https://<lang>.wikipedia.org/api/rest_v1/page/summary/<title>``
extracts
    ``https://<lang>.wikipedia.org/w/api.php?prop=extracts&explaintext`` (plain text body)
_wrappers
    Small utility wrappers (sleep, etc.).

Public API (from each sub-module's own ``__all__``)
---------------------------------------------------
- :func:`get_json_with_retry`
- :func:`fetch_wikidata_sitelinks`
- :func:`fetch_sitelinks_batched`
- :func:`fetch_summary`
- :func:`fetch_extract`
- :func:`fetch_wikipedia_summary`
- :func:`fetch_wikipedia_extract`
"""
from __future__ import annotations

from . import _retry, batched_sitelinks, extracts, http_client, summary
from .._init_helpers import union_all
from ._retry import *  # noqa: F401, F403
from .batched_sitelinks import *  # noqa: F401, F403
from .extracts import *  # noqa: F401, F403
from .http_client import *  # noqa: F401, F403
from .summary import *  # noqa: F401, F403

__all__ = union_all(_retry, batched_sitelinks, extracts, http_client, summary)
