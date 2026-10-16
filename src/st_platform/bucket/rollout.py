"""Gray release controller for SynthTrial P1 (st-bucket)."""

from __future__ import annotations

from threading import Lock

from .bucket import bucket


class RolloutError(ValueError):
    pass


class RolloutController:
    def __init__(self) -> None:
        self._percents: dict[str, int] = {}
        self._lock = Lock()

    def set_percent(self, experiment_id: str, percent: int) -> None:
        if not isinstance(percent, int) or isinstance(percent, bool):
            raise RolloutError("percent must be an int")
        if percent < 0 or percent > 100:
            raise RolloutError("percent must be between 0 and 100")
        with self._lock:
            self._percents[experiment_id] = percent

    def get_percent(self, experiment_id: str) -> int:
        with self._lock:
            return self._percents.get(experiment_id, 0)

    def is_enabled(
        self,
        user_id: str,
        experiment_id: str,
        *,
        business_line: str = "default",
        salt: str = "",
    ) -> bool:
        percent = self.get_percent(experiment_id)
        if percent <= 0:
            return False
        if percent >= 100:
            return True
        return bucket(user_id, experiment_id, business_line=business_line, salt=salt, n_buckets=100) < percent