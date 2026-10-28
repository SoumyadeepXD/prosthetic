"""Arming precondition validator for VAPA."""

from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Any
from ..hal import HALContainer
from ..protocol import SensorMessage

@dataclass
class PreconditionReport:
    passed: bool
    failed_reasons: List[str]

class PreconditionValidator:
    """Evaluates all system readiness criteria before permitting arming transition."""

    def __init__(
        self,
        max_sensor_age_ms: float = 250.0,
        fsr_rest_max_adc: int = 250,
        emg_rest_min_mv: float = 50.0,
        emg_rest_max_mv: float = 800.0,
        emg_saturation_mv: float = 3000.0,
    ):
        self.max_sensor_age_ms = max_sensor_age_ms
        self.fsr_rest_max_adc = fsr_rest_max_adc
        self.emg_rest_min_mv = emg_rest_min_mv
        self.emg_rest_max_mv = emg_rest_max_mv
        self.emg_saturation_mv = emg_saturation_mv

    def evaluate(
        self,
        hal: HALContainer,
        servo_config: Dict[str, Any],
        emg_calibrated: bool = True,
    ) -> PreconditionReport:
        failed: List[str] = []

        # 1. ESP32 Link Health & Freshness
        link_stats = hal.esp_link.get_link_stats()
        frame_age = link_stats.get("frame_age_ms", 99999.0)
        if not hal.esp_link.is_healthy() or frame_age > self.max_sensor_age_ms:
            failed.append(f"ESP32 link offline or stale (frame age {frame_age:.1f} ms > {self.max_sensor_age_ms} ms)")

        # 2. Latest Sensor Packet Integrity
        sensor = hal.esp_link.get_latest_sensor()
        if not sensor:
            failed.append("No sensor telemetry received from ESP32")
        else:
            if sensor.estop_pressed:
                failed.append("Physical Emergency Stop is pressed")
            if sensor.latched_fault:
                failed.append("ESP32 supervisor reports a latched fault")
            if sensor.force_fault:
                failed.append("ESP32 supervisor reports an active force fault")
            if sensor.ads_fault:
                failed.append("ESP32 supervisor reports an ADS1115 fault")

            # 3. FSR Plausibility (near zero with no touch)
            for i, count in enumerate(sensor.fsr):
                if count > self.fsr_rest_max_adc:
                    failed.append(f"FSR[{i}] reading ({count}) not plausible for unweighted rest (> {self.fsr_rest_max_adc})")

            # 4. EMG Baseline Plausibility
            if not emg_calibrated:
                failed.append("EMG baseline calibration not performed")
            else:
                for idx, val in enumerate(sensor.emg):
                    if val < self.emg_rest_min_mv:
                        failed.append(f"EMG[{idx}] reading ({val:.1f} mV) below minimum floor ({self.emg_rest_min_mv} mV)")
                    elif val > self.emg_rest_max_mv:
                        failed.append(f"EMG[{idx}] reading ({val:.1f} mV) exceeds rest threshold ({self.emg_rest_max_mv} mV)")
                    elif val >= self.emg_saturation_mv:
                        failed.append(f"EMG[{idx}] signal railed/saturated ({val:.1f} mV)")

        # 5. PCA9685 Health
        if not hal.pca9685.is_healthy():
            failed.append("PCA9685 PWM driver is not healthy or responding")

        # 6. AS5600 Encoders Health (MD=1, ML=0, MH=0)
        if not hal.as5600.verify_all_magnets():
            failed.append("One or more AS5600 magnetic encoders report missing/degraded magnet")

        # 7. Servo Calibration Presence
        servos = servo_config.get("servos", {})
        if not servos:
            failed.append("Servo configuration missing")

        return PreconditionReport(passed=(len(failed) == 0), failed_reasons=failed)
