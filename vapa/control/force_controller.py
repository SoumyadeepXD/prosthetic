"""Finger force PI controller with anti-windup and force cap."""

from dataclasses import dataclass
from typing import Dict, Tuple

@dataclass
class PIConfig:
    kp: float = 0.002
    ki: float = 0.0005
    anti_windup_limit: float = 0.3
    backoff_step: float = 0.05

class FingerForceController:
    """PI force controller running at 100 Hz to regulate finger closing against FSR force feedback."""

    def __init__(self, pi_config: PIConfig = PIConfig()):
        self.cfg = pi_config
        self.integral_errors: Dict[str, float] = {
            "thumb": 0.0, "index": 0.0, "middle": 0.0, "ring": 0.0, "little": 0.0
        }

    @property
    def integrals(self) -> Dict[str, float]:
        return self.integral_errors

    def reset(self) -> None:
        for f in self.integral_errors:
            self.integral_errors[f] = 0.0

    def compute_finger_command(
        self,
        finger_name: str,
        current_pos: float,
        target_pos: float,
        measured_force: float,
        target_force: float,
        force_cap: float,
        dt_s: float = 0.01,
    ) -> float:
        """Compute next finger position [0.0 = open, 1.0 = closed].

        If force exceeds force_cap, back off immediately.
        If closing, adjust step size based on force error.
        If opening (target_pos < current_pos), bypass force control.
        """
        # If opening, bypass force regulation and open directly
        if target_pos < current_pos:
            self.integral_errors[finger_name] = 0.0
            return target_pos

        # If measured force exceeds safe force cap, back off
        if measured_force >= force_cap:
            backoff_pos = max(0.0, current_pos - self.cfg.backoff_step)
            self.integral_errors[finger_name] = 0.0
            return backoff_pos

        # If already at or above target force, hold position
        force_err = target_force - measured_force
        if measured_force >= target_force:
            # Force reached, hold
            return current_pos

        # Update integral error with anti-windup
        self.integral_errors[finger_name] += force_err * dt_s
        self.integral_errors[finger_name] = max(
            -self.cfg.anti_windup_limit,
            min(self.cfg.anti_windup_limit, self.integral_errors[finger_name])
        )

        pi_out = self.cfg.kp * force_err + self.cfg.ki * self.integral_errors[finger_name]
        step = max(0.0, min(0.02, pi_out))  # Rate limit closing step

        next_pos = min(target_pos, current_pos + step)
        return next_pos
