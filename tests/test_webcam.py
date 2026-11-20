"""Unit tests for Generic USB Webcam HAL and Vision Worker integration."""

import time
import multiprocessing as mp
from queue import Empty
import pytest
import numpy as np
from vapa.hal import MockWebcam, GenericWebcam, create_hal, HALContainer
from vapa.vision.worker import VisionWorker
from vapa.vision.detector import GripSelectionResult


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


def test_hal_factory_with_webcam():
    """Verify HAL factory instantiates MockWebcam when camera_type is webcam."""
    hw_config = {
        "jetson": {
            "backend": "mock",
            "pca9685": {"address": 0x40, "frequency_hz": 50},
        },
        "timing": {"heartbeat_timeout_ms": 250},
    }
    hal: HALContainer = create_hal(
        hw_config,
        force_mock=True,
        enable_camera=True,
        camera_type="webcam",
    )
    assert hal.webcam is not None
    assert isinstance(hal.webcam, MockWebcam)
    assert hal.initialize_all() is True
    assert hal.webcam.is_healthy() is True

    hal.close_all()
    assert hal.webcam.is_healthy() is False


def test_vision_worker_with_webcam():
    """Verify VisionWorker with webcam mock mode runs and publishes grip selection packets."""
    queue = mp.Queue(maxsize=5)
    stop_event = mp.Event()

    worker = VisionWorker(
        result_queue=queue,
        stop_event=stop_event,
        mock_mode=True,
        fps=30,
        config_dir="config",
        camera_type="webcam",
    )

    worker.start()
    try:
        # Wait up to 1.5s for at least one vision packet
        t0 = time.time()
        packet = None
        while (time.time() - t0) < 1.5:
            try:
                packet = queue.get(timeout=0.1)
                break
            except Empty:
                pass

        assert packet is not None, "VisionWorker did not publish any packet within timeout"
        dist_res, grip_res, t_vis = packet
        # USB Webcam provides no hardware depth -> dist_res is None
        assert dist_res is None
        # Grip selection result is valid
        assert isinstance(grip_res, GripSelectionResult)
        assert grip_res.profile_name in ("cylindrical", "spherical", "pinch", "lateral", "default")
        assert t_vis > 0.0

    finally:
        stop_event.set()
        worker.join(timeout=2.0)
        if worker.is_alive():
            worker.terminate()
