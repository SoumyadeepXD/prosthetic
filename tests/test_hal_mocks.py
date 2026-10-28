"""Test mock HAL backends without physical hardware."""

from vapa.hal import (
    MockPCA9685, MockTCA9548A, MockAS5600, MockESPLink, MockRealSense
)
from vapa.protocol import HeartbeatMessage

def test_mock_pca9685():
    pca = MockPCA9685()
    assert pca.initialize() is True
    assert pca.is_healthy() is True

    pca.set_pulse_us(0, 1500.0)
    assert pca.get_pulse_us(0) == 1500.0

    pca.disable_all()
    assert pca.get_pulse_us(0) == 0.0

def test_mock_tca9548a():
    mux = MockTCA9548A()
    assert mux.initialize() is True
    assert mux.active_channel is None

    mux.select_channel(2)
    assert mux.active_channel == 2
    mux.deselect()
    assert mux.active_channel is None

def test_mock_as5600():
    enc = MockAS5600()
    assert enc.initialize() is True
    assert enc.verify_all_magnets() is True

    status = enc.read_joint_angle("wrist_flex")
    assert status.is_valid is True
    assert status.magnet_detected is True

    # Test degraded magnet
    enc.set_mock_magnet("wrist_flex", False)
    bad_status = enc.read_joint_angle("wrist_flex")
    assert bad_status.is_valid is False
    assert enc.verify_all_magnets() is False

def test_mock_esp_link_supervisor_rules():
    link = MockESPLink(hb_timeout_ms=100)
    assert link.initialize() is True

    # Initial state: no heartbeat yet -> not armed, OE disabled
    s = link.get_latest_sensor()
    assert s.oe_enabled is False
    assert s.armed is False

    # Send heartbeat with arm_request = 1
    link.send_message(HeartbeatMessage(arm_request=1, jetson_state=2))
    s2 = link.get_latest_sensor()
    assert s2.armed is True
    assert s2.oe_enabled is True

    # Test E-Stop assertion immediately drops OE
    link.estop_active = True
    link.update_supervisor()
    s3 = link.get_latest_sensor()
    assert s3.estop_pressed is True
    assert s3.oe_enabled is False
    assert s3.armed is False
    assert s3.latched_fault is True

def test_mock_realsense():
    rs = MockRealSense()
    assert rs.initialize() is True
    color, depth, t = rs.capture_frame()
    assert color.shape == (480, 640, 3)
    assert depth.shape == (480, 640)
    assert depth.dtype == "float32"
    # Verify synthetic target placed in center
    assert depth[240, 320] == 0.35
