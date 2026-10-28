"""VAPA Hardware Abstraction Layer (HAL)."""

from .base import BaseDevice
from .pca9685 import AbstractPCA9685, MockPCA9685, RealPCA9685
from .tca9548a import AbstractTCA9548A, MockTCA9548A, RealTCA9548A
from .as5600 import AbstractAS5600, MockAS5600, RealAS5600, EncoderStatus
from .esp_link import AbstractESPLink, MockESPLink, RealESPLink
from .mock_esp32_pty import MockESP32Pty
from .realsense import AbstractRealSense, MockRealSense, RealRealSense
from .factory import create_hal, HALContainer

__all__ = [
    "BaseDevice",
    "AbstractPCA9685", "MockPCA9685", "RealPCA9685",
    "AbstractTCA9548A", "MockTCA9548A", "RealTCA9548A",
    "AbstractAS5600", "MockAS5600", "RealAS5600", "EncoderStatus",
    "AbstractESPLink", "MockESPLink", "RealESPLink", "MockESP32Pty",
    "AbstractRealSense", "MockRealSense", "RealRealSense",
    "create_hal", "HALContainer",
]
