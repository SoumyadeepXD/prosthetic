"""Fault Injection Test: Physical Emergency Stop and Transient Cutoff.

Verifies:
1. Immediate transition to EMERGENCY_STOP state when hardware switch is pressed.
2. Invalidation of all PWM outputs across all channels upon E-stop.
3. Strict locking: fault cannot be cleared while E-stop is physically held.
4. Auto-rearm is strictly prevented when E-stop is released; explicit operator re-arm required.
5. Multi-channel grasp interruption under emergency shutdown.
"""

import pytest
from vapa.safety import SafetyStateMachine, SafetyState, PWMGate
from vapa.hal import MockPCA9685, MockESPLink
from vapa.protocol import HeartbeatMessage


def test_estop_under_active_motion():
    """Verify that striking E-stop during high-speed motion immediately cuts PWM."""
    sm = SafetyStateMachine()
    pca = MockPCA9685()
    pca.initialize()
    esp = MockESPLink()
    esp.initialize()
    gate = PWMGate(pca, sm)

    # Arm and activate
    sm.request_arm(
        esp_link_healthy=True,
        estop_released=True,
        no_latched_fault=True,
        pca9685_healthy=True,
        encoders_healthy=True,
        emg_plausible=True,
        fsr_plausible=True,
    )
    sm.set_active()
    assert sm.state == SafetyState.ACTIVE

    # Command active pulses to multiple finger servos
    for ch in range(5):
        assert gate.set_pulse_us(ch, 1800.0) is True
        assert pca.get_pulse_us(ch) == 1800.0

    # Strike Emergency Stop
    esp.estop_active = True
    sensor = esp.get_latest_sensor()
    assert sensor.estop_pressed is True
    assert sensor.oe_enabled is False

    # Software state machine triggers E-stop
    sm.trigger_estop("Physical E-Stop engaged by operator")
    gate.enforce_gate()

    assert sm.state == SafetyState.EMERGENCY_STOP
    assert sm.is_pwm_allowed is False
    assert sm.arm_request == 0

    # All PWM channels must be zeroed immediately
    for ch in range(5):
        assert pca.get_pulse_us(ch) == 0.0
        assert gate.set_pulse_us(ch, 1800.0) is False


def test_estop_clear_prevention_while_pressed():
    """Verify that clear_fault() strictly fails as long as physical E-stop is engaged."""
    sm = SafetyStateMachine()
    sm.trigger_estop("E-Stop engaged")
    assert sm.state == SafetyState.EMERGENCY_STOP

    # Attempt to clear fault with switch still pressed
    cleared = sm.clear_fault(estop_released=False)
    assert cleared is False
    assert sm.state == SafetyState.EMERGENCY_STOP

    # Attempt to arm directly from EMERGENCY_STOP
    armed = sm.request_arm(
        esp_link_healthy=True,
        estop_released=False,
        no_latched_fault=True,
        pca9685_healthy=True,
        encoders_healthy=True,
        emg_plausible=True,
        fsr_plausible=True,
    )
    assert armed is False
    assert sm.state == SafetyState.EMERGENCY_STOP


def test_estop_release_transitions_only_to_disarmed():
    """Verify that releasing E-stop and clearing fault transitions to DISARMED, never armed."""
    sm = SafetyStateMachine()
    sm.trigger_estop("E-Stop engaged")

    # Release E-stop and clear fault
    cleared = sm.clear_fault(estop_released=True)
    assert cleared is True
    assert sm.state == SafetyState.DISARMED
    assert sm.is_pwm_allowed is False
    assert sm.arm_request == 0

    # Arming now requires explicit operator request and precondition check
    armed = sm.request_arm(
        esp_link_healthy=True,
        estop_released=True,
        no_latched_fault=True,
        pca9685_healthy=True,
        encoders_healthy=True,
        emg_plausible=True,
        fsr_plausible=True,
    )
    assert armed is True
    assert sm.state == SafetyState.ARMED_IDLE
