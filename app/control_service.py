from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException

from app.config import Settings, get_settings


app = FastAPI(title="Xueliang AI Control Service")
USER_AGENT = "Xueliang-AI-Control/0.1"


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


async def _execute_action(action: str, settings: Settings) -> dict[str, Any]:
    normalized = action.upper()
    if normalized == "START":
        pid = _start_hidden(_powershell_command(_script_path("start_cloud_all.ps1"), "-SkipCloudConfigCheck"))
        status = await _stack_status(settings)
        status.update({"accepted": True, "action": "START", "pid": pid, "message": "AI 绘图启动命令已执行。"})
        return status
    if normalized == "RESTART":
        pid = _start_hidden(_powershell_command(_script_path("start_cloud_all.ps1"), "-SkipCloudConfigCheck", "-Restart"))
        status = await _stack_status(settings)
        status.update({"accepted": True, "action": "RESTART", "pid": pid, "message": "AI 绘图重启命令已执行。"})
        return status
    if normalized == "STOP":
        result = await _run_capture(_powershell_command(_script_path("stop_cloud_all.ps1")))
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "AI 绘图停止命令执行失败。").strip())
        status = await _stack_status(settings)
        status.update({
            "accepted": True,
            "action": "STOP",
            "message": result.stdout.strip() or "AI 绘图停止命令已执行。",
        })
        return status
    raise RuntimeError(f"Unsupported AI control action: {action}")


def _cloud_headers(settings: Settings) -> dict[str, str]:
    return {
        "X-AI-Worker-Token": settings.ai_worker_token,
        "User-Agent": USER_AGENT,
    }


async def _claim_cloud_command(client: httpx.AsyncClient, settings: Settings) -> dict[str, Any]:
    response = await client.post(
        f"{settings.cloud_api_url.rstrip('/')}/ai-worker/control-commands/claim",
        json={"workerId": settings.ai_worker_id},
    )
    response.raise_for_status()
    return response.json()


async def _complete_cloud_command(
    client: httpx.AsyncClient,
    settings: Settings,
    command_id: int,
    result: dict[str, Any],
) -> None:
    response = await client.post(
        f"{settings.cloud_api_url.rstrip('/')}/ai-worker/control-commands/{command_id}/complete",
        json={"workerId": settings.ai_worker_id, "result": result},
    )
    response.raise_for_status()


async def _fail_cloud_command(
    client: httpx.AsyncClient,
    settings: Settings,
    command_id: int,
    error: str,
) -> None:
    response = await client.post(
        f"{settings.cloud_api_url.rstrip('/')}/ai-worker/control-commands/{command_id}/fail",
        json={"workerId": settings.ai_worker_id, "errorMessage": error[:1000]},
    )
    response.raise_for_status()


async def _poll_cloud_commands() -> None:
    settings = get_settings()
    if not settings.cloud_api_url or not settings.ai_worker_token:
        print("[ai-control] CLOUD_API_URL or AI_WORKER_TOKEN is empty; cloud control polling disabled.")
        return
    async with httpx.AsyncClient(timeout=60, headers=_cloud_headers(settings)) as client:
        while True:
            command_id = None
            try:
                claimed = await _claim_cloud_command(client, settings)
                if not claimed.get("hasCommand"):
                    await asyncio.sleep(settings.control_poll_seconds)
                    continue
                command = claimed["command"]
                command_id = command["id"]
                action = command["action"]
                result = await _execute_action(action, settings)
                await _complete_cloud_command(client, settings, command_id, result)
            except Exception as exc:
                try:
                    if command_id is not None:
                        await _fail_cloud_command(client, settings, command_id, str(exc))
                except Exception as report_exc:
                    print(f"[ai-control] failed to report command failure: {report_exc}")
                print(f"[ai-control] cloud control loop error: {exc}")
                await asyncio.sleep(settings.control_poll_seconds)


@app.on_event("startup")
async def start_cloud_control_polling() -> None:
    asyncio.create_task(_poll_cloud_commands())


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
    return await _execute_action("START", settings)


@app.post("/restart")
async def restart(
    authorization: str | None = Header(default=None),
    x_ai_control_token: str | None = Header(default=None),
) -> dict[str, Any]:
    settings = get_settings()
    _require_token(settings, authorization, x_ai_control_token)
    return await _execute_action("RESTART", settings)


@app.post("/stop")
async def stop(
    authorization: str | None = Header(default=None),
    x_ai_control_token: str | None = Header(default=None),
) -> dict[str, Any]:
    settings = get_settings()
    _require_token(settings, authorization, x_ai_control_token)
    try:
        return await _execute_action("STOP", settings)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.control_host, port=settings.control_port)


if __name__ == "__main__":
    main()
