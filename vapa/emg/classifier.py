"""Interface and temporal feature extractor for optional EMG classifier.

SAFETY & HARDWARE LIMITATION NOTE (Rev 2, Section 2.2):
---------------------------------------------------------
A standard raw EMG pattern-recognition classifier CANNOT run on this hardware architecture:
1. Sub-Nyquist Sampling: The ESP32 reads the ADS1115 via I2C in a round-robin schedule
   across 3 channels (A0 flexor, A1 extensor, A2 EEG), yielding ~100 Hz per channel.
   According to the Nyquist-Shannon sampling theorem, the maximum observable frequency is 50 Hz.
   Raw bipolar surface EMG contains meaningful spectral power up to 450-500 Hz, which requires
   sampling at >= 1000-2000 Hz.
2. Analog Pre-Processing: The MyoWare 2.0 sensor output connected to the ADS1115 is the
   envelope pin (ENV), which has already been analog rectified and low-pass filtered by an
   analog envelope detector circuit. The raw motor unit action potentials (MUAP) and
   high-frequency spectral features (such as Mean Frequency, Median Frequency, Zero Crossings,
   and Spectral Entropy) are physically eliminated before analog-to-digital conversion.

Consequently, any classification on this link MUST operate strictly on temporal envelope
features (e.g., envelope amplitude, envelope slope, envelope variance) and is DISABLED BY DEFAULT.
Threshold-based decoding is the primary, deterministic, and safe control method.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Deque
from collections import deque
import numpy as np

@dataclass
class EnvelopeFeatures:
    flex_mean: float = 0.0
    flex_max: float = 0.0
    flex_variance: float = 0.0
    flex_slope: float = 0.0
    ext_mean: float = 0.0
    ext_max: float = 0.0
    ext_variance: float = 0.0
    ext_slope: float = 0.0

class AbstractEMGClassifier(ABC):
    """Abstract interface for optional EMG classification."""

    @abstractmethod
    def is_enabled(self) -> bool:
        """Return True if classifier is enabled in configuration."""
        pass

    @abstractmethod
    def extract_features(self, flex_window: List[float], ext_window: List[float]) -> EnvelopeFeatures:
        """Extract statistical features from sliding envelope window."""
        pass

    @abstractmethod
    def predict(self, flex_window: List[float], ext_window: List[float]) -> Tuple[str, float]:
        """Predict gesture/intent ('OPEN', 'CLOSE', 'HOLD', 'MODE_CYCLE') and confidence [0..1]."""
        pass

class EnvelopeClassifier(AbstractEMGClassifier):
    """Disabled-by-default envelope feature extractor and heuristic/model classifier."""

    def __init__(self, enabled: bool = False, window_size: int = 15):
        self.enabled = enabled
        self.window_size = window_size
        self._flex_buf: Deque[float] = deque(maxlen=window_size)
        self._ext_buf: Deque[float] = deque(maxlen=window_size)

    def is_enabled(self) -> bool:
        return self.enabled

    def push_sample(self, norm_flex: float, norm_ext: float) -> None:
        """Push a normalized sample [0.0..1.0] into sliding window buffer."""
        self._flex_buf.append(norm_flex)
        self._ext_buf.append(norm_ext)

    def extract_features(self, flex_window: List[float], ext_window: List[float]) -> EnvelopeFeatures:
        """Extract time-domain envelope features across the window."""
        if not flex_window or not ext_window:
            return EnvelopeFeatures()

        f_arr = np.array(flex_window, dtype=np.float32)
        e_arr = np.array(ext_window, dtype=np.float32)

        f_slope = float(f_arr[-1] - f_arr[0]) / max(1, len(f_arr) - 1)
        e_slope = float(e_arr[-1] - e_arr[0]) / max(1, len(e_arr) - 1)

        return EnvelopeFeatures(
            flex_mean=float(np.mean(f_arr)),
            flex_max=float(np.max(f_arr)),
            flex_variance=float(np.var(f_arr)),
            flex_slope=f_slope,
            ext_mean=float(np.mean(e_arr)),
            ext_max=float(np.max(e_arr)),
            ext_variance=float(np.var(e_arr)),
            ext_slope=e_slope,
        )

    def predict(self, flex_window: Optional[List[float]] = None, ext_window: Optional[List[float]] = None) -> Tuple[str, float]:
        """Predict intent based on sliding window. Returns ('HOLD', 0.0) if disabled."""
        if not self.enabled:
            return "HOLD", 0.0

        f_win = list(self._flex_buf) if flex_window is None else flex_window
        e_win = list(self._ext_buf) if ext_window is None else ext_window

        if len(f_win) < self.window_size or len(e_win) < self.window_size:
            return "HOLD", 0.0

        feat = self.extract_features(f_win, e_win)

        # Basic envelope heuristic classification
        # Hard safety rule: extensor (open) priority
        if feat.ext_mean > 0.25 and feat.flex_mean > 0.25:
            return "MODE_CYCLE", min(feat.ext_mean, feat.flex_mean)
        elif feat.ext_mean > 0.25:
            return "OPEN", feat.ext_mean
        elif feat.flex_mean > 0.25:
            return "CLOSE", feat.flex_mean

        return "HOLD", 0.0
