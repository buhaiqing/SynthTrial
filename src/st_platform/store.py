"""Content-addressed report store.

Implements AGENTS.md §9 A-5: ``content_id = sha256(canonical payload)`` and
same hash == same result. The store is append-only -- an existing entry is
never overwritten, and a re-save whose bytes disagree with what the hash
addresses is refused rather than silently clobbered, because the audit chain
is only as trustworthy as this layer.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from st_platform.common.types import sha256_hex

SUMMARY_FIELDS = ("task_id", "model_version", "baseline_model_version", "verdict", "created_at")


class StoreConflict(RuntimeError):
    """Existing content at this address differs from the payload being saved."""


class ReportStore:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def _canonical(self, payload: dict[str, Any]) -> str:
        return json.dumps(payload, sort_keys=True, default=str)

    def _path_for(self, content_hash: str) -> Path:
        return self._root / f"{content_hash}.json"

    def save(self, payload: dict[str, Any]) -> str:
        """Store ``payload``; return its content hash. Idempotent by content."""
        canonical = self._canonical(payload)
        content_hash = sha256_hex(canonical)
        path = self._path_for(content_hash)

        if path.exists():
            if path.read_text(encoding="utf-8") != canonical:
                raise StoreConflict(
                    f"{content_hash} already holds different content; refusing to "
                    "overwrite (append-only). The stored bytes were tampered with, or "
                    "the hash is colliding."
                )
            return content_hash

        self._root.mkdir(parents=True, exist_ok=True)
        # Write-then-rename so a crash never leaves a half-written file that
        # would later read as a complete, valid report.
        fd, tmp = tempfile.mkstemp(dir=str(self._root), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(canonical)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return content_hash

    def get(self, content_hash: str) -> dict[str, Any]:
        path = self._path_for(content_hash)
        if not path.exists():
            raise KeyError(content_hash)
        return json.loads(path.read_text(encoding="utf-8"))

    def exists(self, content_hash: str) -> bool:
        return self._path_for(content_hash).exists()

    def list_hashes(self) -> list[str]:
        if not self._root.exists():
            return []
        return sorted(p.stem for p in self._root.glob("*.json"))

    def summaries(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for h in self.list_hashes():
            try:
                payload = self.get(h)
            except (json.JSONDecodeError, OSError):
                # A corrupt or half-written entry is surfaced, never skipped
                # silently -- hiding it would make the listing untrustworthy.
                out.append({"hash": h, "corrupt": True})
                continue
            row = {"hash": h}
            for field in SUMMARY_FIELDS:
                if field in payload:
                    row[field] = payload[field]
            out.append(row)
        return out
