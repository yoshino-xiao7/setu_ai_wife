from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.presets import load_characters
from app.prompting import PromptTranslationError, translate_prompt


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MODEL_SUFFIXES = {".safetensors", ".ckpt", ".pt"}
USER_AGENT = "Xueliang-AI-Worker/0.1"


def _capability_item(file: Path, root: Path) -> dict[str, Any]:
    try:
        name = str(file.relative_to(root)).replace("\\", "/")
    except ValueError:
        name = file.name
    return {
        "name": name,
        "displayName": file.stem,
        "sizeBytes": file.stat().st_size,
        "metadataJson": "",
    }


def _list_model_files(root: Path, subdir: str) -> list[dict[str, Any]]:
    directory = root / subdir
    if not directory.exists():
        return []
    items: list[dict[str, Any]] = []
    for file in sorted(directory.rglob("*"), key=lambda item: str(item).lower()):
        if file.is_file() and file.suffix.lower() in MODEL_SUFFIXES:
            items.append(_capability_item(file, directory))
    return items


def scan_capabilities(settings: Settings) -> dict[str, Any]:
    characters = []
    for character in load_characters(settings.characters_path):
        characters.append(
            {
                "name": character.id,
                "displayName": character.name,
                "metadataJson": json.dumps(character.model_dump(), ensure_ascii=False),
            }
        )

    return {
        "workerId": settings.ai_worker_id,
        "nodeName": settings.ai_worker_name,
        "version": settings.ai_worker_version,
        "checkpoints": _list_model_files(settings.comfyui_models_dir, "checkpoints"),
        "loras": _list_model_files(settings.comfyui_models_dir, "loras"),
        "vaes": _list_model_files(settings.comfyui_models_dir, "vae"),
        "characters": characters,
    }


class CloudWorker:
    def __init__(self, settings: Settings):
        if not settings.cloud_api_url:
            raise RuntimeError("CLOUD_API_URL is required for cloud worker mode.")
        if not settings.ai_worker_token:
            raise RuntimeError("AI_WORKER_TOKEN is required for cloud worker mode.")
        self.settings = settings
        self.cloud_url = settings.cloud_api_url.rstrip("/")
        self.local_url = settings.local_ai_url.rstrip("/")
        self.headers = {
            "X-AI-Worker-Token": settings.ai_worker_token,
            "User-Agent": USER_AGENT,
        }
        self._last_capability_report = 0.0

    async def run_forever(self) -> None:
        async with httpx.AsyncClient(timeout=60, headers=self.headers) as client:
            while True:
                try:
                    await self._report_periodic(client)
                    claimed_prompt = await self._claim_prompt_translation(client)
                    if claimed_prompt.get("hasJob"):
                        await self._process_prompt_translation(client, claimed_prompt["job"])
                        continue
                    claimed = await self._claim(client)
                    if not claimed.get("hasJob"):
                        await asyncio.sleep(self.settings.ai_worker_poll_seconds)
                        continue
                    await self._process_job(client, claimed["job"])
                except Exception as exc:
                    print(f"[cloud-worker] loop error: {exc}")
                    await asyncio.sleep(self.settings.ai_worker_poll_seconds)

    async def _report_periodic(self, client: httpx.AsyncClient) -> None:
        now = asyncio.get_running_loop().time()
        if now - self._last_capability_report < self.settings.ai_worker_capability_report_seconds:
            return
        await self._heartbeat(client)
        await self._report_capabilities(client)
        self._last_capability_report = now

    async def _heartbeat(self, client: httpx.AsyncClient) -> None:
        payload = {
            "workerId": self.settings.ai_worker_id,
            "nodeName": self.settings.ai_worker_name,
            "version": self.settings.ai_worker_version,
            "status": "ONLINE",
        }
        response = await client.post(f"{self.cloud_url}/ai-worker/heartbeat", json=payload)
        response.raise_for_status()

    async def _report_capabilities(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            f"{self.cloud_url}/ai-worker/capabilities",
            json=scan_capabilities(self.settings),
        )
        response.raise_for_status()

    async def _claim(self, client: httpx.AsyncClient) -> dict[str, Any]:
        response = await client.post(
            f"{self.cloud_url}/ai-worker/jobs/claim",
            json={"workerId": self.settings.ai_worker_id},
        )
        response.raise_for_status()
        return response.json()

    async def _claim_prompt_translation(self, client: httpx.AsyncClient) -> dict[str, Any]:
        response = await client.post(
            f"{self.cloud_url}/ai-worker/prompt-translations/claim",
            json={"workerId": self.settings.ai_worker_id},
        )
        response.raise_for_status()
        return response.json()

    async def _process_prompt_translation(self, client: httpx.AsyncClient, job: dict[str, Any]) -> None:
        job_id = job["id"]
        try:
            result = await translate_prompt(
                job.get("promptCn") or "",
                self.settings,
                style_tags=job.get("styleTags") or "",
                negative_prompt=job.get("negativePrompt") or "",
            )
            response = await client.post(
                f"{self.cloud_url}/ai-worker/prompt-translations/{job_id}/complete",
                json={
                    "workerId": self.settings.ai_worker_id,
                    "positive": result.positive,
                    "negative": result.negative,
                    "styleNotes": result.style_notes,
                },
            )
            response.raise_for_status()
        except PromptTranslationError as exc:
            await self._fail_prompt_translation(client, job_id, str(exc))
        except Exception as exc:
            await self._fail_prompt_translation(client, job_id, f"Prompt translation worker failed: {exc}")

    async def _process_job(self, client: httpx.AsyncClient, job: dict[str, Any]) -> None:
        job_id = job["id"]
        try:
            local_job = await self._start_local_generation(job)
            await client.post(
                f"{self.cloud_url}/ai-worker/jobs/{job_id}/running",
                json={
                    "workerId": self.settings.ai_worker_id,
                    "localJobId": local_job["job_id"],
                },
            )
            local_result = await self._wait_local_job(local_job["job_id"])
            image_bytes, filename = await self._download_local_image(local_result)
            await self._complete_cloud_job(client, job_id, local_result, image_bytes, filename)
            self._cleanup_local_image(filename)
        except Exception as exc:
            await self._fail_cloud_job(client, job_id, str(exc))

    async def _start_local_generation(self, job: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "prompt_cn": job.get("promptCn") or "",
            "prompt_positive": job.get("promptPositive") or "",
            "prompt_negative": job.get("promptNegative") or "",
            "style_notes": job.get("styleNotes") or "",
            "character_id": job.get("characterId") or None,
            "width": job.get("width") or 832,
            "height": job.get("height") or 1216,
            "steps": job.get("steps") or None,
            "cfg": job.get("cfg") or None,
            "seed": job.get("seed") or None,
            "checkpoint": job.get("checkpoint") or None,
            "lora_name": job.get("loraName") or "",
            "lora_strength": job.get("loraStrength") or 0,
        }
        async with httpx.AsyncClient(timeout=30, headers={"User-Agent": USER_AGENT}) as local:
            response = await local.post(f"{self.local_url}/api/generate", json=payload)
            response.raise_for_status()
            return response.json()

    async def _wait_local_job(self, local_job_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30, headers={"User-Agent": USER_AGENT}) as local:
            while True:
                response = await local.get(f"{self.local_url}/api/jobs/{local_job_id}")
                response.raise_for_status()
                job = response.json()
                status = job.get("status")
                if status == "completed":
                    return job
                if status == "failed":
                    raise RuntimeError(job.get("error") or "Local generation failed")
                await asyncio.sleep(2)

    async def _download_local_image(self, local_job: dict[str, Any]) -> tuple[bytes, str]:
        filename = local_job.get("image_path")
        if not filename:
            raise RuntimeError("Local generation completed without image_path.")
        async with httpx.AsyncClient(timeout=60, headers={"User-Agent": USER_AGENT}) as local:
            response = await local.get(f"{self.local_url}/api/images/{filename}")
            response.raise_for_status()
            return response.content, filename

    async def _complete_cloud_job(
        self,
        client: httpx.AsyncClient,
        job_id: int,
        local_result: dict[str, Any],
        image_bytes: bytes,
        filename: str,
    ) -> None:
        payload = {
            "workerId": self.settings.ai_worker_id,
            "imageBase64": base64.b64encode(image_bytes).decode("ascii"),
            "contentType": "image/png",
            "filename": filename,
            "promptPositive": local_result.get("prompt_positive"),
            "promptNegative": local_result.get("prompt_negative"),
            "styleNotes": local_result.get("style_notes"),
            "seed": local_result.get("seed"),
        }
        response = await client.post(f"{self.cloud_url}/ai-worker/jobs/{job_id}/complete", json=payload, timeout=120)
        response.raise_for_status()

    async def _fail_cloud_job(self, client: httpx.AsyncClient, job_id: int, error: str) -> None:
        response = await client.post(
            f"{self.cloud_url}/ai-worker/jobs/{job_id}/fail",
            json={"workerId": self.settings.ai_worker_id, "errorMessage": error[:1000]},
        )
        response.raise_for_status()

    async def _fail_prompt_translation(self, client: httpx.AsyncClient, job_id: int, error: str) -> None:
        response = await client.post(
            f"{self.cloud_url}/ai-worker/prompt-translations/{job_id}/fail",
            json={"workerId": self.settings.ai_worker_id, "errorMessage": error[:1000]},
        )
        response.raise_for_status()

    def _cleanup_local_image(self, filename: str) -> None:
        if not self.settings.ai_worker_cleanup_outputs:
            return
        safe_name = Path(filename).name
        path = self.settings.output_dir / safe_name
        if path.exists() and path.suffix.lower() in IMAGE_SUFFIXES:
            try:
                path.unlink()
                print(f"[cloud-worker] cleaned local image: {safe_name}")
            except OSError as exc:
                print(f"[cloud-worker] cleanup skipped for {safe_name}: {exc}")


async def main() -> None:
    worker = CloudWorker(get_settings())
    await worker.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
