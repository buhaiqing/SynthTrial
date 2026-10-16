"""Coverage reporting for safety redline execution (st-safety)."""

from __future__ import annotations

from collections.abc import Iterable


def _to_id_set(value) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        # accept {id: ...} or mapping of rule objects
        out = set()
        for k, v in value.items():
            if isinstance(v, str):
                out.add(v)
            else:
                rid = getattr(v, "id", None)
                out.add(rid if rid is not None else str(k))
        return out
    out: set[str] = set()
    for item in value:
        rid = getattr(item, "id", None)
        if rid is None:
            rid = item
        out.add(rid if isinstance(rid, str) else str(rid))
    return out


class CoverageReport:
    """Coverage of registered (and evaluated) safety rules.

    Recall is computed over a *known-risk set* supplied by the caller;
    it never claims zero misses beyond what the registered set actually covers.
    """

    def __init__(
        self,
        *args,
        registered=None,
        evaluated=None,
        registered_rule_ids=None,
        evaluated_rule_ids=None,
        registered_rules=None,
        evaluated_rules=None,
        registered_ids=None,
        evaluated_ids=None,
        known_risks=None,
        known_risk_set=None,
        **kwargs,
    ) -> None:
        # positional: registered, evaluated, known_risks
        if len(args) >= 1 and registered is None:
            registered = args[0]
        if len(args) >= 2 and evaluated is None:
            evaluated = args[1]
        if len(args) >= 3 and known_risks is None:
            known_risks = args[2]

        registered = (
            registered
            if registered is not None
            else registered_rule_ids
            if registered_rule_ids is not None
            else registered_rules
            if registered_rules is not None
            else registered_ids
            if registered_ids is not None
            else kwargs.get("registered_rule_ids")
        )
        evaluated = (
            evaluated
            if evaluated is not None
            else evaluated_rule_ids
            if evaluated_rule_ids is not None
            else evaluated_rules
            if evaluated_rules is not None
            else evaluated_ids
            if evaluated_ids is not None
            else kwargs.get("evaluated_rule_ids")
        )

        # allow passing sets via kwargs common names
        if registered is None:
            registered = kwargs.get("rules")
        if evaluated is None:
            evaluated = kwargs.get("evaluated_rules")

        self.registered_rule_ids: set[str] = _to_id_set(registered)
        self.evaluated_rule_ids: set[str] = _to_id_set(evaluated)
        self.known_risks: set[str] = _to_id_set(
            known_risks if known_risks is not None else known_risk_set
        )

        # optional count overrides (in case ids unavailable)
        if "registered_count" in kwargs and kwargs["registered_count"] is not None:
            # pad only if counts exceed ids (best effort)
            n = int(kwargs["registered_count"])
            if n > len(self.registered_rule_ids):
                self.registered_rule_ids = self.registered_rule_ids | {
                    f"_reg_{i}" for i in range(len(self.registered_rule_ids), n)
                }
        if "evaluated_count" in kwargs and kwargs["evaluated_count"] is not None:
            n = int(kwargs["evaluated_count"])
            if n > len(self.evaluated_rule_ids):
                self.evaluated_rule_ids = self.evaluated_rule_ids | {
                    f"_eval_{i}" for i in range(len(self.evaluated_rule_ids), n)
                }

    # --- counts ---
    @property
    def covered_rule_count(self) -> int:
        return len(self.registered_rule_ids & self.evaluated_rule_ids)

    @property
    def covered_count(self) -> int:
        return self.covered_rule_count

    @property
    def uncovered_rule_count(self) -> int:
        return len(self.registered_rule_ids - self.evaluated_rule_ids)

    @property
    def uncovered_count(self) -> int:
        return self.uncovered_rule_count

    @property
    def uncovered_ratio(self) -> float:
        if not self.registered_rule_ids:
            return 0.0
        return self.uncovered_rule_count / len(self.registered_rule_ids)

    @property
    def coverage_ratio(self) -> float:
        if not self.registered_rule_ids:
            return 1.0 if not self.uncovered_rule_count else 0.0
        return self.covered_rule_count / len(self.registered_rule_ids)

    @property
    def registered_count(self) -> int:
        return len(self.registered_rule_ids)

    @property
    def evaluated_count(self) -> int:
        return len(self.evaluated_rule_ids)

    def recall(self, known_risks: Iterable | None = None) -> float:
        """Recall over a known-risk set (does NOT claim zero misses)."""
        risks = _to_id_set(known_risks) if known_risks is not None else self.known_risks
        if not risks:
            return 1.0
        hit = len(risks & self.registered_rule_ids)
        return hit / len(risks)

    def recall_evaluated(self, known_risks: Iterable | None = None) -> float:
        risks = _to_id_set(known_risks) if known_risks is not None else self.known_risks
        if not risks:
            return 1.0
        return len(risks & self.evaluated_rule_ids) / len(risks)

    def to_dict(self) -> dict:
        return {
            "registered_rule_ids": sorted(self.registered_rule_ids),
            "evaluated_rule_ids": sorted(self.evaluated_rule_ids),
            "covered_rule_count": self.covered_rule_count,
            "uncovered_rule_count": self.uncovered_rule_count,
            "uncovered_ratio": self.uncovered_ratio,
        }
