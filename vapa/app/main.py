"""Main orchestrator and CLI application for VAPA."""

import os
import sys
import time
import signal
import atexit
import argparse
import logging
from pathlib import Path
import yaml

from ..safety import SafetyStateMachine, SafetyState, HeartbeatThread
from ..hal import MockPCA9685, MockTCA9548A, MockAS5600, MockESPLink, MockRealSense
from ..control import ServoMapper, SlewRateLimiter, FingerForceController, GripExecutor
from ..emg import ThresholdEMGDecoder, EnvelopeNormalizer, EMGCalibration
from ..fusion import SharedControlArbitrator
from ..logging import SessionRecorder
from ..ui import StatusScreen

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("vapa.app")

class VAPAApplication:
    """Master orchestrator integrating Safety, HAL, Control, EMG, and Vision."""

    def __init__(self, mock_mode: bool = True, config_dir: str = "config", record: bool = False):
        self.mock_mode = mock_mode
        self.config_dir = Path(config_dir)
        self.record_enabled = record

        # Load configs
        self.hw_config = self._load_yaml("hardware.yaml")
        self.servo_config = self._load_yaml("servos.yaml")
        self.fsr_config = self._load_yaml("fsr.yaml")
        self.emg_config = self._load_yaml("emg.yaml")
        self.grip_config = self._load_yaml("grip_profiles.yaml")
        self.vision_config = self._load_yaml("vision.yaml")

        # Core safety state machine
        self.safety = SafetyStateMachine()

        # HAL Devices
        if self.mock_mode:
            self.pca9685 = MockPCA9685()
            self.tca9548a = MockTCA9548A()
            self.as5600 = MockAS5600()
            self.esp_link = MockESPLink()
            self.realsense = MockRealSense()
        else:
            raise NotImplementedError("Real hardware initialization must be run on physical Jetson")

        # Control & Pipeline
        self.mapper = ServoMapper(self.servo_config)
        self.slew_limiter = SlewRateLimiter({"default": 180.0})
        self.force_controller = FingerForceController()
        self.grip_executor = GripExecutor(self.mapper, self.slew_limiter, self.force_controller)
        self.emg_decoder = ThresholdEMGDecoder()
        self.arbitrator = SharedControlArbitrator(self.grip_config)
        self.recorder = SessionRecorder(enabled=self.record_enabled)
        self.ui = StatusScreen(headless=True)

        # Heartbeat watchdog thread (50 Hz)
        self.heartbeat = HeartbeatThread(
            send_fn=self.esp_link.send_message,
            get_arm_request_fn=lambda: self.safety.arm_request,
            get_state_fn=lambda: self.safety.state.value,
        )

        self._running = False
        self._register_safety_handlers()

    def _load_yaml(self, filename: str) -> dict:
        filepath = self.config_dir / filename
        if filepath.exists():
            with open(filepath, "r") as f:
                return yaml.safe_load(f) or {}
        return {}

    def _register_safety_handlers(self) -> None:
        """Ensure system fails closed upon SIGINT, SIGTERM, or abnormal exit."""
        def emergency_stop(signum, frame):
            logger.warning(f"Signal {signum} received! Disarming immediately...")
            self.shutdown()
            sys.exit(0)

        signal.signal(signal.SIGINT, emergency_stop)
        signal.signal(signal.SIGTERM, emergency_stop)
        atexit.register(self.shutdown)

    def initialize(self) -> bool:
        logger.info("Initializing VAPA subsystems...")
        ok = (
            self.pca9685.initialize()
            and self.tca9548a.initialize()
            and self.as5600.initialize()
            and self.esp_link.initialize()
            and self.realsense.initialize()
        )
        if not ok:
            logger.error("Failed to initialize one or more HAL devices")
            return False

        if self.record_enabled:
            snapshot = {
                "hardware": self.hw_config,
                "servos": self.servo_config,
                "fsr": self.fsr_config,
                "emg": self.emg_config,
            }
            self.recorder.start_session(snapshot)

        self.heartbeat.start()
        logger.info(f"VAPA initialized in state: {self.safety.state.name}")
        return True

    def run_step(self, dt_s: float = 0.01) -> None:
        """Single 100 Hz control loop step."""
        # 1. Feed heartbeat watchdog
        self.heartbeat.feed()

        # 2. Acquire sensor telemetry from ESP32 link
        sensor_msg = self.esp_link.get_latest_sensor()
        if not sensor_msg:
            return

        # 3. Check safety conditions & faults
        if sensor_msg.estop_pressed:
            self.safety.trigger_fault("Emergency Stop pressed")
        elif sensor_msg.force_fault:
            self.safety.trigger_fault("Hardware force ceiling fault reported by supervisor")
        elif sensor_msg.ads_fault:
            self.safety.trigger_fault("ADS1115 sensor failure reported by supervisor")

        # 4. Enforce PWM gate: No PWM if disarmed or faulted
        if not self.safety.is_pwm_allowed:
            self.pca9685.disable_all()

        # 5. Log telemetry
        if self.record_enabled:
            self.recorder.record_sensors(
                t_ms=sensor_msg.t_ms,
                emg=sensor_msg.emg,
                fsr=sensor_msg.fsr,
                safety_state=self.safety.state.name,
                arm_request=self.safety.arm_request,
                flags=sensor_msg.flags,
            )

    def shutdown(self) -> None:
        if not self._running and self.safety.state == SafetyState.DISARMED:
            return
        logger.info("Executing safe shutdown...")
        self.safety.disarm("System shutdown")
        self.heartbeat.stop()
        if hasattr(self, "pca9685"):
            self.pca9685.disable_all()
            self.pca9685.close()
        if hasattr(self, "esp_link"):
            self.esp_link.close()
        if hasattr(self, "recorder"):
            self.recorder.close()
        logger.info("Safe shutdown complete.")

def main():
    parser = argparse.ArgumentParser(description="VAPA Prosthetic Arm Orchestrator")
    parser.add_argument("--mock", action="store_true", default=True, help="Run with mock hardware backends")
    parser.add_argument("--config", type=str, default="config", help="Configuration directory")
    parser.add_argument("--record", action="store_true", help="Record session telemetry to logs/")
    args = parser.parse_args()

    app = VAPAApplication(mock_mode=args.mock, config_dir=args.config, record=args.record)
    if not app.initialize():
        sys.exit(1)

    logger.info("Starting 100 Hz main loop (Press Ctrl+C to terminate)...")
    app._running = True
    try:
        dt = 0.01  # 100 Hz
        while app._running:
            t0 = time.perf_counter()
            app.run_step(dt)
            elapsed = time.perf_counter() - t0
            sleep_time = max(0.0, dt - elapsed)
            time.sleep(sleep_time)
    except KeyboardInterrupt:
        pass
    finally:
        app.shutdown()

if __name__ == "__main__":
    main()
