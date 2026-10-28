"""ESP32 UART communication link with Mock and Real serial backends."""

import time
import threading
from abc import abstractmethod
from typing import Optional, Callable, List, Tuple
from .base import BaseDevice
from ..protocol import (
    FrameParser, encode_frame, encode_payload, decode_payload,
    MSG_TYPE_SENSOR, MSG_TYPE_STATUS, MSG_TYPE_HEARTBEAT,
    MSG_TYPE_CONFIG, MSG_TYPE_CLEAR_FAULT, MSG_TYPE_ACK_NACK,
    FLAG_ESTOP_PRESSED, FLAG_OE_ENABLED, FLAG_ARMED, FLAG_HEARTBEAT_OK,
    FLAG_FORCE_FAULT, FLAG_ADS_FAULT, FLAG_LATCHED_FAULT,
    SensorMessage, StatusMessage, HeartbeatMessage, ConfigMessage, ClearFaultMessage
)

class AbstractESPLink(BaseDevice):
    """Abstract interface for bidirectional ESP32 link."""

    @abstractmethod
    def send_message(self, msg: object) -> None:
        """Transmit message to ESP32."""
        pass

    @abstractmethod
    def get_latest_sensor(self) -> Optional[SensorMessage]:
        """Return the most recently received sensor packet."""
        pass

    @abstractmethod
    def get_latest_status(self) -> Optional[StatusMessage]:
        """Return the most recently received status packet."""
        pass

    @abstractmethod
    def get_link_stats(self) -> dict:
        """Return dictionary containing rx_rate, crc_errors, resyncs, and frame_age_ms."""
        pass

class MockESPLink(AbstractESPLink):
    """Mock ESP32 link simulating the ESP32 supervisor state and sensors."""

    def __init__(self, hb_timeout_ms: int = 250):
        self.hb_timeout_ms = hb_timeout_ms
        self._initialized = False
        self._seq_tx = 0
        self._seq_rx = 0

        # Supervisor simulation state
        self.estop_active = False
        self.latched_fault = False
        self.force_fault = False
        self.ads_fault = False
        self.armed = False
        self.oe_enabled = False
        self.last_heartbeat_time: float = 0.0
        self.had_first_heartbeat = False
        self.arm_requested = False
        self.prev_arm_requested = False

        # Current sensor simulated values
        self.sim_emg = (300, 300)
        self.sim_eeg = 500
        self.sim_fsr = (50, 50, 50, 50, 50)

        self._latest_sensor: Optional[SensorMessage] = None
        self._latest_status: Optional[StatusMessage] = None
        self._last_rx_time: float = 0.0
        self.crc_errors = 0
        self.resync_count = 0
        self.frames_received = 0

    def initialize(self) -> bool:
        self._initialized = True
        self._last_rx_time = time.time()
        self.update_supervisor()
        return True

    def close(self) -> None:
        self._initialized = False
        self.oe_enabled = False
        self.armed = False

    def is_healthy(self) -> bool:
        if not self._initialized:
            return False
        hb_age = (time.time() - self.last_heartbeat_time) * 1000.0
        return hb_age < self.hb_timeout_ms and not self.latched_fault

    def update_supervisor(self) -> None:
        """Simulate Section 4 ESP32 supervisor rules."""
        now = time.time()
        hb_age_ms = (now - self.last_heartbeat_time) * 1000.0 if self.last_heartbeat_time > 0 else 999999.0
        hb_ok = self.had_first_heartbeat and (hb_age_ms < self.hb_timeout_ms)

        if self.estop_active:
            self.latched_fault = True

        # Heartbeat loss latches a fault only after first heartbeat was established
        if self.had_first_heartbeat and not hb_ok:
            self.latched_fault = True

        # OE is LOW (enabled) only if all are true:
        # arm_request == 1, hb_age < timeout, estop released, no latched fault, no ads fault
        if (self.arm_requested and hb_ok and not self.estop_active
                and not self.latched_fault and not self.ads_fault):
            self.oe_enabled = True
            self.armed = True
        else:
            self.oe_enabled = False
            self.armed = False

        # Build flags
        flags = 0
        if self.estop_active:
            flags |= FLAG_ESTOP_PRESSED
        if self.oe_enabled:
            flags |= FLAG_OE_ENABLED
        if self.armed:
            flags |= FLAG_ARMED
        if hb_ok:
            flags |= FLAG_HEARTBEAT_OK
        if self.force_fault:
            flags |= FLAG_FORCE_FAULT
        if self.ads_fault:
            flags |= FLAG_ADS_FAULT
        if self.latched_fault:
            flags |= FLAG_LATCHED_FAULT

        t_ms = int(now * 1000) & 0xFFFFFFFF
        self._latest_sensor = SensorMessage(
            t_ms=t_ms,
            emg=self.sim_emg,
            eeg=self.sim_eeg,
            fsr=self.sim_fsr,
            flags=flags
        )
        self._last_rx_time = now
        self.frames_received += 1

    def send_message(self, msg: object) -> None:
        if isinstance(msg, HeartbeatMessage):
            self.had_first_heartbeat = True
            self.last_heartbeat_time = time.time()
            self.arm_requested = bool(msg.arm_request == 1)
            self.update_supervisor()
        elif isinstance(msg, ConfigMessage):
            self.hb_timeout_ms = msg.hb_timeout_ms
        elif isinstance(msg, ClearFaultMessage):
            if not self.estop_active and not self.arm_requested:
                self.latched_fault = False
                self.force_fault = False
            self.update_supervisor()

    def get_latest_sensor(self) -> Optional[SensorMessage]:
        self.update_supervisor()
        return self._latest_sensor

    def get_latest_status(self) -> Optional[StatusMessage]:
        now = time.time()
        hb_age_ms = int((now - self.last_heartbeat_time) * 1000.0) if self.last_heartbeat_time > 0 else 65535
        hb_age_ms = min(65535, max(0, hb_age_ms))
        return StatusMessage(
            fw_version=0x0200,
            reset_reason=0,
            fault_code=1 if self.latched_fault else 0,
            rx_err=self.crc_errors,
            ads_err=1 if self.ads_fault else 0,
            hb_age_ms=hb_age_ms
        )

    def get_link_stats(self) -> dict:
        now = time.time()
        age_ms = (now - self._last_rx_time) * 1000.0 if self._last_rx_time > 0 else 99999.0
        return {
            "rx_rate_hz": 100.0 if self._initialized else 0.0,
            "crc_errors": self.crc_errors,
            "resyncs": self.resync_count,
            "frame_age_ms": age_ms,
            "frames_received": self.frames_received,
        }

class RealESPLink(AbstractESPLink):
    """Real serial port implementation communicating with ESP32 over UART2."""

    def __init__(self, port: str = "/dev/ttyTHS1", baudrate: int = 460800):
        self.port = port
        self.baudrate = baudrate
        self._serial = None
        self._parser = FrameParser()
        self._latest_sensor: Optional[SensorMessage] = None
        self._latest_status: Optional[StatusMessage] = None
        self._last_rx_time: float = 0.0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._tx_seq = 0
        self._lock = threading.Lock()

    def initialize(self) -> bool:
        try:
            import serial
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.01,
            )
            self._running = True
            self._thread = threading.Thread(target=self._rx_loop, daemon=True)
            self._thread.start()
            return True
        except Exception:
            self._running = False
            return False

    def close(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.5)
            self._thread = None
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

    def is_healthy(self) -> bool:
        if not self._running or not self._serial or not self._serial.is_open:
            return False
        age_ms = (time.time() - self._last_rx_time) * 1000.0 if self._last_rx_time > 0 else 99999.0
        return age_ms < 500.0

    def send_message(self, msg: object) -> None:
        if not self._serial or not self._serial.is_open:
            return
        msg_type, payload = encode_payload(msg)
        with self._lock:
            seq = self._tx_seq
            self._tx_seq = (self._tx_seq + 1) & 0xFF
            frame = encode_frame(msg_type, seq, payload)
            self._serial.write(frame)

    def _rx_loop(self) -> None:
        while self._running and self._serial and self._serial.is_open:
            try:
                raw_bytes = self._serial.read(64)
                if raw_bytes:
                    for msg_type, seq, payload in self._parser.parse(raw_bytes):
                        decoded = decode_payload(msg_type, payload)
                        now = time.time()
                        if isinstance(decoded, SensorMessage):
                            self._latest_sensor = decoded
                            self._last_rx_time = now
                        elif isinstance(decoded, StatusMessage):
                            self._latest_status = decoded
                            self._last_rx_time = now
            except Exception:
                time.sleep(0.01)

    def get_latest_sensor(self) -> Optional[SensorMessage]:
        return self._latest_sensor

    def get_latest_status(self) -> Optional[StatusMessage]:
        return self._latest_status

    def get_link_stats(self) -> dict:
        age_ms = (time.time() - self._last_rx_time) * 1000.0 if self._last_rx_time > 0 else 99999.0
        return {
            "crc_errors": self._parser.crc_errors,
            "resyncs": self._parser.resync_count,
            "frame_age_ms": age_ms,
            "frames_received": self._parser.frames_received,
        }
