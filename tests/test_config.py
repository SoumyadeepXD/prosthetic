"""Test that all configuration files exist, parse correctly, and contain Rev 2 values."""

import yaml
from pathlib import Path

CONFIG_DIR = Path("config")

def test_hardware_config():
    with open(CONFIG_DIR / "hardware.yaml") as f:
        cfg = yaml.safe_load(f)

    assert cfg["jetson"]["pca9685"]["address"] == 0x40
    assert cfg["jetson"]["pca9685"]["disable_allcall"] is True
    assert cfg["jetson"]["tca9548a"]["address"] == 0x71
    assert cfg["jetson"]["as5600"]["address"] == 0x36
    assert cfg["esp32"]["pins"]["pca9685_oe"] == 25
    assert cfg["esp32"]["pins"]["estop_pin"] == 27
    assert cfg["esp32"]["ads1115"]["address"] == 0x48

def test_servos_config():
    with open(CONFIG_DIR / "servos.yaml") as f:
        cfg = yaml.safe_load(f)

    servos = cfg["servos"]
    assert "thumb" in servos
    assert "wrist_flex" in servos
    assert "wrist_bend" in servos
    assert "forearm_rotation" in servos
    assert servos["wrist_bend"]["has_encoder"] is False

    # Check conservative default pulse limits
    for name, s in servos.items():
        assert s["pulse_min_us"] >= 800
        assert s["pulse_max_us"] <= 2200
        assert s["pulse_neutral_us"] == 1500

def test_fsr_config():
    with open(CONFIG_DIR / "fsr.yaml") as f:
        cfg = yaml.safe_load(f)

    assert len(cfg["sensors"]) == 5
    for name in ["thumb", "index", "middle", "ring", "little"]:
        assert name in cfg["sensors"]

def test_emg_config():
    with open(CONFIG_DIR / "emg.yaml") as f:
        cfg = yaml.safe_load(f)

    assert cfg["decoder"] == "threshold"
    assert cfg["classifier"]["enabled"] is False  # Must be disabled by default
    assert cfg["eeg"]["enabled"] is False         # Must be disabled by default

def test_grip_profiles_config():
    with open(CONFIG_DIR / "grip_profiles.yaml") as f:
        cfg = yaml.safe_load(f)

    profiles = cfg["profiles"]
    for expected in ["default", "cylindrical", "spherical", "pinch", "lateral", "flat", "fragile_cup"]:
        assert expected in profiles
    assert profiles["fragile_cup"]["force_cap_grams"] < profiles["default"]["force_cap_grams"]

def test_vision_config():
    with open(CONFIG_DIR / "vision.yaml") as f:
        cfg = yaml.safe_load(f)

    assert cfg["distance_matrix"]["grid_rows"] == 12
    assert cfg["distance_matrix"]["grid_cols"] == 16
    assert "cup" in cfg["class_to_profile"]
    assert cfg["class_to_profile"]["cup"] == "fragile_cup"
