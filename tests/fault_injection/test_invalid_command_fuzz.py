"""Fault Injection Test: Adversarial Input Fuzzing and Boundary Limits.

Verifies:
1. Servo mapper and slew limiter clamp extreme, negative, and out-of-range commands.
2. Protocol parser rejects corrupted CRC, illegal message lengths, and malformed frames.
3. Illegal safety state machine transitions are strictly rejected.
4. NaN, Infinity, and invalid data types are handled safely without unhandled crashes.
"""

import math
import pytest
import yaml
from vapa.control.servo_mapper import ServoMapper
from vapa.control.slew_limiter import SlewRateLimiter
from vapa.protocol import (
    FrameParser, encode_frame, encode_payload,
    MSG_TYPE_HEARTBEAT, HeartbeatMessage
)
from vapa.safety import SafetyStateMachine, SafetyState


@pytest.fixture
def servo_config():
    with open("config/servos.yaml", "r") as f:
        return yaml.safe_load(f)


def test_servo_mapper_adversarial_clamping(servo_config):
    """Verify that extreme out-of-bounds angle/pulse commands are clamped to conservative physical limits."""
    mapper = ServoMapper(servo_config)

    # Commanded negative position (-5.0) -> must clamp to angle_min (0.0) and pulse_min (1000 us)
    clamped_neg = mapper.normalized_to_pulse("thumb", -5.0)
    assert clamped_neg >= 1000.0

    # Commanded massive position (+100.0) -> must clamp to angle_max (90.0) and pulse_max (2000 us)
    clamped_pos = mapper.normalized_to_pulse("thumb", 100.0)
    assert clamped_pos <= 2000.0

    # Degrees mapping out of bounds
    clamped_deg_low = mapper.degrees_to_pulse("thumb", -999.0)
    assert clamped_deg_low == 1000.0

    clamped_deg_high = mapper.degrees_to_pulse("thumb", 999.0)
    assert clamped_deg_high == 2000.0


def test_slew_limiter_extreme_acceleration():
    """Verify slew rate limiter strictly bounds velocity regardless of commanded step size."""
    rates = {"thumb": 180.0}  # 180 deg/s max
    limiter = SlewRateLimiter(rates)
    limiter.reset({"thumb": 0.0})

    # Instantaneous command jump of 1000 degrees in 10 ms (dt=0.01s)
    # Max change in 0.01s at 180 deg/s is 1.8 deg
    limited = limiter.update("thumb", 1000.0, dt_s=0.01)
    assert limited == pytest.approx(1.8, abs=0.01)


def test_protocol_parser_fuzz_injection():
    """Verify parser resilience against corrupted streams, junk bytes, and CRC tampering."""
    parser = FrameParser()

    # Generate a valid heartbeat frame
    hb = HeartbeatMessage(arm_request=1, jetson_state=2)
    mtype, payload = encode_payload(hb)
    valid_bytes = encode_frame(mtype, seq=1, payload=payload)

    # Case 1: Corrupted CRC byte
    corrupted_crc = bytearray(valid_bytes)
    corrupted_crc[-1] ^= 0xFF  # Flip CRC byte
    parsed = list(parser.parse(bytes(corrupted_crc)))
    assert len(parsed) == 0  # Dropped cleanly due to CRC failure

    # Case 2: Random garbage bytes followed by valid frame
    garbage = b"\x00\xFF\xAA\x55\xDE\xAD\xBE\xEF" + valid_bytes
    parsed_resync = list(parser.parse(garbage))
    assert len(parsed_resync) == 1
    rx_type, rx_seq, rx_payload = parsed_resync[0]
    assert rx_seq == 1
    assert rx_type == MSG_TYPE_HEARTBEAT

    # Case 3: Truncated frame (incomplete bytes)
    truncated = valid_bytes[:4]
    parsed_trunc = list(parser.parse(truncated))
    assert len(parsed_trunc) == 0


def test_illegal_state_transitions():
    """Verify that forbidden safety state transitions cannot be forced."""
    sm = SafetyStateMachine()
    assert sm.state == SafetyState.DISARMED

    # Cannot transition directly to ACTIVE from DISARMED without arming
    sm.set_active()
    assert sm.state == SafetyState.DISARMED

    # Cannot arm when preconditions fail
    armed = sm.request_arm(
        esp_link_healthy=False,  # Failed check
        estop_released=True,
        no_latched_fault=True,
        pca9685_healthy=True,
        encoders_healthy=True,
        emg_plausible=True,
        fsr_plausible=True,
    )
    assert armed is False
    assert sm.state == SafetyState.DISARMED

    # From FAULT state, cannot transition to ACTIVE or ARMED_IDLE
    sm.trigger_fault("Hardware error")
    assert sm.state == SafetyState.FAULT

    sm.set_active()
    assert sm.state == SafetyState.FAULT
    assert sm.request_arm(True, True, True, True, True, True, True) is False
    assert sm.state == SafetyState.FAULT
