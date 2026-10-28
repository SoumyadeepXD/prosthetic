"""EMG intent decoder (threshold-based with hysteresis and mode-switching)."""

from enum import Enum, auto
from dataclasses import dataclass
from typing import Tuple

class EMGIntent(Enum):
    HOLD = auto()
    CLOSE = auto()
    OPEN = auto()
    MODE_CYCLE = auto()

@dataclass
class DecoderConfig:
    flex_act_threshold: float = 0.25
    flex_deact_threshold: float = 0.15
    ext_act_threshold: float = 0.25
    ext_deact_threshold: float = 0.15
    co_contract_hold_s: float = 0.60
    min_dwell_s: float = 0.10

class ThresholdEMGDecoder:
    """Decodes normalized activations into user intent."""

    def __init__(self, cfg: DecoderConfig = DecoderConfig()):
        self.cfg = cfg
        self._flex_active = False
        self._ext_active = False
        self._co_contract_timer = 0.0

    def decode(self, a_flex: float, a_ext: float, dt_s: float) -> Tuple[EMGIntent, float]:
        """Decode activations into (intent, velocity_factor).

        Velocity factor is in [0.0, 1.0].
        Hard rule: OPEN unconditionally wins over CLOSE.
        """
        # Hysteresis update
        if not self._flex_active and a_flex >= self.cfg.flex_act_threshold:
            self._flex_active = True
        elif self._flex_active and a_flex <= self.cfg.flex_deact_threshold:
            self._flex_active = False

        if not self._ext_active and a_ext >= self.cfg.ext_act_threshold:
            self._ext_active = True
        elif self._ext_active and a_ext <= self.cfg.ext_deact_threshold:
            self._ext_active = False

        # Check co-contraction (both active)
        if self._flex_active and self._ext_active:
            self._co_contract_timer += dt_s
            if self._co_contract_timer >= self.cfg.co_contract_hold_s:
                self._co_contract_timer = 0.0
                return EMGIntent.MODE_CYCLE, 0.0
            return EMGIntent.HOLD, 0.0
        else:
            self._co_contract_timer = 0.0

        # Hard rule: extensor (OPEN) always beats flexor (CLOSE)
        if self._ext_active:
            return EMGIntent.OPEN, a_ext

        if self._flex_active:
            return EMGIntent.CLOSE, a_flex

        return EMGIntent.HOLD, 0.0
