"""Shared helpers used by every subpackage ``__init__.py``.

Why
---
Without this, each subpackage's ``__init__.py`` had to compute the
union of its modules' ``__all__`` lists by hand::

    __all__ = sum(
        (getattr(m, "__all__", []) for m in (a, b, c)),
        [],
    )

That's identical boilerplate in 5 places. The :func:`union_all`
helper below factors it out and adds two small wins:

1.  Preserves order while de-duplicating.
2.  Skips the special name ``"annotations"`` (some modules inject it
    when they use ``from __future__ import annotations``).
"""
from __future__ import annotations

from types import ModuleType


_SKIP = {"annotations"}


def union_all(*modules: ModuleType) -> list[str]:
    """Return the in-order union of every module's ``__all__``.

    Names listed in :data:`_SKIP` are excluded. Order is the order in
    which the modules are passed; within a module, the order of its
    own ``__all__`` is preserved. Duplicates (a name re-exported by
    two modules) keep the first occurrence.
    """
    seen: set[str] = set()
    out: list[str] = []
    for m in modules:
        for sym in getattr(m, "__all__", ()):
            if sym in _SKIP or sym in seen:
                continue
            seen.add(sym)
            out.append(sym)
    return out


__all__ = ["union_all"]
