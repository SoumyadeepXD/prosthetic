"""Test servo mapper, slew limiter, and finger force controller."""

from vapa.control import (
    ServoMapper, SlewRateLimiter, FingerForceController, PIConfig
)

def test_servo_mapper_uncalibrated_neutral():
    config = {
        "servos": {
            "thumb": {
                "channel": 0,
                "pulse_min_us": 1000.0,
                "pulse_neutral_us": 1500.0,
                "pulse_max_us": 2000.0,
                "calibrated": False,  # Uncalibrated!
            }
        }
    }
    mapper = ServoMapper(config)
    # Even if commanded to full close (1.0), it MUST stay at neutral (1500 us) until calibrated
    pulse = mapper.normalized_to_pulse("thumb", 1.0)
    assert pulse == 1500.0

def test_servo_mapper_calibrated_bounds():
    config = {
        "servos": {
            "thumb": {
                "channel": 0,
                "pulse_min_us": 1000.0,
                "pulse_neutral_us": 1500.0,
                "pulse_max_us": 2000.0,
                "calibrated": True,
            }
        }
    }
    mapper = ServoMapper(config)
    assert mapper.normalized_to_pulse("thumb", 0.0) == 1000.0
    assert mapper.normalized_to_pulse("thumb", 0.5) == 1500.0
    assert mapper.normalized_to_pulse("thumb", 1.0) == 2000.0
    # Test out of bounds clamp
    assert mapper.normalized_to_pulse("thumb", 1.5) == 2000.0
    assert mapper.normalized_to_pulse("thumb", -0.5) == 1000.0

def test_slew_limiter():
    limiter = SlewRateLimiter({"thumb": 100.0}) # 100 units/second
    limiter.reset({"thumb": 0.0})

    # In 0.01s, max change is 1.0 unit
    val = limiter.update("thumb", 10.0, dt_s=0.01)
    assert val == 1.0

def test_force_controller_cap_and_open():
    fc = FingerForceController()

    # Case 1: Force exceeds cap (measured 360g >= cap 350g) -> must back off
    cmd = fc.compute_finger_command(
        finger_name="index",
        current_pos=0.8,
        target_pos=1.0,
        measured_force=360.0,
        target_force=200.0,
        force_cap=350.0,
        dt_s=0.01,
    )
    assert cmd < 0.8  # Backed off

    # Case 2: Opening motion (target_pos < current_pos) -> bypass force control directly
    cmd_open = fc.compute_finger_command(
        finger_name="index",
        current_pos=0.8,
        target_pos=0.2,
        measured_force=360.0,
        target_force=200.0,
        force_cap=350.0,
        dt_s=0.01,
    )
    assert cmd_open == 0.2
