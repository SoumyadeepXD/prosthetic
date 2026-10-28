"""Comprehensive Safety Test Suite covering all Section 6 requirements."""

import time
import pytest
import yaml
from vapa.safety import (
    SafetyStateMachine, SafetyState, PWMGate, PreconditionValidator,
    HeartbeatThread, SafetyEmergencyShutdown
)
from vapa.hal import (
    MockPCA9685, MockTCA9548A, MockAS5600, MockESPLink, MockRealSense,
    HALContainer, create_hal
)
from vapa.control import FingerForceController
from vapa.emg import EnvelopeNormalizer, EMGCalibration
from vapa.protocol import HeartbeatMessage

@pytest.fixture
def mock_hal():
    with open("config/hardware.yaml", "r") as f:
        cfg = yaml.safe_load(f)
    return create_hal(cfg, force_mock=True)

def test_no_pwm_emitted_unless_active_or_armed_idle():
    sm = SafetyStateMachine()
    pca = MockPCA9685()
    pca.initialize()
    gate = PWMGate(pca, sm)

    # 1. While DISARMED: pulse MUST be blocked and PCA channel disabled
    assert sm.state == SafetyState.DISARMED
    assert gate.set_pulse_us(0, 1500.0) is False
    assert pca.get_pulse_us(0) == 0.0

    # 2. While FAULT: pulse MUST be blocked
    sm.trigger_fault("Test fault")
    assert sm.state == SafetyState.FAULT
    assert gate.set_pulse_us(0, 1500.0) is False
    assert pca.get_pulse_us(0) == 0.0

    # 3. Transition to ARMED_IDLE: pulse permitted
    sm.clear_fault(estop_released=True)
    sm.request_arm(
        esp_link_healthy=True,
        estop_released=True,
        no_latched_fault=True,
        pca9685_healthy=True,
        encoders_healthy=True,
        emg_plausible=True,
        fsr_plausible=True,
    )
    assert sm.state == SafetyState.ARMED_IDLE
    assert gate.set_pulse_us(0, 1500.0) is True
    assert pca.get_pulse_us(0) == 1500.0

    # 4. Transition to ACTIVE: pulse permitted
    sm.set_active()
    assert sm.state == SafetyState.ACTIVE
    assert gate.set_pulse_us(1, 1600.0) is True
    assert pca.get_pulse_us(1) == 1600.0

    # 5. Fault triggered while ACTIVE: immediately shuts down PWM
    sm.trigger_fault("Sudden fault")
    gate.enforce_gate()
    assert pca.get_pulse_us(0) == 0.0
    assert pca.get_pulse_us(1) == 0.0

def test_heartbeat_loss_disarms(mock_hal):
    mock_hal.initialize_all()
    sm = SafetyStateMachine()

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
    assert sm.state == SafetyState.ARMED_IDLE
    mock_hal.esp_link.send_message(HeartbeatMessage(arm_request=1, jetson_state=2))
    assert mock_hal.esp_link.get_latest_sensor().oe_enabled is True

    # Simulate heartbeat timeout on ESP32 link (advance time past 250ms)
    time.sleep(0.3)
    sensor = mock_hal.esp_link.get_latest_sensor()
    assert sensor.heartbeat_ok is False
    assert sensor.oe_enabled is False
    assert sensor.latched_fault is True

    # Jetson reacts to supervisor latched fault
    if sensor.latched_fault:
        sm.trigger_fault("ESP32 reported heartbeat loss / latched fault")

    assert sm.state == SafetyState.FAULT
    assert sm.arm_request == 0

def test_estop_disarms(mock_hal):
    mock_hal.initialize_all()
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
    assert sm.state == SafetyState.ARMED_IDLE

    # Strike E-stop
    mock_hal.esp_link.estop_active = True
    sensor = mock_hal.esp_link.get_latest_sensor()
    assert sensor.estop_pressed is True
    assert sensor.oe_enabled is False

    # Jetson reacts
    sm.trigger_fault("E-stop pressed")
    assert sm.state == SafetyState.FAULT
    assert sm.arm_request == 0
    assert sm.is_pwm_allowed is False

def test_force_fault_backs_off():
    fc = FingerForceController()
    # Measured force exceeds cap (cap=350g, measured=380g)
    current_pos = 0.85
    cmd = fc.compute_finger_command(
        finger_name="index",
        current_pos=current_pos,
        target_pos=1.0,
        measured_force=380.0,
        target_force=200.0,
        force_cap=350.0,
    )
    # Must back off (command position lower than current)
    assert cmd < current_pos
    assert cmd == current_pos - 0.05

def test_stuck_emg_faults():
    normalizer = EnvelopeNormalizer(
        flexor_cal=EMGCalibration(baseline_mv=250.0, mvc_mv=2200.0, saturation_mv=3200.0),
        extensor_cal=EMGCalibration(baseline_mv=250.0, mvc_mv=2200.0, saturation_mv=3200.0),
        stuck_window_size=10,
    )
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
    assert sm.state == SafetyState.ACTIVE

    # Feed stuck/constant EMG signal for 10 samples
    for _ in range(10):
        _, _, healthy = normalizer.normalize(300.0, 300.0)

    assert healthy is False
    assert "stuck" in normalizer.last_fault_reason.lower()

    # Safety responds by faulting
    sm.trigger_fault(normalizer.last_fault_reason)
    assert sm.state == SafetyState.FAULT
    assert sm.arm_request == 0

def test_arming_refused_when_any_precondition_fails(mock_hal):
    mock_hal.initialize_all()
    validator = PreconditionValidator()
    servo_cfg = {"servos": {"thumb": {}}}

    # Baseline valid test
    res = validator.evaluate(mock_hal, servo_cfg, emg_calibrated=True)
    assert res.passed is True

    # Case A: E-stop pressed
    mock_hal.esp_link.estop_active = True
    assert validator.evaluate(mock_hal, servo_cfg).passed is False
    mock_hal.esp_link.estop_active = False

    # Case B: AS5600 degraded magnet
    mock_hal.as5600.set_mock_magnet("wrist_flex", False)
    assert validator.evaluate(mock_hal, servo_cfg).passed is False
    mock_hal.as5600.set_mock_magnet("wrist_flex", True)

    # Case C: FSR high at rest (not plausible)
    mock_hal.esp_link.sim_fsr = (50, 400, 50, 50, 50)  # > 250 counts
    assert validator.evaluate(mock_hal, servo_cfg).passed is False
    mock_hal.esp_link.sim_fsr = (50, 50, 50, 50, 50)

    # Case D: EMG saturated
    mock_hal.esp_link.sim_emg = (3500, 300)  # > 3000 mV
    assert validator.evaluate(mock_hal, servo_cfg).passed is False
    mock_hal.esp_link.sim_emg = (300, 300)

    # Case E: Missing servo configuration
    assert validator.evaluate(mock_hal, {"servos": {}}).passed is False

def test_exception_handler_drops_arm_request(mock_hal):
    mock_hal.initialize_all()
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
    assert sm.arm_request == 1

    shutdown = SafetyEmergencyShutdown(sm, hal=mock_hal)
    shutdown.execute_fail_safe_shutdown("Simulated unhandled exception")

    assert sm.state == SafetyState.FAULT
    assert sm.arm_request == 0
    assert mock_hal.pca9685.get_pulse_us(0) == 0.0

def test_loop_stall_stops_heartbeats():
    sm = SafetyStateMachine()
    last_sent_hb = []

    def fake_send(hb):
        last_sent_hb.append(hb)

    stall_flag = [False]
    def on_stall():
        stall_flag[0] = True
        sm.trigger_fault("Loop stall detected")

    hb_thread = HeartbeatThread(
        send_fn=fake_send,
        get_arm_request_fn=lambda: sm.arm_request,
        get_state_fn=lambda: sm.state.value,
        stall_timeout_s=0.04,  # 40 ms timeout
        on_stall_callback=on_stall,
    )
    hb_thread.start()

    # Feed for 50 ms
    for _ in range(5):
        hb_thread.feed()
        time.sleep(0.01)

    assert len(last_sent_hb) > 0

    # Stop feeding and stall for 60 ms
    time.sleep(0.06)

    # Check stall callback triggered
    assert stall_flag[0] is True
    assert sm.state == SafetyState.FAULT
    assert sm.arm_request == 0

    # In stall state, the thread sent arm_request = 0
    assert last_sent_hb[-1].arm_request == 0

    hb_thread.stop()
