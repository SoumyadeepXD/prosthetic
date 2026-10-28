"""PWM Arm-State Gate enforcing fail-closed PWM emission rules.

HARD NON-NEGOTIABLE RULE:
While not ARMED_IDLE or ACTIVE, the PWM layer must not emit any PWM.
No bypass of limits, slew, or the arm gate is permitted.
"""

import logging
from typing import Optional
from .state_machine import SafetyStateMachine
from ..hal.pca9685 import AbstractPCA9685

logger = logging.getLogger(__name__)

class PWMGate:
    """Interlocks all servo PWM commands with the safety state machine."""

    def __init__(self, pca9685: AbstractPCA9685, safety_machine: SafetyStateMachine):
        self.pca = pca9685
        self.safety = safety_machine

    def set_pulse_us(self, channel: int, pulse_us: float) -> bool:
        """Forward pulse to PCA9685 strictly if arm-state allows it.

        Returns:
            True if pulse was dispatched, False if blocked by gate.
        """
        if not self.safety.is_pwm_allowed:
            # Enforce hard zero PWM: ensure all outputs are disabled
            self.pca.disable_channel(channel)
            logger.warning(
                f"PWM pulse ({pulse_us:.1f} us on ch {channel}) BLOCKED by gate: "
                f"state={self.safety.state.name} is not ARMED_IDLE or ACTIVE"
            )
            return False

        self.pca.set_pulse_us(channel, pulse_us)
        return True

    def disable_channel(self, channel: int) -> None:
        self.pca.disable_channel(channel)

    def disable_all(self) -> None:
        self.pca.disable_all()

    def enforce_gate(self) -> None:
        """Called periodically to guarantee all channels remain disabled if not armed."""
        if not self.safety.is_pwm_allowed:
            self.pca.disable_all()
