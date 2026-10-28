"""Test MockESP32Pty connected to RealESPLink over virtual OS serial port."""

import time
import pytest
from vapa.hal import MockESP32Pty, RealESPLink
from vapa.protocol import HeartbeatMessage, ClearFaultMessage

def test_pty_serial_end_to_end():
    # 1. Start virtual ESP32 simulator
    sim = MockESP32Pty(hb_timeout_ms=300)
    slave_port = sim.start()
    assert slave_port is not None

    try:
        # 2. Connect RealESPLink to virtual serial port
        link = RealESPLink(port=slave_port, baudrate=460800)
        assert link.initialize() is True

        # Wait briefly for initial frames to arrive
        time.sleep(0.1)

        # 3. Check initial sensor reception
        sensor = link.get_latest_sensor()
        assert sensor is not None
        assert sensor.oe_enabled is False
        assert sensor.armed is False

        # 4. Send arming sequence (first heartbeat with 0, then 1)
        link.send_message(HeartbeatMessage(arm_request=0, jetson_state=1))
        time.sleep(0.05)
        link.send_message(HeartbeatMessage(arm_request=1, jetson_state=2))
        time.sleep(0.05)

        sensor2 = link.get_latest_sensor()
        assert sensor2 is not None
        assert sensor2.armed is True
        assert sensor2.oe_enabled is True
        assert sensor2.heartbeat_ok is True

        # 5. Simulate E-Stop press on virtual ESP32
        sim.trigger_estop(True)
        time.sleep(0.05)

        sensor3 = link.get_latest_sensor()
        assert sensor3 is not None
        assert sensor3.estop_pressed is True
        assert sensor3.oe_enabled is False
        assert sensor3.latched_fault is True

        # 6. Release E-Stop and clear fault
        sim.trigger_estop(False)
        link.send_message(HeartbeatMessage(arm_request=0, jetson_state=1))
        time.sleep(0.05)
        link.send_message(ClearFaultMessage())
        time.sleep(0.05)

        sensor4 = link.get_latest_sensor()
        assert sensor4 is not None
        assert sensor4.estop_pressed is False
        assert sensor4.latched_fault is False

        # 7. Re-arm with fresh 0->1 transition
        link.send_message(HeartbeatMessage(arm_request=1, jetson_state=2))
        time.sleep(0.05)
        sensor5 = link.get_latest_sensor()
        assert sensor5 is not None
        assert sensor5.armed is True
        assert sensor5.oe_enabled is True

        # Check link stats
        stats = link.get_link_stats()
        assert stats["frames_received"] > 10
        assert stats["crc_errors"] == 0

        link.close()
    finally:
        sim.stop()
