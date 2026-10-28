"""VAPA EMG Processing Package."""

from .envelope import (
    EMGCalibration,
    EnvelopeNormalizer,
    counts_to_mv,
    ADS1115_MV_PER_LSB,
)
from .decoder import (
    EMGIntent,
    DecoderConfig,
    ThresholdEMGDecoder,
)
from .classifier import (
    AbstractEMGClassifier,
    EnvelopeClassifier,
    EnvelopeFeatures,
)

__all__ = [
    "EMGCalibration",
    "EnvelopeNormalizer",
    "counts_to_mv",
    "ADS1115_MV_PER_LSB",
    "EMGIntent",
    "DecoderConfig",
    "ThresholdEMGDecoder",
    "AbstractEMGClassifier",
    "EnvelopeClassifier",
    "EnvelopeFeatures",
]
