"""Common types and hashing for SynthTrial P0 (offline eval core)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class Versioned(BaseModel):
    """Base with strict model config; forbid extras."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SafetyVerdictTier(str, Enum):
    BLOCK = "BLOCK"
    WARN = "WARN"
    PASS = "PASS"


class AuditEvent(Versioned):
    event_id: str
    prev_hash: str
    payload_hash: str
    event_type: str
    actor: str = "system"
    created_at: datetime = Field(default_factory=utcnow)

    def chain_hash(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json", exclude={"created_at"}),
            sort_keys=True,
            default=str,
        )
        return sha256_hex(canonical + ":" + self.created_at.isoformat())

    @staticmethod
    def compute_event_hash(
        prev_hash: str, payload_hash: str, event_type: str, actor: str, created_at_iso: str
    ) -> str:
        canonical = json.dumps(
            {
                "prev_hash": prev_hash,
                "payload_hash": payload_hash,
                "event_type": event_type,
                "actor": actor,
            },
            sort_keys=True,
        )
        return sha256_hex(canonical + ":" + created_at_iso)


def audit_hash(prev_hash: str, payload: Any) -> str:
    """Content-addressed hash for audit linked list."""
    return sha256_hex(prev_hash + ":" + json.dumps(payload, sort_keys=True, default=str))
