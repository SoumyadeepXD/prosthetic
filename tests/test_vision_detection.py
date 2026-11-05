"""Comprehensive unit tests for object detection, class-to-profile mapping, and N-of-M temporal voting."""

import pytest
import yaml
import numpy as np
from vapa.vision import (
    Detection,
    GripSelectionResult,
    MockObjectDetector,
    TemporalProfileVoter,
    GripSelector,
)


def test_class_to_profile_mapping_from_config():
    with open("config/vision.yaml", "r") as f:
        vision_cfg = yaml.safe_load(f)

    class_map = vision_cfg.get("class_to_profile", {})
    mock_detector = MockObjectDetector()
    selector = GripSelector(detector=mock_detector, class_to_profile=class_map, voting_n=1, voting_m=1)
    img = np.zeros((480, 640, 3), dtype=np.uint8)

    # Test mapped categories
    test_cases = [
        ("bottle", "cylindrical"),
        ("can", "cylindrical"),
        ("cup", "fragile_cup"),
        ("wine_glass", "fragile_cup"),
        ("apple", "spherical"),
        ("sports_ball", "spherical"),
        ("cell_phone", "pinch"),
        ("pen", "pinch"),
        ("fork", "pinch"),
        ("book", "lateral"),
        ("plate", "flat"),
        ("unknown_tool", "default"),  # Unknown class fallback
    ]

    for class_name, expected_profile in test_cases:
        mock_detector.set_detection(class_name=class_name, confidence=0.85)
        res = selector.process(img)
        assert res.profile_name == expected_profile
        assert res.confidence == 0.85


def test_confidence_threshold_gating():
    mock_detector = MockObjectDetector()
    selector = GripSelector(
        detector=mock_detector,
        confidence_threshold=0.45,
        voting_n=1,
        voting_m=1,
    )
    img = np.zeros((480, 640, 3), dtype=np.uint8)

    # Case 1: High confidence (0.80 >= 0.45) -> maps to profile
    mock_detector.set_detection("bottle", confidence=0.80)
    res = selector.process(img)
    assert res.profile_name == "cylindrical"

    # Case 2: Low confidence (0.35 < 0.45) -> fallback to default
    mock_detector.set_detection("bottle", confidence=0.35)
    res = selector.process(img)
    assert res.profile_name == "default"

    # Case 3: Empty scene (no detections) -> fallback to default
    mock_detector.clear()
    res = selector.process(img)
    assert res.profile_name == "default"
    assert res.class_name is None


def test_temporal_voting_n_of_m():
    # 5-of-7 voting
    voter = TemporalProfileVoter(window_m=7, min_votes_n=5, default_profile="default")

    # Step 1: Initial state is default
    assert voter.locked_profile == "default"

    # Step 2: Feed 4 frames of "cylindrical" (< 5 required votes)
    for _ in range(4):
        prof, locked = voter.update("cylindrical")
        assert prof == "default"  # Still locked to default
        assert not locked

    # Step 3: Feed 5th frame of "cylindrical" (reaches 5 votes!)
    prof, locked = voter.update("cylindrical")
    assert prof == "cylindrical"
    assert locked
    assert voter.locked_profile == "cylindrical"

    # Step 4: Single transient noise frame ("spherical") must NOT cause flicker
    prof, locked = voter.update("spherical")
    assert prof == "cylindrical"  # Retained locked profile

    # Step 5: Transitioning to "pinch" requires 5 frames of pinch
    for _ in range(4):
        prof, _ = voter.update("pinch")
        assert prof == "cylindrical"  # Still holds cylindrical

    # 5th frame of pinch reaches majority
    prof, locked = voter.update("pinch")
    assert prof == "pinch"
    assert locked

    # Step 6: Reset
    voter.reset()
    assert voter.locked_profile == "default"
    assert len(voter.history) == 0


def test_grip_selector_end_to_end_with_bounding_box():
    mock_detector = MockObjectDetector()
    selector = GripSelector(
        detector=mock_detector,
        confidence_threshold=0.50,
        voting_n=3,
        voting_m=5,
    )
    img = np.zeros((480, 640, 3), dtype=np.uint8)

    bbox = (0.25, 0.25, 0.75, 0.75)
    mock_detector.set_detection("apple", confidence=0.92, bounding_box=bbox)

    # First 2 frames
    selector.process(img)
    selector.process(img)

    # 3rd frame locks in spherical
    res = selector.process(img)
    assert res.profile_name == "spherical"
    assert res.is_locked
    assert res.class_name == "apple"
    assert res.confidence == 0.92
    assert res.bounding_box == bbox


def test_onnx_detector_missing_file_fallback():
    """Verify that if ONNX model weights are missing or unreadable, detector falls back to empty standby without crashing."""
    from vapa.vision.detector import ONNXObjectDetector

    detector = ONNXObjectDetector(model_path="non_existent_yolo_model.onnx")
    img = np.zeros((480, 640, 3), dtype=np.uint8)

    # Must safely return empty detections list
    detections = detector.detect(img)
    assert detections == []

    # Grip selector handles standby detector by falling back to default profile
    selector = GripSelector(detector=detector)
    res = selector.process(img)
    assert res.profile_name == "default"
    assert res.confidence == 0.0
    assert res.class_name is None

