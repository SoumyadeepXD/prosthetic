"""EMG envelope normalization and health monitoring."""

from dataclasses import dataclass
from typing import Tuple, Optional, Deque
from collections import deque

@dataclass
class EMGCalibration:
    baseline_mv: float = 250.0
    mvc_mv: float = 2200.0
    saturation_mv: float = 3200.0

class EnvelopeNormalizer:
    """Normalizes raw envelope voltage readings into [0.0, 1.0] activation and checks signal health."""

    def __init__(
        self,
        flexor_cal: EMGCalibration,
        extensor_cal: EMGCalibration,
        stuck_window_size: int = 50,  # 50 samples @ 100 Hz = 0.5 s
    ):
        self.flexor_cal = flexor_cal
        self.extensor_cal = extensor_cal
        self.stuck_window_size = stuck_window_size
        self._flex_history: Deque[float] = deque(maxlen=stuck_window_size)
        self._ext_history: Deque[float] = deque(maxlen=stuck_window_size)
        self.last_fault_reason: Optional[str] = None

    def normalize(self, raw_flex_mv: float, raw_ext_mv: float) -> Tuple[float, float, bool]:
        """Normalize readings to activations in [0.0, 1.0].

        Returns:
            (a_flex, a_ext, is_healthy)
        """
        # 1. Saturation check
        if raw_flex_mv >= self.flexor_cal.saturation_mv:
            self.last_fault_reason = f"Flexor EMG saturated at {raw_flex_mv:.1f} mV"
            return 0.0, 0.0, False
        if raw_ext_mv >= self.extensor_cal.saturation_mv:
            self.last_fault_reason = f"Extensor EMG saturated at {raw_ext_mv:.1f} mV"
            return 0.0, 0.0, False

        # 2. Invalid negative check
        if raw_flex_mv < 0.0 or raw_ext_mv < 0.0:
            self.last_fault_reason = f"Negative EMG voltage ({raw_flex_mv:.1f}, {raw_ext_mv:.1f})"
            return 0.0, 0.0, False

        # 3. Sudden rail step check
        if len(self._flex_history) > 0 and abs(raw_flex_mv - self._flex_history[-1]) > 2000.0:
            self.last_fault_reason = "Sudden step to rail on flexor EMG"
            return 0.0, 0.0, False
        if len(self._ext_history) > 0 and abs(raw_ext_mv - self._ext_history[-1]) > 2000.0:
            self.last_fault_reason = "Sudden step to rail on extensor EMG"
            return 0.0, 0.0, False

        self._flex_history.append(raw_flex_mv)
        self._ext_history.append(raw_ext_mv)

        # 4. Stuck / Flat-line check (active only when window is full)
        if len(self._flex_history) == self.stuck_window_size:
            flex_range = max(self._flex_history) - min(self._flex_history)
            ext_range = max(self._ext_history) - min(self._ext_history)
            # If completely invariant across 50 consecutive samples
            if flex_range == 0.0:
                self.last_fault_reason = "Flexor EMG signal stuck / flat-lined"
                return 0.0, 0.0, False
            if ext_range == 0.0:
                self.last_fault_reason = "Extensor EMG signal stuck / flat-lined"
                return 0.0, 0.0, False

        span_flex = max(1.0, self.flexor_cal.mvc_mv - self.flexor_cal.baseline_mv)
        span_ext = max(1.0, self.extensor_cal.mvc_mv - self.extensor_cal.baseline_mv)

        a_flex = max(0.0, min(1.0, (raw_flex_mv - self.flexor_cal.baseline_mv) / span_flex))
        a_ext = max(0.0, min(1.0, (raw_ext_mv - self.extensor_cal.baseline_mv) / span_ext))

        self.last_fault_reason = None
        return a_flex, a_ext, True
