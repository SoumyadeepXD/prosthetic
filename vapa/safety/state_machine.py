"""Safety state machine implementation for VAPA.

Implements the formal 8-state safety architecture:
1. BOOT: System hardware power-on state; transitions immediately to DISARMED.
2. DISARMED: Safe resting state. PWM forbidden. Preconditions evaluated here.
3. SELF_TEST: Automated pre-flight diagnostics (sensor plausibility, link integrity).
4. CALIBRATION: Isolated bench calibration mode (strictly human-supervised, guarded PWM).
5. ARMED_IDLE: Armed, holding positions stationary. PWM active.
6. ACTIVE: Real-time shared-control motion execution. PWM active.
7. FAULT: Software/sensor/tracking/communication fault latch. PWM strictly forbidden.
8. EMERGENCY_STOP: Physical E-stop active or power interlock broken. PWM strictly forbidden.
"""

from enum import Enum, auto
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


class SafetyState(Enum):
    BOOT = auto()
    DISARMED = auto()
    SELF_TEST = auto()
    CALIBRATION = auto()
    ARMED_IDLE = auto()
    ACTIVE = auto()
    FAULT = auto()
    EMERGENCY_STOP = auto()


class SafetyStateMachine:
    """Manages system safety states, arming preconditions, and fault transitions."""

    def __init__(self, initial_state: SafetyState = SafetyState.DISARMED):
        self._state = SafetyState.BOOT
        self._fault_reason: Optional[str] = None
        self._arm_request = 0
        self._self_test_passed = False
        if initial_state != SafetyState.BOOT:
            self._transition_to(initial_state, "System booted")
        else:
            self._state = SafetyState.BOOT

    def boot_complete(self) -> None:
        """Complete boot sequence and transition to DISARMED."""
        if self._state == SafetyState.BOOT:
            self._transition_to(SafetyState.DISARMED, "Boot sequence completed")

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
        """PWM is strictly permitted ONLY in ARMED_IDLE, ACTIVE, and CALIBRATION.

        In BOOT, DISARMED, SELF_TEST, FAULT, and EMERGENCY_STOP, PWM is strictly forbidden.
        """
        return self._state in (SafetyState.ARMED_IDLE, SafetyState.ACTIVE, SafetyState.CALIBRATION)

    def _transition_to(self, new_state: SafetyState, reason: str) -> None:
        old_state = self._state
        self._state = new_state

        if new_state in (SafetyState.FAULT, SafetyState.EMERGENCY_STOP):
            self._arm_request = 0
            self._fault_reason = reason
        elif new_state in (SafetyState.DISARMED, SafetyState.BOOT, SafetyState.SELF_TEST):
            self._arm_request = 0
            if new_state == SafetyState.DISARMED and old_state not in (SafetyState.FAULT, SafetyState.EMERGENCY_STOP):
                self._fault_reason = None
        elif new_state == SafetyState.CALIBRATION:
            self._arm_request = 0  # Not armed for autonomous motion
            self._fault_reason = None
        elif new_state in (SafetyState.ARMED_IDLE, SafetyState.ACTIVE):
            self._arm_request = 1
            self._fault_reason = None

        logger.info(f"SafetyState transition: {old_state.name} -> {new_state.name} ({reason})")

    def start_self_test(self) -> bool:
        """Begin automated self-test diagnostics from DISARMED state."""
        if self._state != SafetyState.DISARMED:
            logger.warning(f"Cannot start SELF_TEST from state {self._state.name}")
            return False
        self._self_test_passed = False
        self._transition_to(SafetyState.SELF_TEST, "Self-test sequence initiated")
        return True

    def finish_self_test(self, passed: bool, reason: str = "") -> None:
        """Conclude self-test. Transitions to DISARMED if passed, FAULT if failed."""
        if self._state != SafetyState.SELF_TEST:
            return
        self._self_test_passed = passed
        if passed:
            self._transition_to(SafetyState.DISARMED, "Self-test passed successfully")
        else:
            self._transition_to(SafetyState.FAULT, f"Self-test failed: {reason}")

    def enter_calibration(self) -> bool:
        """Enter isolated bench calibration mode from DISARMED state."""
        if self._state != SafetyState.DISARMED:
            logger.warning(f"Cannot enter CALIBRATION from state {self._state.name}")
            return False
        self._transition_to(SafetyState.CALIBRATION, "Entered bench calibration mode")
        return True

    def exit_calibration(self) -> bool:
        """Exit calibration mode and return to DISARMED."""
        if self._state == SafetyState.CALIBRATION:
            self._transition_to(SafetyState.DISARMED, "Exited calibration mode")
            return True
        return False

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
        if self._state in (SafetyState.FAULT, SafetyState.EMERGENCY_STOP):
            logger.warning(f"Cannot arm from {self._state.name} without explicit operator clear")
            return False

        if self._state == SafetyState.CALIBRATION:
            logger.warning("Cannot arm directly from CALIBRATION mode; exit calibration first")
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
        if self._state not in (SafetyState.FAULT, SafetyState.EMERGENCY_STOP):
            self._transition_to(SafetyState.DISARMED, reason)

    def trigger_fault(self, reason: str) -> None:
        """Trigger immediate emergency transition to FAULT state."""
        self._transition_to(SafetyState.FAULT, reason)

    def trigger_estop(self, reason: str = "Physical Emergency Stop active") -> None:
        """Trigger immediate transition to EMERGENCY_STOP state."""
        self._transition_to(SafetyState.EMERGENCY_STOP, reason)

    def clear_fault(self, estop_released: bool = True) -> bool:
        """Clear latched fault or emergency stop if physical E-stop is released.

        Transitions to DISARMED.
        """
        if self._state not in (SafetyState.FAULT, SafetyState.EMERGENCY_STOP):
            return True
        if not estop_released:
            logger.warning("Cannot clear fault while E-Stop is physically active")
            return False
        self._transition_to(SafetyState.DISARMED, "Fault cleared by operator")
        return True
