"""Dedicated 30 Hz multiprocessing worker for RealSense acquisition, filtering, and detection."""

import time
import multiprocessing as mp
from queue import Empty, Full
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import yaml
import logging

from .distance_matrix import DistanceMatrixProcessor, DistanceMatrixResult
from .filters import SoftwareDepthFilter, FilterConfig
from .detector import MockObjectDetector, ONNXObjectDetector, GripSelector, GripSelectionResult
from ..hal.realsense import MockRealSense, RealRealSense

logger = logging.getLogger("vapa.vision.worker")

class VisionWorker(mp.Process):
    """Multiprocessing worker running vision capture, filtering, and detection at ~30 Hz.

    Ensures the 100 Hz main control loop never blocks on camera I/O or model inference.
    """

    def __init__(
        self,
        result_queue: mp.Queue,
        stop_event: mp.Event,
        mock_mode: bool = True,
        fps: int = 30,
        config_dir: str = "config",
    ):
        super().__init__(name="VisionWorker", daemon=True)
        self.result_queue = result_queue
        self.stop_event = stop_event
        self.mock_mode = mock_mode
        self.fps = fps
        self.config_dir = Path(config_dir)

    def run(self) -> None:
        """Worker loop running at ~30 fps."""
        logger.info("VisionWorker process started.")

        # Load vision configuration
        vision_cfg_path = self.config_dir / "vision.yaml"
        vision_cfg = {}
        if vision_cfg_path.exists():
            with open(vision_cfg_path, "r") as f:
                vision_cfg = yaml.safe_load(f) or {}

        # 1. Initialize Camera
        cam_cfg = vision_cfg.get("camera", {})
        width = cam_cfg.get("width", 640)
        height = cam_cfg.get("height", 480)

        if self.mock_mode:
            camera = MockRealSense(width=width, height=height, fps=self.fps)
        else:
            camera = RealRealSense(width=width, height=height, fps=self.fps, filter_config=cam_cfg.get("filters", {}))

        if not camera.initialize():
            logger.error("VisionWorker failed to initialize camera. Worker exiting.")
            return

        # 2. Initialize Filters & Processors
        depth_filter = SoftwareDepthFilter(FilterConfig())
        dist_cfg = vision_cfg.get("distance_matrix", {})
        dist_proc = DistanceMatrixProcessor(
            grid_rows=dist_cfg.get("grid_rows", 12),
            grid_cols=dist_cfg.get("grid_cols", 16),
            z_min_m=dist_cfg.get("roi", {}).get("z_min_m", 0.10),
            z_max_m=dist_cfg.get("roi", {}).get("z_max_m", 0.80),
        )

        # 3. Initialize Detector & GripSelector
        det_cfg = vision_cfg.get("detection", {})
        class_map = vision_cfg.get("class_to_profile", {})

        if self.mock_mode:
            detector = MockObjectDetector()
        else:
            model_path = det_cfg.get("model_path", "models/yolov8n_prosthetics.onnx")
            detector = ONNXObjectDetector(model_path=model_path, confidence_threshold=det_cfg.get("confidence_threshold", 0.45))

        grip_selector = GripSelector(
            detector=detector,
            class_to_profile=class_map,
            confidence_threshold=det_cfg.get("confidence_threshold", 0.45),
            voting_n=det_cfg.get("voting_n", 5),
            voting_m=det_cfg.get("voting_m", 7),
        )

        dt = 1.0 / self.fps

        try:
            while not self.stop_event.is_set():
                t_start = time.perf_counter()

                # Capture frames
                try:
                    color, depth, t_frame = camera.capture_frame()
                except Exception as e:
                    logger.warning(f"Frame capture error: {e}")
                    time.sleep(0.01)
                    continue

                # Filter depth
                filtered_depth = depth_filter.process(depth)

                # Process 3D distance matrix
                dist_result = dist_proc.process(filtered_depth, timestamp=t_frame)

                # Process object detection & grip profile voting
                grip_result = grip_selector.process(color)

                # Publish to queue (keep only freshest frame)
                payload = (dist_result, grip_result, t_frame)
                try:
                    if self.result_queue.full():
                        try:
                            self.result_queue.get_nowait()
                        except Empty:
                            pass
                    self.result_queue.put_nowait(payload)
                except Full:
                    pass

                # Rate limiting to target FPS
                elapsed = time.perf_counter() - t_start
                sleep_s = max(0.0, dt - elapsed)
                time.sleep(sleep_s)

        finally:
            camera.close()
            logger.info("VisionWorker process cleanly stopped.")
