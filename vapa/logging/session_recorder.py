"""Session telemetry and event logging recorder."""

import os
import csv
import time
import yaml
from pathlib import Path
from typing import Dict, Any, Optional

class SessionRecorder:
    """Records session telemetry to sensors.csv, events.log, and config_snapshot.yaml."""

    def __init__(self, base_dir: str = "logs", enabled: bool = True):
        self.enabled = enabled
        self.base_dir = Path(base_dir)
        self.session_dir: Optional[Path] = None
        self._csv_file = None
        self._csv_writer = None
        self._log_file = None

    def start_session(self, config_snapshot: Dict[str, Any]) -> Path:
        if not self.enabled:
            return Path(".")

        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        self.session_dir = self.base_dir / f"session_{timestamp_str}"
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Write config snapshot
        with open(self.session_dir / "config_snapshot.yaml", "w") as f:
            yaml.safe_dump(config_snapshot, f)

        # Initialize sensors.csv
        self._csv_file = open(self.session_dir / "sensors.csv", "w", newline="")
        self._csv_writer = csv.writer(self._csv_file)
        self._csv_writer.writerow([
            "timestamp", "t_ms",
            "emg_flex", "emg_ext",
            "fsr0", "fsr1", "fsr2", "fsr3", "fsr4",
            "safety_state", "arm_request", "flags"
        ])

        # Initialize events.log
        self._log_file = open(self.session_dir / "events.log", "w")
        self.log_event("SESSION_START", "Telemetry recording initialized")

        return self.session_dir

    def record_sensors(
        self,
        t_ms: int,
        emg: tuple,
        fsr: tuple,
        safety_state: str,
        arm_request: int,
        flags: int
    ) -> None:
        if not self.enabled or not self._csv_writer:
            return
        self._csv_writer.writerow([
            time.time(), t_ms,
            emg[0], emg[1],
            fsr[0], fsr[1], fsr[2], fsr[3], fsr[4],
            safety_state, arm_request, flags
        ])

    def log_event(self, event_type: str, message: str) -> None:
        if not self.enabled or not self._log_file:
            return
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        self._log_file.write(f"[{ts}] [{event_type}] {message}\n")
        self._log_file.flush()

    def close(self) -> None:
        if self._csv_file:
            self._csv_file.flush()
            self._csv_file.close()
            self._csv_file = None
        if self._log_file:
            self.log_event("SESSION_END", "Telemetry recording terminated cleanly")
            self._log_file.flush()
            self._log_file.close()
            self._log_file = None
