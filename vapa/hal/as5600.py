"""AS5600 12-bit magnetic angle encoder HAL driver with Mock and Real backends."""

from abc import abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from .base import BaseDevice
from .tca9548a import AbstractTCA9548A

STATUS_REG = 0x0B
RAW_ANGLE_H_REG = 0x0C
RAW_ANGLE_L_REG = 0x0D

BIT_MD = 1 << 5  # Magnet detected
BIT_ML = 1 << 4  # Magnet too weak
BIT_MH = 1 << 3  # Magnet too strong

@dataclass
class EncoderStatus:
    magnet_detected: bool
    magnet_too_weak: bool
    magnet_too_strong: bool
    raw_angle_ticks: int
    angle_degrees: float

    @property
    def is_valid(self) -> bool:
        return self.magnet_detected and not self.magnet_too_weak and not self.magnet_too_strong

class AbstractAS5600(BaseDevice):
    """Abstract interface for AS5600 magnetic encoders via TCA9548A multiplexer."""

    @abstractmethod
    def read_joint_angle(self, joint_name: str) -> EncoderStatus:
        """Read 12-bit angle and status for specified joint."""
        pass

    @abstractmethod
    def verify_all_magnets(self) -> bool:
        """Verify all active joint encoders have valid magnet positions."""
        pass

class MockAS5600(AbstractAS5600):
    """Mock AS5600 magnetic encoder array."""

    def __init__(self, joint_config: Optional[Dict[str, int]] = None):
        self.joint_config = joint_config or {
            "finger_group": 0,
            "wrist_flex": 1,
            "wrist_rotate": 2,
            "forearm_rotation": 3,
        }
        self._raw_angles: Dict[str, int] = {k: 2048 for k in self.joint_config}
        self._magnet_ok: Dict[str, bool] = {k: True for k in self.joint_config}
        self._initialized = False

    def initialize(self) -> bool:
        self._initialized = True
        return True

    def close(self) -> None:
        self._initialized = False

    def is_healthy(self) -> bool:
        return self._initialized and self.verify_all_magnets()

    def set_mock_angle(self, joint_name: str, raw_ticks: int) -> None:
        self._raw_angles[joint_name] = max(0, min(4095, raw_ticks))

    def set_mock_magnet(self, joint_name: str, valid: bool) -> None:
        self._magnet_ok[joint_name] = valid

    def read_joint_angle(self, joint_name: str) -> EncoderStatus:
        if joint_name not in self.joint_config:
            raise ValueError(f"Unknown joint: {joint_name}")

        ticks = self._raw_angles[joint_name]
        is_ok = self._magnet_ok[joint_name]
        deg = (ticks / 4096.0) * 360.0

        return EncoderStatus(
            magnet_detected=is_ok,
            magnet_too_weak=False if is_ok else True,
            magnet_too_strong=False,
            raw_angle_ticks=ticks,
            angle_degrees=deg,
        )

    def verify_all_magnets(self) -> bool:
        return all(self._magnet_ok.values())

class RealAS5600(AbstractAS5600):
    """Real AS5600 array read over I2C through TCA9548A switch."""

    def __init__(
        self,
        mux: AbstractTCA9548A,
        bus_num: int = 7,
        address: int = 0x36,
        joint_config: Optional[Dict[str, int]] = None,
    ):
        self.mux = mux
        self.bus_num = bus_num
        self.address = address
        self.joint_config = joint_config or {
            "finger_group": 0,
            "wrist_flex": 1,
            "wrist_rotate": 2,
            "forearm_rotation": 3,
        }
        self._bus = None
        self._healthy = False

    def initialize(self) -> bool:
        try:
            from smbus2 import SMBus
            self._bus = SMBus(self.bus_num)
            self._healthy = True
            return self.verify_all_magnets()
        except Exception:
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

    def read_joint_angle(self, joint_name: str) -> EncoderStatus:
        if joint_name not in self.joint_config:
            raise ValueError(f"Unknown joint: {joint_name}")
        if not self._bus or not self._healthy:
            raise RuntimeError("AS5600 driver not initialized")

        ch = self.joint_config[joint_name]
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
            deg = (raw_ticks / 4096.0) * 360.0

            return EncoderStatus(
                magnet_detected=md,
                magnet_too_weak=ml,
                magnet_too_strong=mh,
                raw_angle_ticks=raw_ticks,
                angle_degrees=deg,
            )
        finally:
            self.mux.deselect()

    def verify_all_magnets(self) -> bool:
        for joint in self.joint_config:
            try:
                st = self.read_joint_angle(joint)
                if not st.is_valid:
                    return False
            except Exception:
                return False
        return True
