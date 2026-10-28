"""Grip executor applying grip profiles and coordinates joint outputs."""

from typing import Dict, Any
from .servo_mapper import ServoMapper
from .slew_limiter import SlewRateLimiter
from .force_controller import FingerForceController

class GripExecutor:
    """Executes grip profiles with slew limits, force control, and state gating."""

    def __init__(
        self,
        mapper: ServoMapper,
        slew_limiter: SlewRateLimiter,
        force_controller: FingerForceController,
    ):
        self.mapper = mapper
        self.slew_limiter = slew_limiter
        self.force_controller = force_controller
        self.current_finger_positions: Dict[str, float] = {
            "thumb": 0.0, "index": 0.0, "middle": 0.0, "ring": 0.0, "little": 0.0
        }
        self.current_joint_angles: Dict[str, float] = {
            "wrist_flex": 0.0, "wrist_rotate": 0.0, "wrist_bend": 0.0, "forearm_rotation": 0.0
        }

    def reset(self) -> None:
        for f in self.current_finger_positions:
            self.current_finger_positions[f] = 0.0
        for j in self.current_joint_angles:
            self.current_joint_angles[j] = 0.0
        self.force_controller.reset()
