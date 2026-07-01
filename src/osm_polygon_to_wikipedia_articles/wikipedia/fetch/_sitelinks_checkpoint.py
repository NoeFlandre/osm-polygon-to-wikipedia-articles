"""Resumable checkpoint for batched Wikidata sitelinks fetches.

The new pipeline persists each batch's sitelinks to a side-channel
file *as soon as it succeeds*, so a kill / crash at any point loses
at most one in-flight batch of work.  On restart, the pipeline
reads the checkpoint, takes the union with the new fetches, and
continues from where it left off.

File format
-----------
One JSON record per line::

    {"qid": "Q42", "sitelinks": {"enwiki": {"title": "..."}}}

The file is append-only with a periodic temp-file + rename compaction
to keep the on-disk size bounded.  Atomicity: a reader that opens
the file mid-write either sees the pre-rename or post-rename state
(the rename syscall is atomic on POSIX), never a partial line.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Iterable


class SitelinksCheckpoint:
    """Resumable JSONL checkpoint of ``{qid: sitelinks}``.

    Parameters
    ----------
    path
        File to read from / append to.  Created on first ``save``.
    compact_every
        How many ``save`` calls between full file compactions
        (rewrites the file with one line per QID, in order).
        Default 200 — small enough to keep the file bounded even
        when the run is long; large enough to amortise the rewrite.
    """

    def __init__(self, path: Path, compact_every: int = 200) -> None:
        self.path = Path(path)
        self.compact_every = compact_every
        self._writes_since_compact = 0
        self._fp = None
        self._in_memory: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "SitelinksCheckpoint":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._fp is not None:
            self._fp.close()
            self._fp = None

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def _ensure_open(self) -> None:
        if self._fp is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # 'a' so concurrent readers (e.g. monitoring tools) can tail
            self._fp = self.path.open("a", buffering=1)  # line-buffered

    def save(self, qid: str, sitelinks: dict) -> None:
        """Append or overwrite a QID's sitelinks.

        In-memory we keep a dict for O(1) overwrite; on disk we
        always append (one line per save), and periodically compact.
        """
        self._ensure_open()
        self._in_memory[qid] = sitelinks
        rec = json.dumps({"qid": qid, "sitelinks": sitelinks},
                         separators=(",", ":"))
        # Sanity: one line per record — no embedded newlines.
        assert "\n" not in rec
        self._fp.write(rec + "\n")
        self._writes_since_compact += 1
        if self._writes_since_compact >= self.compact_every:
            self._compact_locked()

    def _compact_locked(self) -> None:
        """Rewrite the file with one line per QID, in memory order.

        Atomic: write to a temp file in the same directory then
        ``os.replace`` it.  The reader always sees either the old
        or new version, never a partial file.
        """
        if self._fp is not None:
            self._fp.flush()
        if not self._in_memory:
            return
        fd, tmp_path = tempfile.mkstemp(
            prefix=self.path.name + ".",
            suffix=".tmp",
            dir=str(self.path.parent) if self.path.parent.exists() else ".",
        )
        try:
            with os.fdopen(fd, "w") as tf:
                for qid, sl in self._in_memory.items():
                    rec = json.dumps({"qid": qid, "sitelinks": sl},
                                     separators=(",", ":"))
                    tf.write(rec + "\n")
                tf.flush()
                os.fsync(tf.fileno())
            os.replace(tmp_path, self.path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        self._writes_since_compact = 0
        # Reopen the append handle pointing at the new file.
        if self._fp is not None:
            self._fp.close()
        self._fp = self.path.open("a", buffering=1)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def load(self) -> dict[str, dict]:
        """Return the full ``{qid: sitelinks}`` map from the file.

        Filters out entries whose sitelinks dict contains a
        ``_missing`` key — those are treated as "not done" so the
        resilient layer re-fetches them on the next run.  Empty
        sitelinks (``{}``) is a real "no sitelinks" answer and is
        kept.

        Replaces the in-memory cache; future ``save`` calls
        overwrite into the same cache.
        """
        out: dict[str, dict] = {}
        if not self.path.exists():
            self._in_memory = out
            return out
        with self.path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except (ValueError, json.JSONDecodeError):
                    # Corrupted line — skip rather than fail the
                    # whole load (the user can investigate manually).
                    continue
                qid = rec.get("qid")
                sl = rec.get("sitelinks")
                if not (isinstance(qid, str) and isinstance(sl, dict)):
                    continue
                # Re-fetch QIDs whose previous run ended in a
                # ``_missing`` marker — those are transient
                # failures, not authoritative answers.
                if "_missing" in sl:
                    continue
                out[qid] = sl
        self._in_memory = out
        return out

    def done_qids(self) -> set[str]:
        """Return the set of QIDs already saved."""
        if not self._in_memory:
            self.load()
        return set(self._in_memory.keys())

    def filter_pending(self, qids: Iterable[str]) -> list[str]:
        """Return the QIDs that are NOT yet in the checkpoint."""
        if not self._in_memory:
            self.load()
        return [q for q in qids if q not in self._in_memory]

    def size_bytes(self) -> int:
        if self.path.exists():
            return self.path.stat().st_size
        return 0


__all__ = ["SitelinksCheckpoint"]
