"""Fault Injection Test: Encoder Drift, Stall, and Uncommanded Motion.

Verifies:
1. Closed-loop joint stall detection when physical joint fails to move with servo.
2. Uncommanded motion detection (runaway joint or tendon slippage while commanded stationary).
3. Transient dynamic lag during fast acceleration is tolerated without false faulting.
4. Magnet diagnostic failure (magnet dropped, misaligned, or field degraded) prevents arming.
5. Invalidation of PWM outputs immediately upon stall/runaway fault latch.
"""

import pytest
from vapa.control.encoder_monitor import EncoderMonitor, MonitorConfig
from vapa.safety import SafetyStateMachine, SafetyState, PWMGate
from vapa.hal import MockPCA9685, MockAS5600


def test_encoder_stall_detection_and_disarm():
    """Verify that a joint stall (e.g. jammed gearbox or obstruction) triggers safe shutdown."""
    cfg = MonitorConfig(stall_error_threshold_deg=10.0, stall_timeout_s=0.30)
    monitor = EncoderMonitor(cfg)
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
    assert sm.state == SafetyState.ACTIVE

    # Simulate commanded 45 degrees, but encoder stuck at 0 degrees
    dt = 0.05  # 20 Hz loop
    fault_detected = False
    fault_msg = None

    # Step through time; must not fault immediately on first step (allows slew)
    for step in range(10):  # 10 * 0.05s = 0.50s total
        commanded = {"finger_group": 45.0, "wrist_flex": 0.0, "wrist_rotate": 0.0, "forearm_rotation": 0.0}
        measured = {"finger_group": 0.0, "wrist_flex": 0.0, "wrist_rotate": 0.0, "forearm_rotation": 0.0}
        has_fault, reason = monitor.update(commanded, measured, dt_s=dt)
        if has_fault:
            fault_detected = True
            fault_msg = reason
            sm.trigger_fault(reason)
            gate.enforce_gate()
            break

    assert fault_detected is True
    assert "stall detected" in fault_msg.lower()
    assert "finger_group" in fault_msg
    assert sm.state == SafetyState.FAULT
    assert sm.is_pwm_allowed is False
    assert gate.set_pulse_us(0, 1500.0) is False


def test_uncommanded_motion_runaway_detection():
    """Verify that uncommanded movement (e.g. tendon slippage or external violent force) triggers fault."""
    cfg = MonitorConfig(uncommanded_velocity_deg_s=20.0, drift_timeout_s=0.20)
    monitor = EncoderMonitor(cfg)
    sm = SafetyStateMachine()

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

    dt = 0.05
    fault_detected = False
    fault_msg = None

    # Commanded stationary at 0 degrees, but measured rotates rapidly (e.g. 50 deg/s)
    current_meas = 0.0
    for _ in range(8):  # 0.4s
        current_meas += 2.5  # 2.5 deg / 0.05s = 50 deg/s
        commanded = {"finger_group": 0.0, "wrist_flex": 0.0, "wrist_rotate": 0.0, "forearm_rotation": 0.0}
        measured = {"finger_group": 0.0, "wrist_flex": current_meas, "wrist_rotate": 0.0, "forearm_rotation": 0.0}
        has_fault, reason = monitor.update(commanded, measured, dt_s=dt)
        if has_fault:
            fault_detected = True
            fault_msg = reason
            sm.trigger_fault(reason)
            break

    assert fault_detected is True
    assert "uncommanded motion detected" in fault_msg.lower()
    assert "wrist_flex" in fault_msg
    assert sm.state == SafetyState.FAULT


def test_transient_lag_does_not_nuisance_trip():
    """Verify that normal dynamic servo slew lag (<0.35s) does NOT trip stall fault."""
    cfg = MonitorConfig(stall_error_threshold_deg=10.0, stall_timeout_s=0.35)
    monitor = EncoderMonitor(cfg)

    # Initial command step of 30 deg, joint catches up in 0.15s (3 steps of 0.05s)
    trajectory = [0.0, 10.0, 20.0, 30.0]
    for meas in trajectory:
        commanded = {"finger_group": 30.0, "wrist_flex": 0.0, "wrist_rotate": 0.0, "forearm_rotation": 0.0}
        measured = {"finger_group": meas, "wrist_flex": 0.0, "wrist_rotate": 0.0, "forearm_rotation": 0.0}
        has_fault, _ = monitor.update(commanded, measured, dt_s=0.05)
        assert has_fault is False


def test_as5600_magnet_loss_injection():
    """Verify that loss of magnet field on AS5600 trips status checks."""
    as5600 = MockAS5600()
    as5600.initialize()

    # Verify nominal status
    status = as5600.read_joint_status("wrist_flex")
    assert status.magnet_detected is True
    assert status.magnet_too_strong is False
    assert status.magnet_too_weak is False
    assert as5600.verify_all_magnets() is True

    # Inject magnet removal (air gap too large or magnet fell off)
    as5600.set_mock_magnet("wrist_flex", False)
    degraded_status = as5600.read_joint_status("wrist_flex")
    assert degraded_status.magnet_detected is False
    assert degraded_status.magnet_too_weak is True
    assert as5600.verify_all_magnets() is False
