"""Unit tests for Generic USB Webcam HAL."""

import pytest
import numpy as np
from vapa.hal import MockWebcam, GenericWebcam


def test_mock_webcam_initialization_and_capture():
    cam = MockWebcam(width=640, height=480, fps=30)
    assert cam.is_healthy() is False

    assert cam.initialize() is True
    assert cam.is_healthy() is True

    frame, t = cam.capture_frame()
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (480, 640, 3)
    assert frame.dtype == np.uint8
    assert t > 0.0

    cam.close()
    assert cam.is_healthy() is False
    with pytest.raises(RuntimeError):
        cam.capture_frame()


def test_generic_webcam_graceful_missing_device():
    """Verify GenericWebcam fails gracefully when no physical camera is attached."""
    # Attempting to open high device index (e.g. 99) should fail cleanly without crash
    cam = GenericWebcam(device_index=99)
    # If OpenCV is not installed or device does not exist, initialize returns False
    ok = cam.initialize()
    assert ok is False
    assert cam.is_healthy() is False
    with pytest.raises(RuntimeError):
        cam.capture_frame()
    cam.close()
