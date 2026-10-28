"""Abstract base classes and factory for Hardware Abstraction Layer (HAL)."""

from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseDevice(ABC):
    """Base interface for all hardware devices in the HAL."""

    @abstractmethod
    def initialize(self) -> bool:
        """Initialize and verify communication with device. Returns True on success."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Safely shutdown or release device handles."""
        pass

    @abstractmethod
    def is_healthy(self) -> bool:
        """Check if device is currently responding and within operational parameters."""
        pass
