"""Audit chain: append-only, hash-linked.

In-memory by default (``AuditLedger()``); with ``path=`` every entry is also appended
to an append-only JSONL file and reloaded on open, so the chain continues across
processes. A chain that restarts at genesis on each run verifies while proving
nothing across runs, so reopening must link to the last stored hash.

The file is ``.jsonl`` and not ``.json`` on purpose: ``ReportStore.list_hashes()``
globs ``*.json``, so a ``.json`` audit file would be listed as if it were a report.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path


@dataclass
class AuditEntry:
    event_id: str
    event_type: str
    payload: dict
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    prev_hash: str = ""
    hash: str = ""

    def compute_hash(self, prev: str) -> str:
        canonical = json.dumps(self.payload, sort_keys=True, default=str)
        base = (prev + ":" + canonical + ":" + self.created_at.isoformat()).encode()
        return sha256(base).hexdigest()


class AuditChainError(Exception):
    pass


class AuditLedger:
    def __init__(self, *, genesis_hash: str = "genesis", path: str | Path | None = None) -> None:
        self._genesis = genesis_hash
        self._entries: list[AuditEntry] = []
        self._path = Path(path) if path is not None else None
        if self._path is not None:
            self._load()

    @property
    def path(self) -> Path | None:
        """Backing file, or ``None`` for the in-memory ledger."""
        return self._path

    @staticmethod
    def _record(entry: AuditEntry) -> dict:
        """The on-disk / exported shape of one entry — one definition, two callers."""
        return {
            "event_id": entry.event_id,
            "event_type": entry.event_type,
            "payload": entry.payload,
            "created_at": entry.created_at.isoformat(),
            "prev_hash": entry.prev_hash,
            "hash": entry.hash,
        }

    def _load(self) -> None:
        assert self._path is not None
        if not self._path.exists():
            return
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            self._entries.append(
                AuditEntry(
                    event_id=rec["event_id"],
                    event_type=rec["event_type"],
                    payload=rec["payload"],
                    created_at=datetime.fromisoformat(rec["created_at"]),
                    prev_hash=rec["prev_hash"],
                    hash=rec["hash"],
                )
            )

    def append(self, event_type: str, payload: dict) -> AuditEntry:
        prev = self._entries[-1].hash if self._entries else self._genesis
        entry = AuditEntry(
            event_id=f"ae_{len(self._entries)}", event_type=event_type, payload=payload
        )
        entry.prev_hash = prev
        entry.hash = entry.compute_hash(prev)
        self._entries.append(entry)
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(self._record(entry), sort_keys=True, default=str) + "\n")
        return entry

    def verify(self) -> bool:
        prev = self._genesis
        for e in self._entries:
            if e.prev_hash != prev:
                return False
            if e.hash != e.compute_hash(prev):
                return False
            prev = e.hash
        return True

    def export(self) -> list[dict]:
        return [self._record(e) for e in self._entries]

    def clone(self):
        out = AuditLedger(genesis_hash=self._genesis)
        out._entries = [AuditEntry(**e.__dict__) for e in self._entries]
        return out

    @property
    def entries(self) -> list[AuditEntry]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


def has_tamper(entries_before: AuditLedger) -> bool:
    # helper for tests
    try:
        entries_before.verify()
        return False
    except (ValueError, KeyError, RuntimeError):
        return True
