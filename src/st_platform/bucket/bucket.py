"""Deterministic bucketing (MurmurHash3 32-bit)."""

from __future__ import annotations


def murmur3_32(data: str, seed: int = 0) -> int:
    """MurmurHash3 32-bit (x86). Pure Python, no external deps."""
    c1 = 0xCC9E2D51
    c2 = 0x1B873593
    length = len(data.encode("utf-8"))
    h1 = seed & 0xFFFFFFFF
    # body
    for i in range(0, length - 3, 4):
        k1 = int.from_bytes(data.encode("utf-8")[i : i + 4], "little")
        k1 = (k1 * c1) & 0xFFFFFFFF
        k1 = ((k1 << 15) | (k1 >> 17)) & 0xFFFFFFFF
        k1 = (k1 * c2) & 0xFFFFFFFF
        h1 ^= k1
        h1 = ((h1 << 13) | (h1 >> 19)) & 0xFFFFFFFF
        h1 = (h1 * 5 + 0xE6546B64) & 0xFFFFFFFF
    # tail
    tail = data.encode("utf-8")[length - (length % 4) :]
    k1 = 0
    if len(tail) >= 3:
        k1 ^= tail[2] << 16
    if len(tail) >= 2:
        k1 ^= tail[1] << 8
    if len(tail) >= 1:
        k1 ^= tail[0]
        k1 = (k1 * c1) & 0xFFFFFFFF
        k1 = ((k1 << 15) | (k1 >> 17)) & 0xFFFFFFFF
        k1 = (k1 * c2) & 0xFFFFFFFF
        h1 ^= k1
    # finalization
    h1 ^= length
    h1 ^= h1 >> 16
    h1 = (h1 * 0x85EBCA6B) & 0xFFFFFFFF
    h1 ^= h1 >> 13
    h1 = (h1 * 0xC2B2AE35) & 0xFFFFFFFF
    h1 ^= h1 >> 16
    return h1 & 0xFFFFFFFF


def bucket(
    user_id: str,
    experiment_id: str,
    *,
    business_line: str = "default",
    salt: str = "",
    n_buckets: int = 2,
) -> int:
    if n_buckets < 2 or n_buckets > 100:
        raise ValueError("n_buckets must be between 2 and 100")
    key = f"{business_line}|{user_id}|{experiment_id}|{salt}"
    return murmur3_32(key) % n_buckets
