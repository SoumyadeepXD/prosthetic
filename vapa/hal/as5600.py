"""AS5600 12-bit magnetic angle encoder HAL driver with Mock and Real backends.

Implements:
- 12-bit angle reading over I2C through TCA9548A switch.
- STATUS register checks: MD (magnet detected), ML (too weak), MH (too strong).
- Continuous angle unwrapping across the 0/4095 (360 deg) boundary.
- Per-joint zero-offset calibration and direction multiplier (+1 / -1).
- Configurable retries on bus errors.
- Read latency measurement.
"""

import time
import logging
from abc import abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Any
from .base import BaseDevice
from .tca9548a import AbstractTCA9548A

logger = logging.getLogger(__name__)

STATUS_REG = 0x0B
RAW_ANGLE_H_REG = 0x0C
RAW_ANGLE_L_REG = 0x0D

BIT_MD = 1 << 5  # Magnet detected
BIT_ML = 1 << 4  # Magnet too weak
BIT_MH = 1 << 3  # Magnet too strong

@dataclass
class EncoderStatus:
    joint_name: str
    channel: int
    magnet_detected: bool
    magnet_too_weak: bool
    magnet_too_strong: bool
    raw_angle_ticks: int
    unwrapped_degrees: float
    joint_angle_degrees: float

    @property
    def is_valid(self) -> bool:
        """Encoder is valid only if magnet is detected and neither too weak nor too strong."""
        return self.magnet_detected and not self.magnet_too_weak and not self.magnet_too_strong

class JointTracker:
    """Tracks raw ticks and continuous unwrapping across the 0/4095 boundary."""

    def __init__(self, channel: int, zero_offset_deg: float = 0.0, direction: int = 1):
        self.channel = channel
        self.zero_offset_deg = zero_offset_deg
        self.direction = 1 if direction >= 0 else -1
        self.last_raw_ticks: Optional[int] = None
        self.cumulative_ticks: int = 0

    def update(self, raw_ticks: int) -> Tuple[float, float]:
        """Update with new 12-bit tick reading (0-4095).

        Returns:
            (unwrapped_degrees, calibrated_joint_angle_degrees)
        """
        raw_ticks = raw_ticks & 0x0FFF  # Ensure 12-bit

        if self.last_raw_ticks is None:
            self.last_raw_ticks = raw_ticks
            self.cumulative_ticks = raw_ticks
        else:
            delta = raw_ticks - self.last_raw_ticks
            # Handle boundary wraps
            if delta > 2048:
                delta -= 4096  # Crossed 0 in reverse
            elif delta < -2048:
                delta += 4096  # Crossed 4095 moving forward

            self.cumulative_ticks += delta
            self.last_raw_ticks = raw_ticks

        unwrapped_deg = (self.cumulative_ticks / 4096.0) * 360.0
        joint_deg = self.direction * (unwrapped_deg - self.zero_offset_deg)
        return unwrapped_deg, joint_deg

class AbstractAS5600(BaseDevice):
    """Abstract interface for AS5600 magnetic encoders via TCA9548A multiplexer."""

    @abstractmethod
    def read_joint_status(self, joint_name: str) -> EncoderStatus:
        """Read 12-bit angle and status for specified joint."""
        pass

    def read_joint_angle(self, joint_name: str) -> EncoderStatus:
        """Alias for read_joint_status."""
        return self.read_joint_status(joint_name)

    @abstractmethod
    def read_angle(self, joint_name: str) -> float:
        """Read calibrated joint angle in degrees."""
        pass

    @abstractmethod
    def verify_all_magnets(self) -> bool:
        """Verify all active joint encoders have valid magnet positions."""
        pass

    @abstractmethod
    def benchmark_read_latency(self, iterations: int = 50) -> float:
        """Benchmark average read time per cycle across all joints in milliseconds."""
        pass

class MockAS5600(AbstractAS5600):
    """Mock AS5600 magnetic encoder array for offline simulation and testing."""

    def __init__(self, joint_config: Optional[Dict[str, Any]] = None):
        cfg = joint_config or {
            "finger_group": {"channel": 0, "zero_offset_deg": 0.0, "direction": 1},
            "wrist_flex": {"channel": 1, "zero_offset_deg": 0.0, "direction": 1},
            "wrist_rotate": {"channel": 2, "zero_offset_deg": 0.0, "direction": 1},
            "forearm_rotation": {"channel": 3, "zero_offset_deg": 0.0, "direction": 1},
        }

        self.trackers: Dict[str, JointTracker] = {}
        self._raw_angles: Dict[str, int] = {}
        self._magnet_ok: Dict[str, bool] = {}
        self._initialized = False

        for name, params in cfg.items():
            if isinstance(params, int):
                ch = params
                zero = 0.0
                dir_val = 1
            else:
                ch = params.get("channel", 0)
                zero = float(params.get("zero_offset_deg", 0.0))
                dir_val = int(params.get("direction", 1))

            self.trackers[name] = JointTracker(ch, zero, dir_val)
            self._raw_angles[name] = 2048
            self._magnet_ok[name] = True

    def initialize(self) -> bool:
        self._initialized = True
        return True

    def close(self) -> None:
        self._initialized = False

    def is_healthy(self) -> bool:
        return self._initialized and self.verify_all_magnets()

    def set_mock_angle(self, joint_name: str, raw_ticks: int) -> None:
        if joint_name not in self.trackers:
            raise ValueError(f"Unknown joint: {joint_name}")
        self._raw_angles[joint_name] = max(0, min(4095, raw_ticks))

    def set_mock_magnet(self, joint_name: str, valid: bool) -> None:
        if joint_name not in self.trackers:
            raise ValueError(f"Unknown joint: {joint_name}")
        self._magnet_ok[joint_name] = valid

    def read_joint_status(self, joint_name: str) -> EncoderStatus:
        if joint_name not in self.trackers:
            raise ValueError(f"Unknown joint: {joint_name}")

        ticks = self._raw_angles[joint_name]
        is_ok = self._magnet_ok[joint_name]
        unwrapped_deg, joint_deg = self.trackers[joint_name].update(ticks)

        return EncoderStatus(
            joint_name=joint_name,
            channel=self.trackers[joint_name].channel,
            magnet_detected=is_ok,
            magnet_too_weak=False if is_ok else True,
            magnet_too_strong=False,
            raw_angle_ticks=ticks,
            unwrapped_degrees=unwrapped_deg,
            joint_angle_degrees=joint_deg,
        )

    def read_angle(self, joint_name: str) -> float:
        st = self.read_joint_status(joint_name)
        if not st.is_valid:
            raise RuntimeError(f"AS5600 for {joint_name} invalid magnet status")
        return st.joint_angle_degrees

    def verify_all_magnets(self) -> bool:
        return all(self._magnet_ok.values())

    def benchmark_read_latency(self, iterations: int = 50) -> float:
        t0 = time.perf_counter()
        for _ in range(iterations):
            for j in self.trackers:
                self.read_joint_status(j)
        elapsed = time.perf_counter() - t0
        return (elapsed / iterations) * 1000.0

class RealAS5600(AbstractAS5600):
    """Real AS5600 array read over I2C through TCA9548A switch on Linux/Jetson."""

    def __init__(
        self,
        mux: AbstractTCA9548A,
        bus_num: int = 7,
        address: int = 0x36,
        joint_config: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
    ):
        self.mux = mux
        self.bus_num = bus_num
        self.address = address
        self.max_retries = max_retries

        cfg = joint_config or {
            "finger_group": {"channel": 0, "zero_offset_deg": 0.0, "direction": 1},
            "wrist_flex": {"channel": 1, "zero_offset_deg": 0.0, "direction": 1},
            "wrist_rotate": {"channel": 2, "zero_offset_deg": 0.0, "direction": 1},
            "forearm_rotation": {"channel": 3, "zero_offset_deg": 0.0, "direction": 1},
        }

        self.trackers: Dict[str, JointTracker] = {}
        for name, params in cfg.items():
            if isinstance(params, int):
                ch = params
                zero = 0.0
                dir_val = 1
            else:
                ch = params.get("channel", 0)
                zero = float(params.get("zero_offset_deg", 0.0))
                dir_val = int(params.get("direction", 1))
            self.trackers[name] = JointTracker(ch, zero, dir_val)

        self._bus = None
        self._healthy = False

    def initialize(self) -> bool:
        try:
            from smbus2 import SMBus
            self._bus = SMBus(self.bus_num)
            self._healthy = True
            return self.verify_all_magnets()
        except Exception as e:
            logger.error(f"Failed to initialize RealAS5600 on bus {self.bus_num}: {e}")
            self._healthy = False
            return False

    def close(self) -> None:
        if self._bus:
            try:
                self._bus.close()
            except Exception:
                pass
            self._bus = None
        self._healthy = False

    def is_healthy(self) -> bool:
        return self._healthy and self.verify_all_magnets()

    def read_joint_status(self, joint_name: str) -> EncoderStatus:
        if joint_name not in self.trackers:
            raise ValueError(f"Unknown joint: {joint_name}")
        if not self._bus or not self._healthy:
            raise RuntimeError("AS5600 driver not initialized")

        tracker = self.trackers[joint_name]
        ch = tracker.channel

        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                self.mux.select_channel(ch)
                # Read STATUS register
                status_byte = self._bus.read_byte_data(self.address, STATUS_REG)
                md = bool(status_byte & BIT_MD)
                ml = bool(status_byte & BIT_ML)
                mh = bool(status_byte & BIT_MH)

                # Read raw angle (12-bit)
                raw_h = self._bus.read_byte_data(self.address, RAW_ANGLE_H_REG)
                raw_l = self._bus.read_byte_data(self.address, RAW_ANGLE_L_REG)
                raw_ticks = ((raw_h & 0x0F) << 8) | raw_l

                unwrapped_deg, joint_deg = tracker.update(raw_ticks)

                return EncoderStatus(
                    joint_name=joint_name,
                    channel=ch,
                    magnet_detected=md,
                    magnet_too_weak=ml,
                    magnet_too_strong=mh,
                    raw_angle_ticks=raw_ticks,
                    unwrapped_degrees=unwrapped_deg,
                    joint_angle_degrees=joint_deg,
                )
            except Exception as e:
                last_err = e
            finally:
                self.mux.deselect()

        raise RuntimeError(f"AS5600 read failed for joint {joint_name} after {self.max_retries} attempts: {last_err}")

    def read_angle(self, joint_name: str) -> float:
        st = self.read_joint_status(joint_name)
        if not st.is_valid:
            raise RuntimeError(f"AS5600 magnet status invalid for {joint_name}")
        return st.joint_angle_degrees

    def verify_all_magnets(self) -> bool:
        for joint in self.trackers:
            try:
                st = self.read_joint_status(joint)
                if not st.is_valid:
                    return False
            except Exception:
                return False
        return True

    def benchmark_read_latency(self, iterations: int = 50) -> float:
        t0 = time.perf_counter()
        for _ in range(iterations):
            for j in self.trackers:
                self.read_joint_status(j)
        elapsed = time.perf_counter() - t0
        return (elapsed / iterations) * 1000.0
