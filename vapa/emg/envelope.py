"""EMG envelope normalization and health monitoring."""

from dataclasses import dataclass
from typing import Tuple

@dataclass
class EMGCalibration:
    baseline_mv: float = 250.0
    mvc_mv: float = 2200.0
    saturation_mv: float = 3200.0

class EnvelopeNormalizer:
    """Normalizes raw envelope voltage readings into [0.0, 1.0] activation."""

    def __init__(self, flexor_cal: EMGCalibration, extensor_cal: EMGCalibration):
        self.flexor_cal = flexor_cal
        self.extensor_cal = extensor_cal

    def normalize(self, raw_flex_mv: float, raw_ext_mv: float) -> Tuple[float, float, bool]:
        """Normalize readings to activations in [0.0, 1.0].

        Returns:
            (a_flex, a_ext, is_healthy)
        """
        # Check saturation or negative invalidity
        if raw_flex_mv >= self.flexor_cal.saturation_mv or raw_ext_mv >= self.extensor_cal.saturation_mv:
            return 0.0, 0.0, False
        if raw_flex_mv < 0.0 or raw_ext_mv < 0.0:
            return 0.0, 0.0, False

        span_flex = max(1.0, self.flexor_cal.mvc_mv - self.flexor_cal.baseline_mv)
        span_ext = max(1.0, self.extensor_cal.mvc_mv - self.extensor_cal.baseline_mv)

        a_flex = max(0.0, min(1.0, (raw_flex_mv - self.flexor_cal.baseline_mv) / span_flex))
        a_ext = max(0.0, min(1.0, (raw_ext_mv - self.extensor_cal.baseline_mv) / span_ext))

        return a_flex, a_ext, True
