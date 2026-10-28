"""EEG experimental interface (disabled by default).

NOTE: A single dry EEG channel is not reliable for motion control.
When enabled, EEG signals may ONLY trigger low-confidence mode cycles
and are strictly prohibited from commanding or increasing closing motion.
"""

from abc import ABC, abstractmethod
from typing import Optional

class AbstractEEGDecoder(ABC):
    """Abstract interface for optional EEG auxiliary trigger."""

    @abstractmethod
    def process_sample(self, raw_eeg: int) -> Optional[str]:
        """Process raw EEG sample. Returns event name or None."""
        pass

class MockEEGDecoder(AbstractEEGDecoder):
    """Disabled mock EEG decoder."""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def process_sample(self, raw_eeg: int) -> Optional[str]:
        if not self.enabled:
            return None
        # Never commands closing
        return None
