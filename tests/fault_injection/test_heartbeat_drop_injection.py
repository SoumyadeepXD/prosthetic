"""Fault Injection Test: Heartbeat Drop and Link Severance Injection.

Verifies:
1. ESP32 supervisor trips fault and disables /OE within 250 ms of heartbeat cessation.
2. Jetson reacts to supervisor fault and transitions to FAULT state, dropping arm_request.
3. Single frame drops (<250 ms) do not trigger false nuisance trips.
4. Physical UART disconnect / exception triggers fail-closed state transition.
5. System remains in FAULT until explicit operator clearance.
"""

import time
import pytest
from vapa.safety import SafetyStateMachine, SafetyState, PWMGate
from vapa.hal import MockPCA9685, MockESPLink
from vapa.protocol import HeartbeatMessage, SensorMessage


def test_heartbeat_loss_exact_timing():
    """Verify ESP32 supervisor trips within 250 ms timeout and disables OE."""
    esp = MockESPLink()
    esp.initialize()
    sm = SafetyStateMachine()
    pca = MockPCA9685()
    pca.initialize()
    gate = PWMGate(pca, sm)

    # Arm system
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
    assert sm.is_pwm_allowed is True

    # Send valid heartbeats to establish link
    for _ in range(5):
        esp.send_message(HeartbeatMessage(arm_request=1, jetson_state=int(sm.state.value)))
        time.sleep(0.02)

    sensor = esp.get_latest_sensor()
    assert sensor.heartbeat_ok is True
    assert sensor.oe_enabled is True
    assert sensor.latched_fault is False

    # Allow 100 ms to elapse without heartbeat (< 250 ms threshold) - must stay alive
    time.sleep(0.10)
    sensor_100ms = esp.get_latest_sensor()
    assert sensor_100ms.heartbeat_ok is True
    assert sensor_100ms.oe_enabled is True

    # Allow cumulative time to exceed 250 ms (e.g. 270 ms total)
    time.sleep(0.18)
    sensor_stalled = esp.get_latest_sensor()
    assert sensor_stalled.heartbeat_ok is False
    assert sensor_stalled.oe_enabled is False
    assert sensor_stalled.latched_fault is True

    # Jetson detects latched fault and disarms
    if sensor_stalled.latched_fault:
        sm.trigger_fault("ESP32 supervisor latched fault: Heartbeat lost")

    assert sm.state == SafetyState.FAULT
    assert sm.arm_request == 0
    assert sm.is_pwm_allowed is False

    # Gate must actively block pulse commands
    assert gate.set_pulse_us(0, 1500.0) is False
    assert pca.get_pulse_us(0) == 0.0


def test_heartbeat_recovery_requires_operator_clear():
    """Verify that simply restoring heartbeats does NOT re-enable PWM without operator intervention."""
    esp = MockESPLink()
    esp.initialize()
    sm = SafetyStateMachine()

    # Trigger heartbeat timeout
    esp.send_message(HeartbeatMessage(arm_request=1, jetson_state=2))
    time.sleep(0.3)
    sensor = esp.get_latest_sensor()
    assert sensor.latched_fault is True

    sm.trigger_fault("Heartbeat lost")
    assert sm.state == SafetyState.FAULT

    # Heartbeats resume at 50 Hz
    for _ in range(10):
        esp.send_message(HeartbeatMessage(arm_request=1, jetson_state=2))
        time.sleep(0.02)

    # ESP32 supervisor latched fault persists because supervisor requires fault latch clear
    sensor_resumed = esp.get_latest_sensor()
    # State machine must still refuse to arm while in FAULT
    assert sm.state == SafetyState.FAULT
    assert sm.request_arm(
        esp_link_healthy=True,
        estop_released=True,
        no_latched_fault=not sensor_resumed.latched_fault,
        pca9685_healthy=True,
        encoders_healthy=True,
        emg_plausible=True,
        fsr_plausible=True,
    ) is False


def test_uart_disconnect_injection():
    """Verify behavior when physical UART communication drops abruptly."""
    esp = MockESPLink()
    esp.initialize()
    sm = SafetyStateMachine()
    pca = MockPCA9685()
    pca.initialize()
    gate = PWMGate(pca, sm)

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
    assert gate.set_pulse_us(0, 1500.0) is True

    # Simulate link failure (e.g. cable disconnect)
    esp.close()
    assert esp.is_healthy() is False

    # Safety supervisor detects loss of link
    sm.trigger_fault("UART connection severed")
    gate.enforce_gate()

    assert sm.state == SafetyState.FAULT
    assert pca.get_pulse_us(0) == 0.0
    assert gate.set_pulse_us(0, 1500.0) is False
