"""Safety state machine implementation for VAPA."""

from enum import Enum, auto
from typing import Optional, List, Callable
import logging

logger = logging.getLogger(__name__)

class SafetyState(Enum):
    BOOT = auto()
    DISARMED = auto()
    ARMED_IDLE = auto()
    ACTIVE = auto()
    FAULT = auto()

class SafetyStateMachine:
    """Manages system safety states, arming preconditions, and fault transitions."""

    def __init__(self):
        self._state = SafetyState.BOOT
        self._fault_reason: Optional[str] = None
        self._arm_request = 0
        # Initialize directly to DISARMED upon startup
        self._transition_to(SafetyState.DISARMED, "System booted")

    @property
    def state(self) -> SafetyState:
        return self._state

    @property
    def fault_reason(self) -> Optional[str]:
        return self._fault_reason

    @property
    def arm_request(self) -> int:
        return self._arm_request

    @property
    def is_pwm_allowed(self) -> bool:
        """PWM is strictly forbidden in BOOT, DISARMED, and FAULT."""
        return self._state in (SafetyState.ARMED_IDLE, SafetyState.ACTIVE)

    def _transition_to(self, new_state: SafetyState, reason: str) -> None:
        old_state = self._state
        self._state = new_state
        if new_state == SafetyState.FAULT:
            self._arm_request = 0
            self._fault_reason = reason
        elif new_state == SafetyState.DISARMED:
            self._arm_request = 0
            self._fault_reason = None
        elif new_state in (SafetyState.ARMED_IDLE, SafetyState.ACTIVE):
            self._arm_request = 1
            self._fault_reason = None

        logger.info(f"SafetyState transition: {old_state.name} -> {new_state.name} ({reason})")

    def request_arm(
        self,
        esp_link_healthy: bool,
        estop_released: bool,
        no_latched_fault: bool,
        pca9685_healthy: bool,
        encoders_healthy: bool,
        emg_plausible: bool,
        fsr_plausible: bool,
    ) -> bool:
        """Attempt to arm the system. Returns True if armed successfully."""
        if self._state == SafetyState.FAULT:
            logger.warning("Cannot arm from FAULT state without explicit fault clearing")
            return False

        # Verify all pre-conditions
        failed_checks: List[str] = []
        if not esp_link_healthy:
            failed_checks.append("ESP32 link offline or stale")
        if not estop_released:
            failed_checks.append("E-Stop active")
        if not no_latched_fault:
            failed_checks.append("Supervisor reports latched fault")
        if not pca9685_healthy:
            failed_checks.append("PCA9685 PWM driver not responding")
        if not encoders_healthy:
            failed_checks.append("One or more AS5600 encoders missing magnet")
        if not emg_plausible:
            failed_checks.append("EMG envelope baseline not plausible")
        if not fsr_plausible:
            failed_checks.append("FSR baseline counts not plausible")

        if failed_checks:
            reason = f"Arming rejected: {', '.join(failed_checks)}"
            logger.warning(reason)
            return False

        self._transition_to(SafetyState.ARMED_IDLE, "Operator armed with all preconditions met")
        return True

    def set_active(self) -> None:
        """Transition from ARMED_IDLE to ACTIVE when control starts."""
        if self._state == SafetyState.ARMED_IDLE:
            self._transition_to(SafetyState.ACTIVE, "Motion control active")

    def set_idle(self) -> None:
        """Transition from ACTIVE to ARMED_IDLE."""
        if self._state == SafetyState.ACTIVE:
            self._transition_to(SafetyState.ARMED_IDLE, "Motion control idle")

    def disarm(self, reason: str = "Operator disarmed") -> None:
        """Transition to DISARMED."""
        self._transition_to(SafetyState.DISARMED, reason)

    def trigger_fault(self, reason: str) -> None:
        """Trigger immediate emergency transition to FAULT state."""
        self._transition_to(SafetyState.FAULT, reason)

    def clear_fault(self, estop_released: bool) -> bool:
        """Clear latched fault if E-stop is released. Transitions to DISARMED."""
        if self._state != SafetyState.FAULT:
            return True
        if not estop_released:
            logger.warning("Cannot clear fault while E-Stop is active")
            return False
        self._transition_to(SafetyState.DISARMED, "Fault cleared by operator")
        return True
