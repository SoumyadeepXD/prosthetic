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

        # Wait up to 250ms for condition to be met
        def wait_sensor(condition, timeout=0.25):
            t0 = time.time()
            while time.time() - t0 < timeout:
                s = link.get_latest_sensor()
                if s is not None and condition(s):
                    return s
                time.sleep(0.01)
            return link.get_latest_sensor()

        # 3. Check initial sensor reception
        sensor = wait_sensor(lambda s: s.oe_enabled is False and s.armed is False)
        assert sensor is not None
        assert sensor.oe_enabled is False
        assert sensor.armed is False

        # 4. Send arming sequence (first heartbeat with 0, then 1)
        link.send_message(HeartbeatMessage(arm_request=0, jetson_state=1))
        time.sleep(0.02)
        link.send_message(HeartbeatMessage(arm_request=1, jetson_state=2))

        sensor2 = wait_sensor(lambda s: s.armed is True)
        assert sensor2 is not None
        assert sensor2.armed is True
        assert sensor2.oe_enabled is True
        assert sensor2.heartbeat_ok is True

        # 5. Simulate E-Stop press on virtual ESP32
        sim.trigger_estop(True)

        sensor3 = wait_sensor(lambda s: s.estop_pressed is True)
        assert sensor3 is not None
        assert sensor3.estop_pressed is True
        assert sensor3.oe_enabled is False
        assert sensor3.latched_fault is True

        # 6. Release E-Stop and clear fault
        sim.trigger_estop(False)
        link.send_message(HeartbeatMessage(arm_request=0, jetson_state=1))
        time.sleep(0.02)
        link.send_message(ClearFaultMessage())

        sensor4 = wait_sensor(lambda s: s.estop_pressed is False and s.latched_fault is False)
        assert sensor4 is not None
        assert sensor4.estop_pressed is False
        assert sensor4.latched_fault is False

        # 7. Re-arm with fresh 0->1 transition
        link.send_message(HeartbeatMessage(arm_request=1, jetson_state=2))
        sensor5 = wait_sensor(lambda s: s.armed is True)
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
