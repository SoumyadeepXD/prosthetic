"""Generic USB Webcam driver with Mock and Real (V4L2 / OpenCV) backends.

Provides video capture for generic USB webcams on NVIDIA Jetson or development PCs,
used for visual perception and proximity sensing as an alternative to stereo depth cameras.
"""

import time
import logging
from abc import abstractmethod
from typing import Tuple, Optional, Dict, Any
import numpy as np
from .base import BaseDevice

logger = logging.getLogger(__name__)


class AbstractWebcam(BaseDevice):
    """Abstract interface for standard USB webcam video capture."""

    @abstractmethod
    def capture_frame(self) -> Tuple[np.ndarray, float]:
        """Capture one color frame from the webcam.

        Returns:
            Tuple of:
            - color: np.ndarray (H, W, 3) uint8 BGR image
            - timestamp: float (epoch time in seconds)
        """
        pass


class MockWebcam(AbstractWebcam):
    """Mock webcam generating synthetic test frames for unit tests and CI."""

    def __init__(
        self,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
        target_name: str = "bottle",
    ):
        self.width = width
        self.height = height
        self.fps = fps
        self.target_name = target_name
        self._initialized = False
        self._frame_count = 0

    def initialize(self) -> bool:
        self._initialized = True
        self._frame_count = 0
        logger.info(f"MockWebcam initialized ({self.width}x{self.height} @ {self.fps}fps)")
        return True

    def close(self) -> None:
        self._initialized = False

    def is_healthy(self) -> bool:
        return self._initialized

    def capture_frame(self) -> Tuple[np.ndarray, float]:
        if not self._initialized:
            raise RuntimeError("MockWebcam not initialized")

        t = time.time()
        self._frame_count += 1

        # Generate a synthetic BGR frame
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        frame[:, :] = [30, 30, 30]  # Dark gray background

        # Draw a synthetic target object in the center
        cy, cx = self.height // 2, self.width // 2
        r = 60
        frame[cy - r : cy + r, cx - r : cx + r] = [0, 180, 220]  # Colored block

        return frame, t


class GenericWebcam(AbstractWebcam):
    """Generic USB webcam interface using standard OpenCV / V4L2 video capture."""

    def __init__(
        self,
        device_index: int = 0,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
    ):
        self.device_index = device_index
        self.width = width
        self.height = height
        self.fps = fps
        self._cap = None
        self._healthy = False

    def initialize(self) -> bool:
        try:
            import cv2  # type: ignore
        except ImportError:
            logger.warning(
                "OpenCV (cv2) is not installed. GenericWebcam cannot open physical camera. "
                "Install with: pip install opencv-python"
            )
            self._healthy = False
            return False

        try:
            self._cap = cv2.VideoCapture(self.device_index)
            if not self._cap.isOpened():
                logger.error(f"Cannot open webcam device at index {self.device_index}")
                self._healthy = False
                return False

            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self._cap.set(cv2.CAP_PROP_FPS, self.fps)

            # Warm-up grab
            ret, _ = self._cap.read()
            if not ret:
                logger.warning(f"Failed to read test frame from webcam index {self.device_index}")
                self._healthy = False
                return False

            self._healthy = True
            logger.info(
                f"GenericWebcam connected on /dev/video{self.device_index} "
                f"({self.width}x{self.height} @ {self.fps}fps)"
            )
            return True
        except Exception as e:
            logger.error(f"GenericWebcam initialization failed: {e}")
            self._healthy = False
            return False

    def close(self) -> None:
        self._healthy = False
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def is_healthy(self) -> bool:
        return self._healthy and (self._cap is not None) and self._cap.isOpened()

    def capture_frame(self) -> Tuple[np.ndarray, float]:
        if not self.is_healthy() or self._cap is None:
            raise RuntimeError("GenericWebcam is not initialized or healthy")

        ret, frame = self._cap.read()
        t = time.time()
        if not ret or frame is None:
            raise RuntimeError("GenericWebcam failed to grab frame from video device")

        return frame, t
