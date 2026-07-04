from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException

from app.config import Settings, get_settings


app = FastAPI(title="Xueliang AI Control Service")


def _root_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _script_path(name: str) -> Path:
    return _root_dir() / "scripts" / name


def _require_token(settings: Settings, authorization: str | None, x_ai_control_token: str | None) -> None:
    if not settings.control_token:
        raise HTTPException(status_code=503, detail="AI_CONTROL_TOKEN is not configured.")
    bearer = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
    token = bearer or (x_ai_control_token or "").strip()
    if token != settings.control_token:
        raise HTTPException(status_code=401, detail="Invalid AI control token.")


def _powershell_command(script: Path, *args: str) -> list[str]:
    return [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        *args,
    ]


def _start_hidden(command: list[str]) -> int:
    creationflags = 0
    startupinfo = None
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags = subprocess.CREATE_NO_WINDOW
    if hasattr(subprocess, "STARTUPINFO"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    process = subprocess.Popen(
        command,
        cwd=_root_dir(),
        creationflags=creationflags,
        startupinfo=startupinfo,
    )
    return process.pid


async def _run_capture(command: list[str]) -> subprocess.CompletedProcess[str]:
    return await asyncio.to_thread(
        subprocess.run,
        command,
        cwd=_root_dir(),
        text=True,
        capture_output=True,
        timeout=30,
    )


async def _local_http_ready(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(url)
        return response.status_code < 500
    except Exception:
        return False


async def _stack_status(settings: Settings) -> dict[str, Any]:
    control_ready = True
    comfy_ready, local_ready = await asyncio.gather(
        _local_http_ready(settings.comfyui_url),
        _local_http_ready(settings.local_ai_url),
    )
    worker_probe = await _run_capture(_powershell_command(_script_path("probe_cloud_stack.ps1")))
    worker_running = worker_probe.returncode == 0 and "worker=true" in worker_probe.stdout
    return {
        "controlReady": control_ready,
        "comfyReady": comfy_ready,
        "localServiceReady": local_ready,
        "workerRunning": worker_running,
        "running": comfy_ready and local_ready and worker_running,
        "comfyUrl": settings.comfyui_url,
        "localAiUrl": settings.local_ai_url,
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True}


@app.get("/status")
async def status(
    authorization: str | None = Header(default=None),
    x_ai_control_token: str | None = Header(default=None),
) -> dict[str, Any]:
    settings = get_settings()
    _require_token(settings, authorization, x_ai_control_token)
    return await _stack_status(settings)


@app.post("/start")
async def start(
    authorization: str | None = Header(default=None),
    x_ai_control_token: str | None = Header(default=None),
) -> dict[str, Any]:
    settings = get_settings()
    _require_token(settings, authorization, x_ai_control_token)
    pid = _start_hidden(_powershell_command(_script_path("start_cloud_all.ps1"), "-SkipCloudConfigCheck"))
    return {"accepted": True, "action": "start", "pid": pid}


@app.post("/restart")
async def restart(
    authorization: str | None = Header(default=None),
    x_ai_control_token: str | None = Header(default=None),
) -> dict[str, Any]:
    settings = get_settings()
    _require_token(settings, authorization, x_ai_control_token)
    pid = _start_hidden(_powershell_command(_script_path("start_cloud_all.ps1"), "-SkipCloudConfigCheck", "-Restart"))
    return {"accepted": True, "action": "restart", "pid": pid}


@app.post("/stop")
async def stop(
    authorization: str | None = Header(default=None),
    x_ai_control_token: str | None = Header(default=None),
) -> dict[str, Any]:
    settings = get_settings()
    _require_token(settings, authorization, x_ai_control_token)
    result = await _run_capture(_powershell_command(_script_path("stop_cloud_all.ps1")))
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=(result.stderr or result.stdout or "Stop command failed.").strip())
    return {"accepted": True, "action": "stop", "message": result.stdout.strip()}


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.control_host, port=settings.control_port)


if __name__ == "__main__":
    main()
