"""Slew rate limiter for smooth and safe servo transitions."""

from typing import Dict

class SlewRateLimiter:
    """Enforces maximum rate of change (units/second) on commanded values."""

    def __init__(self, max_rates: Dict[str, float]):
        self.max_rates = max_rates
        self._current_values: Dict[str, float] = {}

    def reset(self, initial_values: Dict[str, float]) -> None:
        self._current_values = dict(initial_values)

    def update(self, servo_name: str, target_val: float, dt_s: float) -> float:
        if servo_name not in self._current_values:
            self._current_values[servo_name] = target_val
            return target_val

        curr = self._current_values[servo_name]
        max_rate = self.max_rates.get(servo_name, 1.0)
        max_step = max_rate * dt_s

        diff = target_val - curr
        if abs(diff) <= max_step:
            next_val = target_val
        else:
            direction = 1.0 if diff > 0 else -1.0
            next_val = curr + direction * max_step

        self._current_values[servo_name] = next_val
        return next_val
