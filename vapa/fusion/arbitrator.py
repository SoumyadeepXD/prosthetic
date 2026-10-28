"""Shared-control fusion and arbitration logic.

HARD SAFETY INVARIANTS:
1. EMG supplies intent (close, open, hold, mode-switch).
2. Vision supplies context (grip profile, aperture preshape, force cap).
3. Vision alone CAN NEVER command or initiate a closing motion.
4. EMG OPEN unconditionally overrides any vision preshape or active closing motion.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
from ..emg.decoder import EMGIntent
from ..vision.distance_matrix import DistanceMatrixResult

@dataclass
class ArbitrationOutput:
    active_profile: str
    preshape_aperture: float  # [0.0 = fully open, 1.0 = fully closed]
    motion_command: str       # "OPEN", "CLOSE", "HOLD", "MODE_CYCLE"
    command_velocity: float   # [0.0 to 1.0]
    force_cap_grams: float

class SharedControlArbitrator:
    """Arbitrates between operator EMG intent and computer vision context."""

    def __init__(self, grip_profiles: Dict[str, Any], default_profile: str = "default"):
        self.grip_profiles = grip_profiles.get("profiles", {})
        self.default_profile = default_profile
        self.current_profile_name = default_profile

    def arbitrate(
        self,
        emg_intent: EMGIntent,
        emg_velocity: float,
        vision_profile: str,
        distance_result: Optional[DistanceMatrixResult],
        current_aperture: float,
    ) -> ArbitrationOutput:
        """Execute one cycle of arbitration."""
        # 1. Profile selection: fallback to default if vision profile unknown
        selected_profile = vision_profile if vision_profile in self.grip_profiles else self.default_profile
        prof_data = self.grip_profiles.get(selected_profile, self.grip_profiles.get(self.default_profile, {}))
        force_cap = float(prof_data.get("force_cap_grams", 300.0))

        # 2. Compute preshape aperture from distance
        # Far (> 0.6m) -> 0.0 (open). Close (near 0.15m) -> preshape target (e.g. 0.2)
        base_preshape = 0.2
        if "preshape" in prof_data:
            base_preshape = float(prof_data["preshape"].get("index", 0.2))

        preshape_target = 0.0
        if distance_result and distance_result.reach_confidence > 0.3:
            dist = distance_result.nearest_distance_m
            if dist < 0.60:
                frac = max(0.0, min(1.0, (0.60 - dist) / 0.45))
                # Preshape opens the hand towards base_preshape, NEVER past it
                preshape_target = frac * base_preshape

        # 3. Handle EMG Intent (EMG OPEN ALWAYS WINS)
        if emg_intent == EMGIntent.OPEN:
            return ArbitrationOutput(
                active_profile=selected_profile,
                preshape_aperture=0.0,  # Open hand
                motion_command="OPEN",
                command_velocity=emg_velocity,
                force_cap_grams=force_cap,
            )

        if emg_intent == EMGIntent.CLOSE:
            return ArbitrationOutput(
                active_profile=selected_profile,
                preshape_aperture=preshape_target,
                motion_command="CLOSE",
                command_velocity=emg_velocity,
                force_cap_grams=force_cap,
            )

        if emg_intent == EMGIntent.MODE_CYCLE:
            return ArbitrationOutput(
                active_profile=selected_profile,
                preshape_aperture=preshape_target,
                motion_command="MODE_CYCLE",
                command_velocity=0.0,
                force_cap_grams=force_cap,
            )

        # EMG is HOLD / rest
        # Hard Rule: Vision alone can NEVER command closing.
        # It may only maintain or open the preshape aperture.
        return ArbitrationOutput(
            active_profile=selected_profile,
            preshape_aperture=preshape_target,
            motion_command="HOLD",
            command_velocity=0.0,
            force_cap_grams=force_cap,
        )
