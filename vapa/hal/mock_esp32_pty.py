"""Mock ESP32 hardware simulator running over a pseudo-terminal (PTY) device."""

import os
import pty
import time
import struct
import select
import threading
from typing import Optional
from ..protocol import (
    FrameParser, encode_frame, encode_payload, decode_payload,
    MSG_TYPE_SENSOR, MSG_TYPE_STATUS, MSG_TYPE_HEARTBEAT,
    MSG_TYPE_CONFIG, MSG_TYPE_CLEAR_FAULT, MSG_TYPE_ACK_NACK,
    FLAG_ESTOP_PRESSED, FLAG_OE_ENABLED, FLAG_ARMED, FLAG_HEARTBEAT_OK,
    FLAG_FORCE_FAULT, FLAG_ADS_FAULT, FLAG_LATCHED_FAULT,
    SensorMessage, StatusMessage, HeartbeatMessage, ConfigMessage,
    AckNackMessage
)

class MockESP32Pty:
    """Simulates physical ESP32 supervisor over an OS pseudo-terminal (PTY).

    External software can open `self.port_name` just like a real serial port (/dev/ttyTHS1).
    """

    def __init__(self, hb_timeout_ms: int = 250, force_ceiling: int = 3500, force_hold_ms: int = 100):
        self.hb_timeout_ms = hb_timeout_ms
        self.force_ceiling = force_ceiling
        self.force_hold_ms = force_hold_ms

        self.master_fd: Optional[int] = None
        self.slave_fd: Optional[int] = None
        self.port_name: Optional[str] = None

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._parser = FrameParser()
        self._tx_seq = 0

        # Supervisor state
        self.estop_active = False
        self.latched_fault = False
        self.force_fault = False
        self.ads_fault = False
        self.oe_enabled = False
        self.armed = False
        self.last_heartbeat_time = 0.0
        self.had_first_heartbeat = False
        self.arm_requested = False
        self.arm_transitioned = False

        # Sensor readings
        self.emg_values = (300, 300)
        self.eeg_value = 500
        self.fsr_values = [50, 50, 50, 50, 50]

    def start(self) -> str:
        """Create PTY pair and spawn simulation thread. Returns slave port path."""
        self.master_fd, self.slave_fd = pty.openpty()
        self.port_name = os.ttyname(self.slave_fd)

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="mock-esp32-pty")
        self._thread.start()
        return self.port_name

    def stop(self) -> None:
        """Terminate simulation and close PTY descriptors."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.3)
            self._thread = None
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except Exception:
                pass
            self.master_fd = None
        if self.slave_fd is not None:
            try:
                os.close(self.slave_fd)
            except Exception:
                pass
            self.slave_fd = None

    def trigger_estop(self, pressed: bool) -> None:
        self.estop_active = pressed

    def _update_supervisor(self, now: float) -> None:
        hb_age_ms = (now - self.last_heartbeat_time) * 1000.0 if self.last_heartbeat_time > 0 else 999999.0
        hb_ok = self.had_first_heartbeat and (hb_age_ms < self.hb_timeout_ms)

        if self.estop_active:
            self.latched_fault = True

        if self.had_first_heartbeat and not hb_ok:
            self.latched_fault = True

        # OE is LOW (enabled) only if all are true:
        if (self.arm_requested and self.arm_transitioned and hb_ok and not self.estop_active
                and not self.latched_fault and not self.ads_fault and not self.force_fault):
            self.oe_enabled = True
            self.armed = True
        else:
            self.oe_enabled = False
            self.armed = False

    def _run_loop(self) -> None:
        last_sensor_time = 0.0
        last_status_time = 0.0

        while self._running and self.master_fd is not None:
            now = time.time()

            # 1. Non-blocking read from master_fd
            r, _, _ = select.select([self.master_fd], [], [], 0.005)
            if r:
                try:
                    data = os.read(self.master_fd, 64)
                    if data:
                        for msg_type, seq, payload in self._parser.parse(data):
                            if msg_type == MSG_TYPE_HEARTBEAT and len(payload) == 2:
                                arm_req = payload[0]
                                self.last_heartbeat_time = now
                                if not self.had_first_heartbeat:
                                    self.had_first_heartbeat = True
                                    self.arm_transitioned = False
                                else:
                                    if not self.arm_requested and arm_req == 1:
                                        self.arm_transitioned = True
                                    elif arm_req == 0:
                                        self.arm_transitioned = False
                                self.arm_requested = bool(arm_req == 1)
                            elif msg_type == MSG_TYPE_CONFIG and len(payload) == 6:
                                fc, hbt, fhm = struct.unpack("<HHH", payload)
                                self.force_ceiling = fc
                                self.hb_timeout_ms = hbt
                                self.force_hold_ms = fhm
                                ack = AckNackMessage(ref_type=MSG_TYPE_CONFIG, ref_seq=seq, code=0)
                                _, ack_payload = encode_payload(ack)
                                frame = encode_frame(MSG_TYPE_ACK_NACK, self._tx_seq, ack_payload)
                                self._tx_seq = (self._tx_seq + 1) & 0xFF
                                os.write(self.master_fd, frame)
                            elif msg_type == MSG_TYPE_CLEAR_FAULT and len(payload) == 0:
                                cleared = False
                                if not self.estop_active and not self.arm_requested:
                                    self.latched_fault = False
                                    self.force_fault = False
                                    self.arm_transitioned = False
                                    cleared = True
                                ack = AckNackMessage(ref_type=MSG_TYPE_CLEAR_FAULT, ref_seq=seq, code=0 if cleared else 1)
                                _, ack_payload = encode_payload(ack)
                                frame = encode_frame(MSG_TYPE_ACK_NACK, self._tx_seq, ack_payload)
                                self._tx_seq = (self._tx_seq + 1) & 0xFF
                                os.write(self.master_fd, frame)
                except Exception:
                    pass

            self._update_supervisor(now)

            # 2. Transmit 100 Hz SENSOR packets
            if (now - last_sensor_time) >= 0.01:
                last_sensor_time = now
                flags = 0
                if self.estop_active: flags |= FLAG_ESTOP_PRESSED
                if self.oe_enabled:    flags |= FLAG_OE_ENABLED
                if self.armed:         flags |= FLAG_ARMED
                if self.had_first_heartbeat and ((now - self.last_heartbeat_time) * 1000.0 < self.hb_timeout_ms):
                    flags |= FLAG_HEARTBEAT_OK
                if self.force_fault:   flags |= FLAG_FORCE_FAULT
                if self.ads_fault:     flags |= FLAG_ADS_FAULT
                if self.latched_fault: flags |= FLAG_LATCHED_FAULT

                t_ms = int(now * 1000) & 0xFFFFFFFF
                s_msg = SensorMessage(
                    t_ms=t_ms,
                    emg=self.emg_values,
                    eeg=self.eeg_value,
                    fsr=tuple(self.fsr_values),
                    flags=flags,
                )
                _, payload = encode_payload(s_msg)
                frame = encode_frame(MSG_TYPE_SENSOR, self._tx_seq, payload)
                self._tx_seq = (self._tx_seq + 1) & 0xFF
                try:
                    os.write(self.master_fd, frame)
                except Exception:
                    pass

            # 3. Transmit 2 Hz STATUS packets
            if (now - last_status_time) >= 0.50:
                last_status_time = now
                hb_age = int((now - self.last_heartbeat_time) * 1000.0) if self.last_heartbeat_time > 0 else 65535
                hb_age = min(65535, max(0, hb_age))
                st_msg = StatusMessage(
                    fw_version=0x0200,
                    reset_reason=0,
                    fault_code=1 if self.latched_fault else 0,
                    rx_err=0,
                    ads_err=1 if self.ads_fault else 0,
                    hb_age_ms=hb_age,
                )
                _, payload = encode_payload(st_msg)
                frame = encode_frame(MSG_TYPE_STATUS, self._tx_seq, payload)
                self._tx_seq = (self._tx_seq + 1) & 0xFF
                try:
                    os.write(self.master_fd, frame)
                except Exception:
                    pass
