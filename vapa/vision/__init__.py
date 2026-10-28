"""VAPA Vision Package."""

from .distance_matrix import DistanceMatrixProcessor, DistanceMatrixResult
from .filters import SoftwareDepthFilter, FilterConfig
from .detector import (
    Detection,
    GripSelectionResult,
    AbstractObjectDetector,
    MockObjectDetector,
    ONNXObjectDetector,
    TemporalProfileVoter,
    GripSelector,
)
from .replay import VisionSequenceRecorder, VisionReplayHarness
from .worker import VisionWorker

__all__ = [
    "DistanceMatrixProcessor",
    "DistanceMatrixResult",
    "SoftwareDepthFilter",
    "FilterConfig",
    "Detection",
    "GripSelectionResult",
    "AbstractObjectDetector",
    "MockObjectDetector",
    "ONNXObjectDetector",
    "TemporalProfileVoter",
    "GripSelector",
    "VisionSequenceRecorder",
    "VisionReplayHarness",
    "VisionWorker",
]
