"""Object detection and grip profile voting."""

from typing import Dict, List, Optional
from collections import deque, Counter

class MockObjectDetector:
    """Mock object detector returning configurable class and confidence."""

    def __init__(self, default_class: str = "bottle", confidence: float = 0.85):
        self.mock_class = default_class
        self.mock_confidence = confidence

    def detect(self, color_image) -> List[tuple[str, float]]:
        return [(self.mock_class, self.mock_confidence)]

class TemporalProfileVoter:
    """N-of-M majority voting filter for stability across detection frames."""

    def __init__(self, window_m: int = 7, min_votes_n: int = 5, default_profile: str = "default"):
        self.window_m = window_m
        self.min_votes_n = min_votes_n
        self.default_profile = default_profile
        self.history = deque(maxlen=window_m)

    def update(self, detected_profile: Optional[str]) -> str:
        if detected_profile:
            self.history.append(detected_profile)
        else:
            self.history.append(self.default_profile)

        counts = Counter(self.history)
        most_common, count = counts.most_common(1)[0]
        if count >= self.min_votes_n:
            return most_common
        return self.default_profile
