"""VAPA EMG Processing Package."""

from .envelope import EMGCalibration, EnvelopeNormalizer
from .decoder import EMGIntent, DecoderConfig, ThresholdEMGDecoder

__all__ = [
    "EMGCalibration",
    "EnvelopeNormalizer",
    "EMGIntent",
    "DecoderConfig",
    "ThresholdEMGDecoder",
]
