"""Comprehensive unit tests and benchmarks for Jetson HAL components."""

import time
import pytest
import yaml
from vapa.hal import (
    MockPCA9685, MockTCA9548A, MockAS5600, MockESPLink, MockRealSense,
    create_hal, HALContainer
)
from vapa.hal.as5600 import JointTracker

def test_pca9685_mock_and_math():
    pca = MockPCA9685(address=0x40, frequency_hz=50)
    assert pca.initialize() is True

    # 50 Hz period is 20000 us.
    # 1000 us -> 1000 / 20000 * 4096 = 204.8 -> 205 ticks
    # 1500 us -> 1500 / 20000 * 4096 = 307.2 -> 307 ticks
    # 2000 us -> 2000 / 20000 * 4096 = 409.6 -> 410 ticks
    pca.set_pulse_us(0, 1500.0)
    assert pca.get_pulse_us(0) == 1500.0
    assert len(pca.pulse_history) == 1

    pca.disable_channel(0)
    assert pca.get_pulse_us(0) == 0.0

    pca.set_pulse_us(1, 1200.0)
    pca.disable_all()
    assert pca.get_pulse_us(1) == 0.0

    with pytest.raises(ValueError):
        pca.set_pulse_us(16, 1500.0)

def test_tca9548a_mux():
    mux = MockTCA9548A(address=0x71)
    assert mux.initialize() is True

    mux.select_channel(3)
    assert mux.active_channel == 3
    mux.deselect()
    assert mux.active_channel is None

    with pytest.raises(ValueError):
        mux.select_channel(8)

def test_as5600_angle_unwrapping():
    # Test JointTracker across 0/4095 boundary
    tracker = JointTracker(channel=0, zero_offset_deg=0.0, direction=1)

    # Initial position at tick 4090 (~359.5 deg)
    unwrapped1, joint1 = tracker.update(4090)
    assert abs(unwrapped1 - (4090 / 4096.0 * 360.0)) < 1e-4

    # Rotate forward across boundary to tick 10 (delta = +16 ticks)
    unwrapped2, joint2 = tracker.update(10)
    assert unwrapped2 > unwrapped1
    assert abs(unwrapped2 - ((4090 + 16) / 4096.0 * 360.0)) < 1e-4

    # Rotate forward another 100 ticks
    unwrapped3, joint3 = tracker.update(110)
    assert unwrapped3 > unwrapped2

    # Rotate reverse back across boundary to tick 4090 (delta = -116 ticks)
    unwrapped4, joint4 = tracker.update(4090)
    assert unwrapped4 < unwrapped3
    assert abs(unwrapped4 - unwrapped1) < 1e-4

def test_as5600_zero_offset_and_direction():
    # Offset = 90 deg, Direction = -1
    tracker = JointTracker(channel=1, zero_offset_deg=90.0, direction=-1)

    # 1024 ticks is exactly 90.0 deg unwrapped
    unwrapped, joint = tracker.update(1024)
    assert abs(unwrapped - 90.0) < 1e-4
    assert abs(joint - 0.0) < 1e-4  # (90 - 90) * -1 = 0

    # Rotate forward to 2048 ticks (180.0 deg unwrapped)
    unwrapped2, joint2 = tracker.update(2048)
    assert abs(unwrapped2 - 180.0) < 1e-4
    assert abs(joint2 - (-90.0)) < 1e-4  # (180 - 90) * -1 = -90.0

def test_as5600_magnet_diagnostics():
    enc = MockAS5600()
    assert enc.initialize() is True
    assert enc.verify_all_magnets() is True

    # Test degraded magnet detection
    enc.set_mock_magnet("forearm_rotation", False)
    st = enc.read_joint_status("forearm_rotation")
    assert st.is_valid is False
    assert st.magnet_too_weak is True
    assert enc.verify_all_magnets() is False

    with pytest.raises(RuntimeError):
        enc.read_angle("forearm_rotation")

def test_as5600_read_latency_benchmark():
    enc = MockAS5600()
    assert enc.initialize() is True

    # Benchmark read speed for 4 joints
    latency_ms = enc.benchmark_read_latency(iterations=100)
    print(f"\nAS5600 4-joint mock read latency: {latency_ms:.3f} ms per cycle")
    # In mock, reading 4 joints should take < 1 ms (far below 10 ms budget for 100 Hz loop)
    assert latency_ms < 1.0

def test_hal_factory_mock():
    with open("config/hardware.yaml", "r") as f:
        cfg = yaml.safe_load(f)

    hal = create_hal(cfg, force_mock=True)
    assert isinstance(hal.pca9685, MockPCA9685)
    assert isinstance(hal.tca9548a, MockTCA9548A)
    assert isinstance(hal.as5600, MockAS5600)
    assert isinstance(hal.esp_link, MockESPLink)
    assert isinstance(hal.realsense, MockRealSense)

    assert hal.initialize_all() is True
    assert hal.pca9685.is_healthy() is True
    assert hal.as5600.is_healthy() is True

    hal.close_all()
    assert hal.pca9685.get_pulse_us(0) == 0.0
