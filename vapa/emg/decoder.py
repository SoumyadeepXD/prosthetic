"""EMG intent decoder (two-site threshold-based with hysteresis, dwell, and mode-switching)."""

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
    """Decodes normalized muscle activations [0.0..1.0] into user intent.

    Safety Invariants:
    1. Extensor (OPEN) unconditionally overrides Flexor (CLOSE).
    2. Hysteresis prevents rapid toggling around the activation threshold.
    3. Dwell time filters out transient electrical or mechanical artifact spikes.
    4. Sustained co-contraction (>600 ms) triggers grip MODE_CYCLE.
    """

    def __init__(self, cfg: DecoderConfig = DecoderConfig()):
        self.cfg = cfg

        # Hysteresis state
        self._flex_active = False
        self._ext_active = False

        # Dwell timers (accumulates time above activation threshold)
        self._flex_dwell_s = 0.0
        self._ext_dwell_s = 0.0

        # Co-contraction state
        self._co_contract_timer_s = 0.0
        self._mode_cycled = False

    def reset(self) -> None:
        """Reset internal timers and activation states."""
        self._flex_active = False
        self._ext_active = False
        self._flex_dwell_s = 0.0
        self._ext_dwell_s = 0.0
        self._co_contract_timer_s = 0.0
        self._mode_cycled = False

    def decode(self, a_flex: float, a_ext: float, dt_s: float) -> Tuple[EMGIntent, float]:
        """Decode activations into (intent, velocity_factor).

        Args:
            a_flex: Normalized flexor activation [0.0..1.0]
            a_ext: Normalized extensor activation [0.0..1.0]
            dt_s: Time step in seconds (e.g. 0.01 for 100 Hz)

        Returns:
            Tuple of (EMGIntent, velocity_factor in [0.0..1.0])
        """
        if dt_s <= 0.0:
            return EMGIntent.HOLD, 0.0

        # --- 1. Flexor Dwell & Hysteresis Update ---
        if a_flex >= self.cfg.flex_act_threshold:
            self._flex_dwell_s += dt_s
            if self._flex_dwell_s >= self.cfg.min_dwell_s:
                self._flex_active = True
        elif a_flex <= self.cfg.flex_deact_threshold:
            self._flex_dwell_s = 0.0
            self._flex_active = False
        # else: in hysteresis band (between deact and act), maintain previous self._flex_active

        # --- 2. Extensor Dwell & Hysteresis Update ---
        if a_ext >= self.cfg.ext_act_threshold:
            self._ext_dwell_s += dt_s
            if self._ext_dwell_s >= self.cfg.min_dwell_s:
                self._ext_active = True
        elif a_ext <= self.cfg.ext_deact_threshold:
            self._ext_dwell_s = 0.0
            self._ext_active = False
        # else: in hysteresis band, maintain previous self._ext_active

        # Reset mode_cycled once both drop below deactivation threshold
        if not self._flex_active and not self._ext_active:
            self._mode_cycled = False

        # --- 3. Co-Contraction Detection ---
        if self._flex_active and self._ext_active:
            if not self._mode_cycled:
                self._co_contract_timer_s += dt_s
                if self._co_contract_timer_s >= self.cfg.co_contract_hold_s:
                    self._co_contract_timer_s = 0.0
                    self._mode_cycled = True
                    return EMGIntent.MODE_CYCLE, 0.0
            # While candidate co-contraction is developing or already fired once, hold
            return EMGIntent.HOLD, 0.0
        else:
            self._co_contract_timer_s = 0.0

        # --- 4. Single-Site Intent Resolution ---
        # Hard rule: Extensor (OPEN) unconditionally overrides Flexor (CLOSE)
        if self._ext_active:
            # Proportional velocity above threshold
            span = max(0.01, 1.0 - self.cfg.ext_act_threshold)
            vel = max(0.0, min(1.0, (a_ext - self.cfg.ext_act_threshold) / span))
            # Even at threshold boundary, provide a minimum responsive opening velocity
            vel = max(0.1, vel)
            return EMGIntent.OPEN, vel

        if self._flex_active:
            span = max(0.01, 1.0 - self.cfg.flex_act_threshold)
            vel = max(0.0, min(1.0, (a_flex - self.cfg.flex_act_threshold) / span))
            vel = max(0.1, vel)
            return EMGIntent.CLOSE, vel

        return EMGIntent.HOLD, 0.0
