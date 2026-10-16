"""Orthogonal / multi-layer experiment architecture (M9 T-M9-06)."""

from __future__ import annotations

from dataclasses import dataclass, field

from .bucket import murmur3_32


@dataclass(frozen=True)
class Experiment:
    experiment_id: str
    layer_id: str
    weight: int = 1

    def __post_init__(self) -> None:
        if not self.experiment_id:
            raise ValueError("experiment_id must be non-empty")
        if not self.layer_id:
            raise ValueError("layer_id must be non-empty")
        if not isinstance(self.weight, int) or isinstance(self.weight, bool) or self.weight < 1:
            raise ValueError("weight must be a positive int")


@dataclass(frozen=True)
class Layer:
    layer_id: str
    experiments: tuple[Experiment, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.layer_id:
            raise ValueError("layer_id must be non-empty")
        seen: set[str] = set()
        for exp in self.experiments:
            if exp.layer_id != self.layer_id:
                raise ValueError(
                    f"experiment {exp.experiment_id!r} belongs to layer {exp.layer_id!r}, "
                    f"not {self.layer_id!r}"
                )
            if exp.experiment_id in seen:
                raise ValueError(f"duplicate experiment_id {exp.experiment_id!r} in layer {self.layer_id!r}")
            seen.add(exp.experiment_id)


def assign(
    user_id: str,
    layers: tuple[Layer, ...] | list[Layer],
    *,
    business_line: str = "default",
    base_salt: str = "",
) -> dict[str, str | None]:
    """Assign a user to at most one experiment per layer, independently across layers.

    Returns ``{layer_id: experiment_id | None}``. Layers with no experiments map to
    ``None``. Deterministic: same inputs -> same output in any process.
    """
    result: dict[str, str | None] = {}
    for layer in layers:
        experiments = layer.experiments
        if not experiments:
            result[layer.layer_id] = None
            continue
        total = sum(e.weight for e in experiments)
        slot = murmur3_32(f"{business_line}|{user_id}|{layer.layer_id}|{base_salt}") % total
        cumulative = 0
        chosen: str | None = None
        for exp in experiments:
            cumulative += exp.weight
            if slot < cumulative:
                chosen = exp.experiment_id
                break
        result[layer.layer_id] = chosen
    return result