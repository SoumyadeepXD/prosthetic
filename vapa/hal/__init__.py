"""VAPA Hardware Abstraction Layer (HAL)."""

from .base import BaseDevice
from .pca9685 import AbstractPCA9685, MockPCA9685, RealPCA9685
from .esp_link import AbstractESPLink, MockESPLink, RealESPLink
from .mock_esp32_pty import MockESP32Pty
from .realsense import AbstractRealSense, MockRealSense, RealRealSense
from .webcam import AbstractWebcam, MockWebcam, GenericWebcam
from .factory import create_hal, create_hal_container, HALContainer

__all__ = [
    "BaseDevice",
    "AbstractPCA9685", "MockPCA9685", "RealPCA9685",
    "AbstractESPLink", "MockESPLink", "RealESPLink", "MockESP32Pty",
    "AbstractRealSense", "MockRealSense", "RealRealSense",
    "AbstractWebcam", "MockWebcam", "GenericWebcam",
    "create_hal", "create_hal_container", "HALContainer",
]
