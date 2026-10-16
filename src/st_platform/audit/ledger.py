"""Audit chain: append-only, hash-linked."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256


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
    def __init__(self, *, genesis_hash: str = "genesis") -> None:
        self._genesis = genesis_hash
        self._entries: list[AuditEntry] = []

    def append(self, event_type: str, payload: dict) -> AuditEntry:
        prev = self._entries[-1].hash if self._entries else self._genesis
        entry = AuditEntry(
            event_id=f"ae_{len(self._entries)}", event_type=event_type, payload=payload
        )
        entry.prev_hash = prev
        entry.hash = entry.compute_hash(prev)
        self._entries.append(entry)
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
        return [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "payload": e.payload,
                "created_at": e.created_at.isoformat(),
                "prev_hash": e.prev_hash,
                "hash": e.hash,
            }
            for e in self._entries
        ]

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
