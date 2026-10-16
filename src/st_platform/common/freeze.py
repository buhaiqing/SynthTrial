"""Deep-freezing for snapshot payloads.

Pydantic's ``frozen=True`` blocks attribute reassignment but NOT in-place
mutation of a nested container. That made a Task's ``params`` mutable after
creation, which let ``content_hash`` drift away from the snapshot it claims to
describe (AGENTS.md D-3). Reproduced: ``t.params["k"] = 9`` moved the hash from
74b86887061c to a2e16483b764.

``FrozenDict`` stays a real ``dict`` so ``json.dumps`` / Pydantic validation
keep working unchanged -- it only refuses mutation.
"""

from __future__ import annotations

from typing import Any


class FrozenDict(dict):
    """A dict that refuses every mutating operation."""

    __slots__ = ()

    def _immutable(self, *_args: Any, **_kwargs: Any) -> None:
        raise TypeError(
            "snapshot state is immutable (content-addressed); build a new snapshot "
            "instead of mutating this one"
        )

    __setitem__ = _immutable
    __delitem__ = _immutable
    __ior__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable


def freeze(value: Any) -> Any:
    """Recursively convert dicts to FrozenDict and lists to tuples."""
    if isinstance(value, dict):
        return FrozenDict({k: freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    if isinstance(value, set):
        return frozenset(freeze(v) for v in value)
    return value
