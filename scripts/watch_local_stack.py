"""Keep the local FastAPI service and cloud worker running without a console window."""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
PYTHONW = ROOT / ".venv" / "Scripts" / "pythonw.exe"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000


def _creation_flags() -> int:
    return CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _pid_alive(pid: int) -> bool:
    completed = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        creationflags=CREATE_NO_WINDOW,
    )
    return str(pid) in (completed.stdout or "")


def _iter_python_commands() -> list[str]:
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python(w)?\\.exe' } | ForEach-Object { $_.CommandLine }",
        ],
        capture_output=True,
        text=True,
        creationflags=CREATE_NO_WINDOW,
    )
    return [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]


def _command_running(needle: str) -> bool:
    self_pid = str(os.getpid())
    for command in _iter_python_commands():
        if needle in command and "watch_local_stack.py" not in command:
            return True
    pid_path = LOG_DIR / "cloud-worker.pid" if "cloud_worker" in needle else LOG_DIR / "local-service.pid"
    try:
        pid_text = pid_path.read_text(encoding="ascii").strip()
        if pid_text.isdigit() and pid_text != self_pid and _pid_alive(int(pid_text)):
            # Pid files can point at a dead wrapper; only trust them with a matching command.
            return False
    except OSError:
        pass
    return False


def _spawn(name: str, args: list[str]) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    stdout = LOG_DIR / f"{name}-{stamp}.out.log"
    stderr = LOG_DIR / f"{name}-{stamp}.err.log"
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    with stdout.open("ab") as out, stderr.open("ab") as err:
        process = subprocess.Popen(
            args,
            cwd=str(ROOT),
            stdout=out,
            stderr=err,
            startupinfo=startupinfo,
            creationflags=_creation_flags(),
            close_fds=True,
        )
    (LOG_DIR / f"{name}.pid").write_text(str(process.pid), encoding="ascii")
    print(f"[watch-local-stack] started {name} pid={process.pid}", flush=True)
    return process.pid


def ensure_stack() -> None:
    python = str(PYTHONW if PYTHONW.exists() else PYTHON)
    if not _port_open(7861):
        _spawn("local-service", [python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "7861"])
    if not _command_running("-m app.cloud_worker"):
        _spawn("cloud-worker", [python, "-m", "app.cloud_worker"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int, default=20)
    args = parser.parse_args()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    watch_log = LOG_DIR / "watch-local-stack.out.log"
    log_handle = watch_log.open("a", encoding="utf-8")
    sys.stdout = log_handle
    sys.stderr = log_handle
    print(f"[watch-local-stack] started at {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    ensure_stack()
    if not args.watch:
        return 0
    print("[watch-local-stack] watching local AI stack", flush=True)
    (LOG_DIR / "watch-local-stack.pid").write_text(str(os.getpid()), encoding="ascii")
    while True:
        time.sleep(max(5, args.interval))
        try:
            ensure_stack()
        except Exception as exc:
            print(f"[watch-local-stack] ensure failed: {exc}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
