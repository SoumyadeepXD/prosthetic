"""Comprehensive unit tests and benchmarks for Jetson HAL components."""

import time
import pytest
import yaml
from vapa.hal import (
    MockPCA9685, MockESPLink, MockRealSense,
    create_hal, HALContainer
)

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

def test_hal_factory_mock():
    with open("config/hardware.yaml", "r") as f:
        cfg = yaml.safe_load(f)

    hal = create_hal(cfg, force_mock=True)
    assert isinstance(hal.pca9685, MockPCA9685)
    assert isinstance(hal.esp_link, MockESPLink)
    assert isinstance(hal.realsense, MockRealSense)

    assert hal.initialize_all() is True
    assert hal.pca9685.is_healthy() is True

    hal.close_all()
    assert hal.pca9685.get_pulse_us(0) == 0.0
