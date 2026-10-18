"""Assignment/exposure reconciliation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class AssignmentEvent:
    user_id: str
    experiment_id: str
    group: str


@dataclass(frozen=True)
class ExposureEvent:
    user_id: str
    experiment_id: str


def reconcile(
    assignments: Iterable[AssignmentEvent],
    exposures: Iterable[ExposureEvent],
) -> dict:
    a_list = list(assignments)
    e_list = list(exposures)
    exposed_keys = {(e.user_id, e.experiment_id) for e in e_list}
    missing = [a.user_id for a in a_list if (a.user_id, a.experiment_id) not in exposed_keys]
    a_count = len(a_list)
    missing_count = len(missing)
    ratio = missing_count / a_count if a_count else 0.0
    return {
        "assignment_count": a_count,
        "exposure_count": len(e_list),
        "missing_exposure_count": missing_count,
        "missing_exposure_ratio": ratio,
        "missing_user_ids": missing,
    }