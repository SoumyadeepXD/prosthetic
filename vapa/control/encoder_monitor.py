"""Closed-loop encoder monitoring, stall detection, and uncommanded motion detection."""

import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

@dataclass
class MonitorConfig:
    stall_error_threshold_deg: float = 12.0  # Mismatch threshold
    min_velocity_deg_s: float = 3.0          # Below this is considered stationary
    uncommanded_velocity_deg_s: float = 20.0 # Above this while commanded to hold is uncommanded motion
    stall_timeout_s: float = 0.35            # Sustained stationary mismatch before fault
    drift_timeout_s: float = 0.25            # Sustained uncommanded motion before fault

class JointMismatchTracker:
    """Tracks command vs feedback for a single joint."""

    def __init__(self, joint_name: str, cfg: MonitorConfig):
        self.joint_name = joint_name
        self.cfg = cfg

        self.last_measured_deg: Optional[float] = None
        self.last_commanded_deg: Optional[float] = None
        self.stall_timer_s: float = 0.0
        self.drift_timer_s: float = 0.0

    def reset(self) -> None:
        self.last_measured_deg = None
        self.last_commanded_deg = None
        self.stall_timer_s = 0.0
        self.drift_timer_s = 0.0

    def update(
        self,
        commanded_deg: float,
        measured_deg: float,
        dt_s: float
    ) -> Tuple[bool, Optional[str]]:
        """Update joint tracking. Returns (has_fault, fault_reason)."""
        if dt_s <= 0:
            return False, None

        if self.last_measured_deg is None or self.last_commanded_deg is None:
            self.last_measured_deg = measured_deg
            self.last_commanded_deg = commanded_deg
            return False, None

        measured_vel = abs(measured_deg - self.last_measured_deg) / dt_s
        commanded_vel = abs(commanded_deg - self.last_commanded_deg) / dt_s
        pos_error = abs(commanded_deg - measured_deg)

        self.last_measured_deg = measured_deg
        self.last_commanded_deg = commanded_deg

        # Check 1: Commanded but not moving (Stall)
        if pos_error > self.cfg.stall_error_threshold_deg and measured_vel < self.cfg.min_velocity_deg_s:
            self.stall_timer_s += dt_s
            if self.stall_timer_s >= self.cfg.stall_timeout_s:
                return True, (
                    f"Joint {self.joint_name} stall detected: commanded={commanded_deg:.1f}°, "
                    f"measured={measured_deg:.1f}°, err={pos_error:.1f}° for {self.stall_timer_s:.2f}s"
                )
        else:
            self.stall_timer_s = max(0.0, self.stall_timer_s - dt_s * 2.0)

        # Check 2: Moving without command (Uncommanded motion / slippage)
        if commanded_vel < 1.0 and measured_vel > self.cfg.uncommanded_velocity_deg_s:
            self.drift_timer_s += dt_s
            if self.drift_timer_s >= self.cfg.drift_timeout_s:
                return True, (
                    f"Joint {self.joint_name} uncommanded motion detected: velocity={measured_vel:.1f}°/s "
                    f"while commanded stationary for {self.drift_timer_s:.2f}s"
                )
        else:
            self.drift_timer_s = max(0.0, self.drift_timer_s - dt_s * 2.0)

        return False, None

class EncoderMonitor:
    """Monitors closed-loop AS5600 encoder feedback against commanded servo positions."""

    def __init__(self, cfg: MonitorConfig = MonitorConfig()):
        self.cfg = cfg
        self.monitored_joints = ["finger_group", "wrist_flex", "wrist_rotate", "forearm_rotation"]
        self.trackers = {j: JointMismatchTracker(j, cfg) for j in self.monitored_joints}

    def reset(self) -> None:
        for t in self.trackers.values():
            t.reset()

    def update(
        self,
        commanded_angles: Dict[str, float],
        measured_angles: Dict[str, float],
        dt_s: float
    ) -> Tuple[bool, Optional[str]]:
        """Update all monitored joints. Returns (fault_detected, fault_description)."""
        for joint in self.monitored_joints:
            if joint in commanded_angles and joint in measured_angles:
                cmd = commanded_angles[joint]
                meas = measured_angles[joint]
                fault, reason = self.trackers[joint].update(cmd, meas, dt_s)
                if fault:
                    return True, reason

        return False, None
