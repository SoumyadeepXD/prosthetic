"""Comprehensive unit and integration tests for Phase 4 (Servo Control & Closed-Loop Safety)."""

import pytest
import yaml
from pathlib import Path
from vapa.control import (
    ServoMapper,
    ServoCalibration,
    SlewRateLimiter,
    FingerForceController,
    PIConfig,
    GripExecutor,
    EncoderMonitor,
    MonitorConfig,
)
from vapa.hal.pca9685 import MockPCA9685
from vapa.safety.state_machine import SafetyStateMachine, SafetyState
from vapa.safety.pwm_gate import PWMGate


@pytest.fixture
def sample_servo_config():
    return {
        "servos": {
            "thumb": {
                "channel": 0,
                "pulse_min_us": 1000.0,
                "pulse_neutral_us": 1500.0,
                "pulse_max_us": 2000.0,
                "angle_min_deg": 0.0,
                "angle_max_deg": 90.0,
                "reversed": False,
                "calibrated": True,
            },
            "index": {
                "channel": 1,
                "pulse_min_us": 950.0,
                "pulse_neutral_us": 1500.0,
                "pulse_max_us": 2050.0,
                "angle_min_deg": 0.0,
                "angle_max_deg": 90.0,
                "reversed": True,  # Reversed
                "calibrated": True,
            },
            "wrist_flex": {
                "channel": 5,
                "pulse_min_us": 1000.0,
                "pulse_neutral_us": 1500.0,
                "pulse_max_us": 2000.0,
                "angle_min_deg": -45.0,
                "angle_max_deg": 45.0,
                "reversed": False,
                "calibrated": True,
            },
            "wrist_bend": {
                "channel": 7,
                "pulse_min_us": 1100.0,
                "pulse_neutral_us": 1500.0,
                "pulse_max_us": 1900.0,
                "angle_min_deg": -30.0,
                "angle_max_deg": 30.0,
                "reversed": False,
                "calibrated": False,  # UNCALIBRATED!
            },
        }
    }


def test_servo_mapper_reversed_and_degrees(sample_servo_config):
    mapper = ServoMapper(sample_servo_config)

    # 1. Normal calibrated finger (thumb)
    assert mapper.normalized_to_pulse("thumb", 0.0) == 1000.0
    assert mapper.normalized_to_pulse("thumb", 1.0) == 2000.0

    # 2. Reversed calibrated finger (index)
    # 0.0 should map to max pulse (2050.0), 1.0 to min pulse (950.0)
    assert mapper.normalized_to_pulse("index", 0.0) == 2050.0
    assert mapper.normalized_to_pulse("index", 1.0) == 950.0
    assert mapper.normalized_to_pulse("index", 0.5) == 1500.0

    # 3. Degrees to pulse for wrist_flex (-45 to +45)
    assert mapper.degrees_to_pulse("wrist_flex", -45.0) == 1000.0
    assert mapper.degrees_to_pulse("wrist_flex", 0.0) == 1500.0
    assert mapper.degrees_to_pulse("wrist_flex", 45.0) == 2000.0

    # Clamping outside limits
    assert mapper.degrees_to_pulse("wrist_flex", 90.0) == 2000.0
    assert mapper.degrees_to_pulse("wrist_flex", -90.0) == 1000.0

    # 4. Uncalibrated servo MUST clamp to neutral regardless of target
    assert mapper.degrees_to_pulse("wrist_bend", 25.0) == 1500.0
    assert mapper.normalized_to_pulse("wrist_bend", 1.0) == 1500.0


def test_slew_rate_limiter_ramp_and_reversal():
    rates = {"joint": 100.0}  # 100 deg/sec
    limiter = SlewRateLimiter(rates)
    limiter.reset({"joint": 0.0})

    dt = 0.02  # 20ms steps, max step = 2.0 deg

    # Step 1: Ramp up towards 10.0 deg
    pos = limiter.update("joint", 10.0, dt)
    assert pytest.approx(pos, 0.001) == 2.0

    pos = limiter.update("joint", 10.0, dt)
    assert pytest.approx(pos, 0.001) == 4.0

    # Step 2: Instant reversal towards -5.0 deg
    pos = limiter.update("joint", -5.0, dt)
    assert pytest.approx(pos, 0.001) == 2.0  # Decreased by max step (2.0)

    pos = limiter.update("joint", -5.0, dt)
    assert pytest.approx(pos, 0.001) == 0.0

    pos = limiter.update("joint", -5.0, dt)
    assert pytest.approx(pos, 0.001) == -2.0


def test_force_controller_anti_windup_and_backoff():
    cfg = PIConfig(kp=0.001, ki=0.002, anti_windup_limit=0.1, backoff_step=0.05)
    fc = FingerForceController(cfg)

    # 1. Closed loop force tracking below force cap
    # target = 200g, measured = 100g, error = 100g -> closing proceeds
    curr = 0.5
    for _ in range(5):
        curr = fc.compute_finger_command(
            finger_name="index",
            current_pos=curr,
            target_pos=1.0,
            measured_force=100.0,
            target_force=200.0,
            force_cap=300.0,
            dt_s=0.01,
        )
    assert curr > 0.5  # Position advanced towards target

    # 2. Integrator anti-windup clamping
    # Simulate high error for 1000 steps
    for _ in range(1000):
        fc.compute_finger_command(
            finger_name="index",
            current_pos=0.8,
            target_pos=1.0,
            measured_force=50.0,
            target_force=200.0,
            force_cap=300.0,
            dt_s=0.01,
        )
    assert abs(fc.integrals["index"]) <= cfg.anti_windup_limit

    # 3. Force cap breach (measured 350g > cap 300g) -> immediate backoff
    pos_before = 0.8
    backed_off_pos = fc.compute_finger_command(
        finger_name="index",
        current_pos=pos_before,
        target_pos=1.0,
        measured_force=350.0,
        target_force=200.0,
        force_cap=300.0,
        dt_s=0.01,
    )
    assert backed_off_pos == pos_before - cfg.backoff_step


def test_encoder_monitor_stall_and_uncommanded_motion():
    cfg = MonitorConfig(
        stall_error_threshold_deg=12.0,
        min_velocity_deg_s=3.0,
        uncommanded_velocity_deg_s=20.0,
        stall_timeout_s=0.35,
        drift_timeout_s=0.25,
    )
    monitor = EncoderMonitor(cfg)

    # 1. Healthy tracking: commanded matches measured within 2 deg
    for _ in range(20):
        fault, reason = monitor.update(
            commanded_angles={"wrist_flex": 20.0},
            measured_angles={"wrist_flex": 20.5},
            dt_s=0.02,
        )
        assert not fault
        assert reason is None

    # 2. Joint Stall: Commanded to 40°, but measured stays stuck at 10° (err=30° > 12°)
    # Should not fault immediately, but must fault after 0.35 seconds
    monitor.reset()
    # First update seeds last positions
    monitor.update({"wrist_flex": 40.0}, {"wrist_flex": 10.0}, 0.02)

    total_time = 0.0
    fault_detected = False
    for _ in range(25):  # 25 * 0.02 = 0.50 s
        fault, reason = monitor.update({"wrist_flex": 40.0}, {"wrist_flex": 10.0}, 0.02)
        total_time += 0.02
        if fault:
            fault_detected = True
            assert "stall detected" in reason
            break

    assert fault_detected
    assert total_time >= cfg.stall_timeout_s

    # 3. Uncommanded motion (drift): Commanded stays at 0.0°, but measured spins at 60°/s
    monitor.reset()
    fault_detected = False
    meas_angle = 0.0
    # Seed
    monitor.update({"forearm_rotation": 0.0}, {"forearm_rotation": meas_angle}, 0.02)

    for _ in range(20):  # 20 * 0.02 = 0.40s
        meas_angle += 60.0 * 0.02  # 60 deg/sec
        fault, reason = monitor.update({"forearm_rotation": 0.0}, {"forearm_rotation": meas_angle}, 0.02)
        if fault:
            fault_detected = True
            assert "uncommanded motion detected" in reason
            break

    assert fault_detected


def test_grip_executor_end_to_end_with_pwm_gate():
    with open("config/servos.yaml", "r") as f:
        servo_cfg = yaml.safe_load(f)

    mapper = ServoMapper(servo_cfg)
    slew = SlewRateLimiter({k: 500.0 for k in servo_cfg["servos"].keys()})
    fc = FingerForceController()
    pca = MockPCA9685()
    pca.initialize()
    sm = SafetyStateMachine()
    gate = PWMGate(pca, sm)

    executor = GripExecutor(
        mapper=mapper,
        slew_limiter=slew,
        force_controller=fc,
        pwm_gate=gate,
    )

    with open("config/grip_profiles.yaml", "r") as f:
        profiles = yaml.safe_load(f)["profiles"]
    power_profile = profiles["default"]

    # --- Case A: DISARMED state ---
    # While DISARMED, executor calculations run, but PWMGate drops outputs
    pulses = executor.step(
        motion_command="CLOSE",
        emg_velocity=1.0,
        profile_data=power_profile,
        preshape_aperture=0.0,
        measured_forces={f: 10.0 for f in executor.FINGERS},
        dt_s=0.01,
    )
    assert len(pulses) == 9
    # PCA9685 mock should NOT have received pulses because gate is DISARMED
    assert len(pca.pulse_history) == 0
    for ch in range(9):
        assert pca.get_pulse_us(ch) == 0.0

    # --- Case B: ARMED state ---
    sm._state = SafetyState.ARMED_IDLE
    pulses = executor.step(
        motion_command="CLOSE",
        emg_velocity=1.0,
        profile_data=power_profile,
        preshape_aperture=0.0,
        measured_forces={f: 10.0 for f in executor.FINGERS},
        dt_s=0.01,
    )
    # Now pulses should have reached PCA9685
    assert len(pca.pulse_history) > 0
    for f in executor.FINGERS:
        ch = servo_cfg["servos"][f]["channel"]
        assert pca.get_pulse_us(ch) == pulses[f]


def test_servo_yaml_config_validation():
    config_file = Path("config/servos.yaml")
    assert config_file.exists()

    with open(config_file, "r") as f:
        data = yaml.safe_load(f)

    assert "servos" in data
    servos = data["servos"]
    required_keys = {"channel", "model", "pulse_min_us", "pulse_neutral_us", "pulse_max_us", "calibrated"}

    for name, s in servos.items():
        missing = required_keys - set(s.keys())
        assert not missing, f"Servo {name} is missing keys: {missing}"
        assert s["pulse_min_us"] < s["pulse_neutral_us"] < s["pulse_max_us"]
