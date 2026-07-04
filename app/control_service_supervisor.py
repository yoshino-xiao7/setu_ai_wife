from __future__ import annotations

import contextlib
import datetime as dt
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TextIO
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
PID_FILE = LOG_DIR / "control-service.pid"
SUPERVISOR_LOG = LOG_DIR / "control-service-supervisor.log"
HEALTH_URL = "http://127.0.0.1:7878/health"
CHECK_SECONDS = 10
RESTART_DELAY_SECONDS = 5
STARTUP_GRACE_SECONDS = 15


class ControlServiceSupervisor:
    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None

    def run(self, stop_event: threading.Event) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with SUPERVISOR_LOG.open("a", encoding="utf-8", buffering=1) as log:
            self._log(log, "supervisor started")
            while not stop_event.is_set():
                try:
                    if self.process is None or self.process.poll() is not None:
                        self._start_child(log)
                        self._wait(stop_event, STARTUP_GRACE_SECONDS)
                        continue

                    if not self._healthy():
                        self._log(log, "health check failed; restarting control service")
                        self._stop_child(log)
                        self._wait(stop_event, RESTART_DELAY_SECONDS)
                        continue

                    self._wait(stop_event, CHECK_SECONDS)
                except Exception as exc:
                    self._log(log, f"supervisor loop error: {exc}")
                    self._wait(stop_event, RESTART_DELAY_SECONDS)

            self._stop_child(log)
            self._log(log, "supervisor stopped")

    def _start_child(self, log: TextIO) -> None:
        timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        stdout_path = LOG_DIR / f"control-service-{timestamp}.out.log"
        stderr_path = LOG_DIR / f"control-service-{timestamp}.err.log"
        stdout = stdout_path.open("a", encoding="utf-8")
        stderr = stderr_path.open("a", encoding="utf-8")
        self.process = subprocess.Popen(
            [sys.executable, "-m", "app.control_service"],
            cwd=ROOT,
            stdout=stdout,
            stderr=stderr,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        PID_FILE.write_text(str(self.process.pid), encoding="ascii")
        self._log(log, f"started control service pid={self.process.pid}")

    def _stop_child(self, log: TextIO) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self._log(log, f"stopping control service pid={self.process.pid}")
            self.process.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                self.process.wait(timeout=20)
        if self.process.poll() is None:
            self._log(log, f"killing control service pid={self.process.pid}")
            self.process.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                self.process.wait(timeout=10)
        self.process = None
        with contextlib.suppress(OSError):
            PID_FILE.unlink()

    def _healthy(self) -> bool:
        try:
            with urlopen(HEALTH_URL, timeout=3) as response:
                return 200 <= response.status < 500
        except Exception:
            return False

    def _wait(self, stop_event: threading.Event, seconds: float) -> None:
        stop_event.wait(seconds)

    def _log(self, log: TextIO, message: str) -> None:
        now = dt.datetime.now().isoformat(timespec="seconds")
        log.write(f"[{now}] {message}\n")


def main() -> None:
    stop_event = threading.Event()
    try:
        ControlServiceSupervisor().run(stop_event)
    except KeyboardInterrupt:
        stop_event.set()


if __name__ == "__main__":
    main()
