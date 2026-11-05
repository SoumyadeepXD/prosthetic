"""FSR402 non-linear force calibration and sensor plausibility monitoring.

Maps raw 12-bit ADC counts (0..4095) to calibrated grams force using per-sensor
piecewise calibration curves from config/fsr.yaml.
Detects open-circuit disconnections and short-circuit faults.
"""

from dataclasses import dataclass
from typing import Dict, Any, Tuple, List, Sequence, Optional
import numpy as np
import logging

logger = logging.getLogger(__name__)

FINGER_NAMES = ["thumb", "index", "middle", "ring", "little"]


@dataclass
class FSRCalibrationCurve:
    finger_name: str
    pin: int
    baseline_raw: int
    noise_margin: int
    max_raw: int
    raw_points: np.ndarray
    force_points: np.ndarray

    def raw_to_grams(self, raw_adc: int) -> Tuple[float, bool, Optional[str]]:
        """Convert single raw ADC reading to calibrated grams-force.

        Returns:
            (force_grams, is_plausible, fault_description)
        """
        # 1. Hardware Plausibility Checks
        # ADC reading of < 15 implies detached pull-down / broken trace
        if raw_adc < 10:
            return 0.0, False, f"FSR {self.finger_name} open-circuit / disconnected (raw ADC={raw_adc})"

        # ADC reading of >= 4090 indicates short circuit directly to 3.3V rail
        if raw_adc >= 4090:
            return 1000.0, False, f"FSR {self.finger_name} short-circuit to VDD (raw ADC={raw_adc})"

        # 2. Deadband / Baseline Noise Filtering
        deadband = self.baseline_raw + self.noise_margin
        if raw_adc <= deadband:
            return 0.0, True, None

        # 3. Piecewise Monotonic Interpolation
        # Clamp raw_adc within rated curve range
        clamped_adc = min(float(raw_adc), float(self.max_raw))
        force_g = float(np.interp(clamped_adc, self.raw_points, self.force_points))

        # Extrapolate slightly if over max_raw up to 4080
        if raw_adc > self.max_raw:
            extra_ratio = (raw_adc - self.max_raw) / 500.0
            force_g += extra_ratio * 150.0

        return max(0.0, round(force_g, 2)), True, None


class FSRCalibrator:
    """Manages calibrated force estimation across all 5 prosthetic fingertips."""

    def __init__(self, fsr_config: Dict[str, Any]):
        self.curves: Dict[str, FSRCalibrationCurve] = {}
        sensor_cfgs = fsr_config.get("sensors", {})

        for name in FINGER_NAMES:
            cfg = sensor_cfgs.get(name, {})
            cal_pts = cfg.get("calibration_points", [
                [50, 0], [500, 50], [1500, 200], [2800, 500], [3800, 1000]
            ])
            pts_array = np.array(cal_pts, dtype=np.float32)
            # Ensure sorted by raw ADC
            sorted_indices = np.argsort(pts_array[:, 0])
            sorted_pts = pts_array[sorted_indices]

            self.curves[name] = FSRCalibrationCurve(
                finger_name=name,
                pin=int(cfg.get("pin", 32)),
                baseline_raw=int(cfg.get("baseline_raw", 50)),
                noise_margin=int(cfg.get("noise_margin", 80)),
                max_raw=int(cfg.get("max_raw", 3800)),
                raw_points=sorted_pts[:, 0],
                force_points=sorted_pts[:, 1],
            )

        self.last_faults: List[str] = []

    def convert_readings(self, raw_fsr_tuple: Sequence[int]) -> Tuple[Dict[str, float], bool]:
        """Convert a 5-element tuple of raw ADC readings into fingertip force dictionary.

        Args:
            raw_fsr_tuple: 5-tuple of integers [thumb, index, middle, ring, little]

        Returns:
            (force_grams_dict, all_plausible)
        """
        forces: Dict[str, float] = {}
        all_plausible = True
        self.last_faults.clear()

        for idx, finger in enumerate(FINGER_NAMES):
            raw_val = raw_fsr_tuple[idx] if idx < len(raw_fsr_tuple) else 50
            curve = self.curves[finger]
            grams, plausible, err = curve.raw_to_grams(int(raw_val))
            forces[finger] = grams
            if not plausible:
                all_plausible = False
                if err:
                    self.last_faults.append(err)

        return forces, all_plausible
