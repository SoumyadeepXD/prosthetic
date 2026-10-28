"""Object detection, class-to-profile mapping, and N-of-M temporal voting filter."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
from collections import deque, Counter
import numpy as np
import logging

logger = logging.getLogger(__name__)

@dataclass
class Detection:
    class_name: str
    confidence: float
    bounding_box: Tuple[float, float, float, float]  # Normalized (x_min, y_min, x_max, y_max) in [0..1]

@dataclass
class GripSelectionResult:
    profile_name: str
    confidence: float
    class_name: Optional[str]
    bounding_box: Optional[Tuple[float, float, float, float]]
    is_locked: bool

class AbstractObjectDetector(ABC):
    """Abstract interface for object detector backends."""

    @abstractmethod
    def detect(self, color_image: np.ndarray) -> List[Detection]:
        """Detect objects in RGB/BGR color image.

        Args:
            color_image: (H, W, 3) uint8 numpy array.

        Returns:
            List of Detection objects sorted by confidence descending.
        """
        pass

class MockObjectDetector(AbstractObjectDetector):
    """Mock object detector returning configurable detections for testing and simulation."""

    def __init__(
        self,
        default_class: str = "bottle",
        confidence: float = 0.85,
        bounding_box: Tuple[float, float, float, float] = (0.3, 0.3, 0.7, 0.7),
    ):
        self.detections: List[Detection] = [
            Detection(class_name=default_class, confidence=confidence, bounding_box=bounding_box)
        ]

    def set_detection(
        self,
        class_name: str,
        confidence: float = 0.85,
        bounding_box: Tuple[float, float, float, float] = (0.3, 0.3, 0.7, 0.7),
    ) -> None:
        """Set a single active detection."""
        self.detections = [
            Detection(class_name=class_name, confidence=confidence, bounding_box=bounding_box)
        ]

    def set_detections(self, detections: List[Detection]) -> None:
        """Set multiple active detections."""
        self.detections = detections

    def clear(self) -> None:
        """Clear all active detections (simulate empty scene)."""
        self.detections = []

    def detect(self, color_image: np.ndarray) -> List[Detection]:
        return list(self.detections)

class ONNXObjectDetector(AbstractObjectDetector):
    """ONNX Runtime detector backend for lightweight YOLOv8n models on Jetson Orin Nano."""

    def __init__(
        self,
        model_path: str,
        confidence_threshold: float = 0.45,
        input_size: Tuple[int, int] = (640, 640),
        classes: Optional[List[str]] = None,
    ):
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.input_size = input_size
        self.classes = classes or [
            "bottle", "can", "cup", "glass", "wine_glass", "apple", "orange",
            "sports_ball", "cell_phone", "pen", "spoon", "fork", "book", "plate"
        ]
        self._session = None
        self._initialize_session()

    def _initialize_session(self) -> bool:
        try:
            import onnxruntime as ort
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            self._session = ort.InferenceSession(self.model_path, providers=providers)
            logger.info(f"Loaded ONNX model from {self.model_path} with providers {self._session.get_providers()}")
            return True
        except Exception as e:
            logger.warning(f"ONNX session initialization skipped ({e}). Operating in standby.")
            self._session = None
            return False

    def detect(self, color_image: np.ndarray) -> List[Detection]:
        if self._session is None:
            return []

        # Standard YOLOv8 pre-processing
        h, w = color_image.shape[:2]
        net_w, net_h = self.input_size

        # Simple aspect ratio scaling
        scale = min(net_w / w, net_h / h)
        new_w, new_h = int(w * scale), int(h * scale)

        # Pad and normalize
        import cv2
        resized = cv2.resize(color_image, (new_w, new_h))
        padded = np.zeros((net_h, net_w, 3), dtype=np.uint8)
        padded[:new_h, :new_w] = resized

        blob = padded.astype(np.float32) / 255.0
        blob = np.transpose(blob, (2, 0, 1))  # HWC to CHW
        blob = np.expand_dims(blob, axis=0)  # Add batch dim

        input_name = self._session.get_inputs()[0].name
        outputs = self._session.run(None, {input_name: blob})[0]

        # Process detections: output shape (1, 4 + num_classes, num_anchors)
        detections: List[Detection] = []
        predictions = np.transpose(outputs[0])  # (num_anchors, 4 + num_classes)

        for pred in predictions:
            box = pred[:4]
            scores = pred[4:]
            class_id = int(np.argmax(scores))
            conf = float(scores[class_id])

            if conf >= self.confidence_threshold:
                # Convert center-xywh to normalized xyxy
                cx, cy, bw, bh = box
                x1 = max(0.0, (cx - bw / 2) / net_w)
                y1 = max(0.0, (cy - bh / 2) / net_h)
                x2 = min(1.0, (cx + bw / 2) / net_w)
                y2 = min(1.0, (cy + bh / 2) / net_h)

                class_name = self.classes[class_id] if class_id < len(self.classes) else f"class_{class_id}"
                detections.append(Detection(class_name=class_name, confidence=conf, bounding_box=(x1, y1, x2, y2)))

        # Sort by confidence descending
        detections.sort(key=lambda d: d.confidence, reverse=True)
        return detections

class TemporalProfileVoter:
    """N-of-M majority voting filter for stability across detection frames."""

    def __init__(self, window_m: int = 7, min_votes_n: int = 5, default_profile: str = "default"):
        self.window_m = window_m
        self.min_votes_n = min_votes_n
        self.default_profile = default_profile
        self.history: deque[str] = deque(maxlen=window_m)
        self.locked_profile: str = default_profile

    def reset(self) -> None:
        """Reset vote history and restore default locked profile."""
        self.history.clear()
        self.locked_profile = self.default_profile

    def update(self, candidate_profile: Optional[str]) -> Tuple[str, bool]:
        """Update voting history and return (active_profile, is_locked).

        Returns:
            Tuple of:
            - profile_name: currently active grip profile
            - is_locked: True if candidate achieved >= N votes out of M window
        """
        profile = candidate_profile if candidate_profile else self.default_profile
        self.history.append(profile)

        counts = Counter(self.history)
        most_common, count = counts.most_common(1)[0]

        if count >= self.min_votes_n:
            self.locked_profile = most_common
            return self.locked_profile, True

        # Keep current locked profile until a candidate achieves N votes
        return self.locked_profile, False

class GripSelector:
    """Coordinates object detection, class-to-profile mapping, and temporal voting."""

    DEFAULT_CLASS_MAP = {
        "bottle": "cylindrical",
        "can": "cylindrical",
        "cup": "fragile_cup",
        "glass": "fragile_cup",
        "wine_glass": "fragile_cup",
        "apple": "spherical",
        "orange": "spherical",
        "sports_ball": "spherical",
        "cell_phone": "pinch",
        "pen": "pinch",
        "spoon": "pinch",
        "fork": "pinch",
        "book": "lateral",
        "plate": "flat",
        "default": "default",
    }

    def __init__(
        self,
        detector: AbstractObjectDetector,
        class_to_profile: Optional[Dict[str, str]] = None,
        confidence_threshold: float = 0.45,
        voting_n: int = 5,
        voting_m: int = 7,
        default_profile: str = "default",
    ):
        self.detector = detector
        self.class_map = class_to_profile or dict(self.DEFAULT_CLASS_MAP)
        self.confidence_threshold = confidence_threshold
        self.default_profile = default_profile
        self.voter = TemporalProfileVoter(
            window_m=voting_m,
            min_votes_n=voting_n,
            default_profile=default_profile,
        )

    def reset(self) -> None:
        self.voter.reset()

    def process(self, color_image: np.ndarray) -> GripSelectionResult:
        """Run detection and voting pipeline on color frame.

        Returns:
            GripSelectionResult containing profile name, confidence, and target bounding box.
        """
        detections = self.detector.detect(color_image)

        candidate_profile = self.default_profile
        detected_class: Optional[str] = None
        detected_conf = 0.0
        bbox: Optional[Tuple[float, float, float, float]] = None

        if detections:
            # Consider highest confidence detection
            top = detections[0]
            if top.confidence >= self.confidence_threshold:
                mapped = self.class_map.get(top.class_name.lower())
                if mapped:
                    candidate_profile = mapped
                    detected_class = top.class_name
                    detected_conf = top.confidence
                    bbox = top.bounding_box
                else:
                    # Unknown class: fallback to default
                    candidate_profile = self.default_profile
                    detected_class = top.class_name
                    detected_conf = top.confidence
                    bbox = top.bounding_box

        active_profile, is_locked = self.voter.update(candidate_profile)

        return GripSelectionResult(
            profile_name=active_profile,
            confidence=detected_conf,
            class_name=detected_class,
            bounding_box=bbox,
            is_locked=is_locked,
        )
