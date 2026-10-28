"""Servo mapping, calibration gating, and command dispatch."""

from dataclasses import dataclass
from typing import Dict, Any, Optional
import logging
from ..hal.pca9685 import AbstractPCA9685

logger = logging.getLogger(__name__)

@dataclass
class ServoCalibration:
    channel: int
    model: str
    pulse_min_us: float
    pulse_neutral_us: float
    pulse_max_us: float
    angle_min_deg: float
    angle_max_deg: float
    direction: int
    max_slew_rate_deg_s: float
    home_position: float
    calibrated: bool = False
    has_encoder: bool = True

class ServoMapper:
    """Translates normalized positions (0.0 to 1.0) and joint angles into clamped PWM pulses."""

    def __init__(self, servo_configs: Dict[str, Any]):
        self.servos: Dict[str, ServoCalibration] = {}
        for name, cfg in servo_configs.get("servos", {}).items():
            self.servos[name] = ServoCalibration(
                channel=cfg["channel"],
                model=cfg.get("model", "MG996R"),
                pulse_min_us=float(cfg.get("pulse_min_us", 1000.0)),
                pulse_neutral_us=float(cfg.get("pulse_neutral_us", 1500.0)),
                pulse_max_us=float(cfg.get("pulse_max_us", 2000.0)),
                angle_min_deg=float(cfg.get("angle_min_deg", 0.0)),
                angle_max_deg=float(cfg.get("angle_max_deg", 90.0)),
                direction=int(cfg.get("direction", 1)),
                max_slew_rate_deg_s=float(cfg.get("max_slew_rate_deg_s", 180.0)),
                home_position=float(cfg.get("home_position", 0.0)),
                calibrated=bool(cfg.get("calibrated", False)),
                has_encoder=bool(cfg.get("has_encoder", True)),
            )

    def normalized_to_pulse(self, servo_name: str, normalized_pos: float) -> float:
        """Map normalized [0.0 = open/min, 1.0 = closed/max] to pulse in microseconds."""
        servo = self.servos[servo_name]
        # Until calibrated, only neutral is permitted
        if not servo.calibrated:
            return servo.pulse_neutral_us

        clamped = max(0.0, min(1.0, normalized_pos))
        if servo.direction < 0:
            clamped = 1.0 - clamped
        pulse = servo.pulse_min_us + clamped * (servo.pulse_max_us - servo.pulse_min_us)
        return max(servo.pulse_min_us, min(servo.pulse_max_us, pulse))

    def degrees_to_pulse(self, servo_name: str, deg: float) -> float:
        """Map joint degrees to pulse microseconds."""
        servo = self.servos[servo_name]
        if not servo.calibrated:
            return servo.pulse_neutral_us

        clamped_deg = max(servo.angle_min_deg, min(servo.angle_max_deg, deg))
        span_deg = servo.angle_max_deg - servo.angle_min_deg
        if span_deg == 0:
            return servo.pulse_neutral_us

        frac = (clamped_deg - servo.angle_min_deg) / span_deg
        if servo.direction < 0:
            frac = 1.0 - frac
        pulse = servo.pulse_min_us + frac * (servo.pulse_max_us - servo.pulse_min_us)
        return max(servo.pulse_min_us, min(servo.pulse_max_us, pulse))
