from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings, get_settings
from app.presets import list_checkpoints, list_loras, load_characters, load_prompt_presets
from app.prompting import PromptTranslationError, translate_prompt


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MODEL_SUFFIXES = {".safetensors", ".ckpt", ".pt"}
USER_AGENT = "Xueliang-AI-Worker/0.1"
COMPLETE_MAX_ATTEMPTS = 5
COMPLETE_RETRY_BASE_SECONDS = 1.0


class LocalGenerationError(RuntimeError):
    def __init__(self, message: str, local_job: dict[str, Any] | None = None):
        super().__init__(message)
        self.local_job = local_job or {}

    @property
    def comfy_prompt_id(self) -> str:
        return str(self.local_job.get("comfy_prompt_id") or "")


class CloudCompletionDeliveryError(RuntimeError):
    """The generated image could not be delivered after retryable cloud errors."""


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
    prompt_presets = []
    for preset in load_prompt_presets(settings.prompt_presets_path):
        prompt_presets.append(
            {
                "name": preset.id,
                "displayName": preset.name,
                "metadataJson": json.dumps(preset.model_dump(), ensure_ascii=False),
            }
        )

    return {
        "workerId": settings.ai_worker_id,
        "nodeName": settings.ai_worker_name,
        "version": settings.ai_worker_version,
        "checkpoints": list_checkpoints(settings),
        "loras": list_loras(settings),
        "vaes": _list_model_files(settings.comfyui_models_dir, "vae"),
        "characters": characters,
        "promptPresets": prompt_presets,
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
        self._local_images_reconciled = False

    async def run_forever(self) -> None:
        async with httpx.AsyncClient(timeout=60, headers=self.headers) as client:
            await self._send_qq_startup_notice()
            while True:
                try:
                    await self._report_periodic(client)
                    delete_command = await self._claim_local_image_delete(client)
                    if delete_command.get("hasCommand"):
                        await self._process_local_image_delete(client, delete_command["command"])
                        continue
                    claimed_prompt = await self._claim_prompt_translation(client)
                    if claimed_prompt.get("hasJob"):
                        await self._process_prompt_translation(client, claimed_prompt["job"])
                        continue
                    claimed = await self._claim(client)
                    if not claimed.get("hasJob"):
                        await asyncio.sleep(self.settings.ai_worker_poll_seconds)
                        continue
                    await self._process_job(client, claimed["job"], claimed.get("inpaintSourceUrl") or "")
                except Exception as exc:
                    print(f"[cloud-worker] loop error: {exc}")
                    await asyncio.sleep(self.settings.ai_worker_poll_seconds)

    async def _report_periodic(self, client: httpx.AsyncClient) -> None:
        now = asyncio.get_running_loop().time()
        if now - self._last_capability_report < self.settings.ai_worker_capability_report_seconds:
            return
        await self._heartbeat(client)
        await self._report_capabilities(client)
        if not self._local_images_reconciled:
            await self._reconcile_local_images(client)
            self._local_images_reconciled = True
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

    async def _claim_local_image_delete(self, client: httpx.AsyncClient) -> dict[str, Any]:
        response = await client.post(
            f"{self.cloud_url}/ai-worker/local-image-deletions/claim",
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
                nsfw_mode=job.get("nsfwMode") is True,
                nsfw_visibility_level=job.get("nsfwVisibilityLevel") or "STANDARD",
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

    async def _process_job(
        self,
        client: httpx.AsyncClient,
        job: dict[str, Any],
        inpaint_source_url: str = "",
    ) -> None:
        job_id = job["id"]
        local_job_id = ""
        comfy_prompt_id = ""
        stage = "CLAIMED"
        detail = "Cloud job claimed by worker."
        try:
            stage = "STARTING_LOCAL_GENERATION"
            detail = "Posting generation request to local FastAPI."
            local_job = await self._start_local_generation(job, inpaint_source_url)
            local_job_id = local_job["job_id"]
            stage = "LOCAL_GENERATION_RUNNING"
            detail = "Local FastAPI accepted generation request."
            running_response = await client.post(
                f"{self.cloud_url}/ai-worker/jobs/{job_id}/running",
                json={
                    "workerId": self.settings.ai_worker_id,
                    "localJobId": local_job_id,
                    "workerStage": stage,
                    "workerDetail": detail,
                },
            )
            self._raise_for_status(running_response, "mark cloud job running")
            await self._send_qq_queue_notice(job, local_job_id)
            try:
                local_result = await self._wait_local_job(local_job_id)
            except LocalGenerationError as exc:
                comfy_prompt_id = exc.comfy_prompt_id
                stage = "LOCAL_GENERATION_FAILED"
                detail = str(exc)
                raise
            comfy_prompt_id = str(local_result.get("comfy_prompt_id") or "")
            stage = "UPLOADING_TO_CLOUD"
            detail = "Local image generated; preparing cloud OSS upload."
            await self._mark_uploading(client, job_id, local_job_id, comfy_prompt_id, stage, detail)
            stage = "DOWNLOADING_LOCAL_IMAGE"
            image_bytes, filename = await self._download_local_image(local_result)
            stage = "COMPLETING_CLOUD_JOB"
            detail = f"Sending {filename} to cloud complete endpoint."
            await self._complete_cloud_job(client, job_id, local_job_id, comfy_prompt_id, local_result, image_bytes, filename)
            await self._send_qq_subscription(job, local_result, filename)
        except CloudCompletionDeliveryError as exc:
            print(
                f"[cloud-worker] completion delivery pending for job {job_id}; "
                f"local output was kept and the job was not marked failed: {exc}"
            )
        except Exception as exc:
            await self._fail_cloud_job(client, job_id, str(exc), local_job_id, comfy_prompt_id, stage, detail)

    async def _start_local_generation(self, job: dict[str, Any], inpaint_source_url: str = "") -> dict[str, Any]:
        payload = {
            "prompt_cn": job.get("promptCn") or "",
            "prompt_positive": job.get("promptPositive") or "",
            "prompt_negative": job.get("promptNegative") or "",
            "style_notes": job.get("styleNotes") or "",
            "generation_mode": job.get("generationMode") or "SINGLE",
            "character_id": job.get("characterId") or None,
            "second_character_id": job.get("secondCharacterId") or None,
            "character_mask_json": job.get("characterMaskJson") or "",
            "width": job.get("width") or 832,
            "height": job.get("height") or 1216,
            "steps": job.get("steps") or None,
            "cfg": job.get("cfg") or None,
            "seed": job.get("seed") or None,
            "checkpoint": job.get("checkpoint") or None,
            "lora_name": job.get("loraName") or "",
            "lora_strength": job.get("loraStrength") or 0,
            "second_lora_name": job.get("secondLoraName") or "",
            "second_lora_strength": job.get("secondLoraStrength") or 0,
            "nsfw_mode": job.get("nsfwMode") is True,
            "nsfw_visibility_level": job.get("nsfwVisibilityLevel") or "STANDARD",
            "job_type": job.get("jobType") or "TEXT2IMG",
            "parent_job_id": job.get("parentJobId"),
            "inpaint_instruction": job.get("inpaintInstruction") or "",
            "inpaint_mask_json": job.get("inpaintMaskJson") or "",
            "cloud_job_id": job.get("id"),
            "user_id": job.get("userId"),
            "storage_date": str(job.get("createdAt") or "")[:10] or None,
        }
        if payload["job_type"] == "INPAINT":
            raise RuntimeError("局部修复已下线，请使用一次性生成重新出图。")
        async with httpx.AsyncClient(timeout=30, headers={"User-Agent": USER_AGENT}) as local:
            response = await local.post(f"{self.local_url}/api/generate", json=payload)
            self._raise_for_status(response, "start local generation")
            return response.json()

    async def _wait_local_job(self, local_job_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30, headers={"User-Agent": USER_AGENT}) as local:
            while True:
                response = await local.get(f"{self.local_url}/api/jobs/{local_job_id}")
                self._raise_for_status(response, "poll local generation")
                job = response.json()
                status = job.get("status")
                if status == "completed":
                    return job
                if status == "failed":
                    raise LocalGenerationError(job.get("error") or "Local generation failed", job)
                await asyncio.sleep(2)

    async def _download_local_image(self, local_job: dict[str, Any]) -> tuple[bytes, str]:
        filename = local_job.get("image_path")
        if not filename:
            raise RuntimeError("Local generation completed without image_path.")
        async with httpx.AsyncClient(timeout=60, headers={"User-Agent": USER_AGENT}) as local:
            response = await local.get(f"{self.local_url}/api/images/{quote(filename, safe='/')}")
            self._raise_for_status(response, "download local image")
            return response.content, filename

    async def _mark_uploading(
        self,
        client: httpx.AsyncClient,
        job_id: int,
        local_job_id: str,
        comfy_prompt_id: str,
        stage: str,
        detail: str,
    ) -> None:
        response = await client.post(
            f"{self.cloud_url}/ai-worker/jobs/{job_id}/uploading",
            json={
                "workerId": self.settings.ai_worker_id,
                "localJobId": local_job_id,
                "comfyPromptId": comfy_prompt_id,
                "workerStage": stage,
                "workerDetail": detail,
            },
        )
        self._raise_for_status(response, "mark cloud job uploading")

    async def _complete_cloud_job(
        self,
        client: httpx.AsyncClient,
        job_id: int,
        local_job_id: str,
        comfy_prompt_id: str,
        local_result: dict[str, Any],
        image_bytes: bytes,
        filename: str,
    ) -> None:
        payload = {
            "workerId": self.settings.ai_worker_id,
            "localJobId": local_job_id,
            "comfyPromptId": comfy_prompt_id,
            "workerStage": "COMPLETED",
            "workerDetail": f"Cloud accepted local image {filename}.",
            "imageBase64": base64.b64encode(image_bytes).decode("ascii"),
            "contentType": "image/png",
            "filename": filename,
            "localRelativePath": filename.replace("\\", "/"),
            "localAbsolutePath": str(self._resolve_output_path(filename)),
            "promptPositive": local_result.get("prompt_positive"),
            "promptNegative": local_result.get("prompt_negative"),
            "styleNotes": local_result.get("style_notes"),
            "seed": local_result.get("seed"),
        }
        for attempt in range(1, COMPLETE_MAX_ATTEMPTS + 1):
            try:
                response = await client.post(
                    f"{self.cloud_url}/ai-worker/jobs/{job_id}/complete",
                    json=payload,
                    timeout=120,
                )
            except httpx.TransportError as exc:
                if attempt == COMPLETE_MAX_ATTEMPTS:
                    raise CloudCompletionDeliveryError(
                        f"transport error after {attempt} attempts: {exc}"
                    ) from exc
                await self._wait_before_complete_retry(job_id, attempt, str(exc))
                continue

            if response.status_code < 400:
                return
            if response.status_code < 500 and response.status_code not in {408, 429}:
                self._raise_for_status(response, "complete cloud job")
            if attempt == COMPLETE_MAX_ATTEMPTS:
                body = response.text.strip()
                if len(body) > 500:
                    body = body[:500] + "..."
                raise CloudCompletionDeliveryError(
                    f"HTTP {response.status_code} after {attempt} attempts: {body}"
                )
            await self._wait_before_complete_retry(
                job_id,
                attempt,
                f"HTTP {response.status_code}",
            )

    async def _send_qq_subscription(
        self,
        job: dict[str, Any],
        local_result: dict[str, Any],
        filename: str,
    ) -> None:
        qq_number = str(job.get("qqNumber") or "").strip()
        if not qq_number or not self.settings.qq_bot_send_image_url:
            return
        image_path = self._resolve_output_path(filename)
        if not image_path.exists():
            print(f"[cloud-worker] QQ delivery skipped; local image missing: {image_path}")
            return
        payload = {
            "type": "image",
            "qq": qq_number,
            "userId": job.get("userId"),
            "jobId": job.get("id"),
            "imagePath": str(image_path),
            "localRelativePath": filename.replace("\\", "/"),
            "message": "AI 绘图已完成。",
            "promptCn": job.get("promptCn") or "",
            "seed": local_result.get("seed"),
        }
        try:
            async with httpx.AsyncClient(timeout=30, headers=self._qq_bot_headers()) as bot:
                response = await bot.post(self.settings.qq_bot_send_image_url, json=payload)
                self._raise_for_status(response, "send QQ subscription image")
        except Exception as exc:
            print(f"[cloud-worker] QQ delivery failed for job {job.get('id')} to {qq_number}: {exc}")

    async def _send_qq_queue_notice(self, job: dict[str, Any], local_job_id: str) -> None:
        qq_number = str(job.get("qqNumber") or "").strip()
        bot_url = self.settings.qq_bot_send_message_url or self.settings.qq_bot_send_image_url
        if not qq_number or not bot_url:
            return
        payload = {
            "type": "message",
            "qq": qq_number,
            "userId": job.get("userId"),
            "jobId": job.get("id"),
            "localJobId": local_job_id,
            "message": "AI 绘图已进入本机队列，正在排队生成。",
            "promptCn": job.get("promptCn") or "",
        }
        try:
            async with httpx.AsyncClient(timeout=30, headers=self._qq_bot_headers()) as bot:
                response = await bot.post(bot_url, json=payload)
                self._raise_for_status(response, "send QQ queue notice")
        except Exception as exc:
            print(f"[cloud-worker] QQ queue notice failed for job {job.get('id')} to {qq_number}: {exc}")

    async def _send_qq_startup_notice(self) -> None:
        bot_url = (
            self.settings.qq_bot_startup_notice_url
            or self.settings.qq_bot_send_message_url
            or self.settings.qq_bot_send_image_url
        )
        if not bot_url:
            return
        payload = {
            "type": "worker_startup",
            "workerId": self.settings.ai_worker_id,
            "workerName": self.settings.ai_worker_name,
            "workerVersion": self.settings.ai_worker_version,
            "message": "AI 绘图 Worker 已启动，正在等待任务。",
        }
        startup_qq = self.settings.qq_bot_startup_qq.strip()
        if startup_qq:
            payload["qq"] = startup_qq
        try:
            async with httpx.AsyncClient(timeout=30, headers=self._qq_bot_headers()) as bot:
                response = await bot.post(bot_url, json=payload)
                self._raise_for_status(response, "send QQ worker startup notice")
        except Exception as exc:
            print(f"[cloud-worker] QQ worker startup notice failed: {exc}")

    def _qq_bot_headers(self) -> dict[str, str]:
        headers = {"User-Agent": USER_AGENT}
        if self.settings.qq_bot_token:
            headers["Authorization"] = f"Bearer {self.settings.qq_bot_token}"
        return headers

    async def _wait_before_complete_retry(self, job_id: int, attempt: int, reason: str) -> None:
        delay = COMPLETE_RETRY_BASE_SECONDS * (2 ** (attempt - 1))
        print(
            f"[cloud-worker] retrying completion for job {job_id} in {delay:.0f}s "
            f"after attempt {attempt}: {reason}"
        )
        await asyncio.sleep(delay)

    async def _fail_cloud_job(
        self,
        client: httpx.AsyncClient,
        job_id: int,
        error: str,
        local_job_id: str = "",
        comfy_prompt_id: str = "",
        stage: str = "FAILED",
        detail: str = "",
    ) -> None:
        response = await client.post(
            f"{self.cloud_url}/ai-worker/jobs/{job_id}/fail",
            json={
                "workerId": self.settings.ai_worker_id,
                "localJobId": local_job_id,
                "comfyPromptId": comfy_prompt_id,
                "workerStage": stage,
                "workerDetail": detail,
                "errorMessage": error[:1000],
            },
        )
        self._raise_for_status(response, "fail cloud job")

    async def _fail_prompt_translation(self, client: httpx.AsyncClient, job_id: int, error: str) -> None:
        response = await client.post(
            f"{self.cloud_url}/ai-worker/prompt-translations/{job_id}/fail",
            json={"workerId": self.settings.ai_worker_id, "errorMessage": error[:1000]},
        )
        response.raise_for_status()

    async def _reconcile_local_images(self, client: httpx.AsyncClient) -> None:
        from app.db import JobStore

        jobs = JobStore(self.settings.database_path).list_completed_jobs()
        if not jobs:
            return
        items = [
            {
                "localJobId": job["id"],
                "currentRelativePath": job.get("image_path") or "",
                "currentAbsolutePath": str(self._resolve_output_path(job.get("image_path") or "")),
            }
            for job in jobs
            if job.get("image_path")
        ]
        for start in range(0, len(items), 100):
            response = await client.post(
                f"{self.cloud_url}/ai-worker/local-images/reconcile",
                json={"workerId": self.settings.ai_worker_id, "items": items[start:start + 100]},
            )
            response.raise_for_status()
            for result in response.json():
                if result.get("status") != "MATCHED":
                    print(
                        f"[cloud-worker] local image reconcile skipped "
                        f"{result.get('localJobId')}: {result.get('message')}"
                    )
                    continue
                await self._move_and_report_local_image(client, result)

    async def _move_and_report_local_image(
        self,
        client: httpx.AsyncClient,
        result: dict[str, Any],
    ) -> None:
        from app.db import JobStore

        store = JobStore(self.settings.database_path)
        local_job = store.get_job(str(result["localJobId"]))
        if not local_job or not local_job.get("image_path"):
            return
        source = self._resolve_output_path(local_job["image_path"])
        target_relative = str(result["targetRelativePath"]).replace("\\", "/")
        target = self._resolve_output_path(target_relative)
        if source != target:
            if not source.exists():
                print(f"[cloud-worker] reconcile source missing: {source}")
                return
            if target.exists():
                print(f"[cloud-worker] reconcile target already exists, keeping source: {target}")
                return
            target.parent.mkdir(parents=True, exist_ok=True)
            source.replace(target)
        store.update_job(str(result["localJobId"]), image_path=target_relative)
        response = await client.post(
            f"{self.cloud_url}/ai-worker/jobs/{result['jobId']}/local-image",
            json={
                "workerId": self.settings.ai_worker_id,
                "localJobId": result["localJobId"],
                "localRelativePath": target_relative,
                "localAbsolutePath": str(target),
            },
        )
        response.raise_for_status()

    async def _process_local_image_delete(
        self,
        client: httpx.AsyncClient,
        command: dict[str, Any],
    ) -> None:
        command_id = command["id"]
        try:
            path = self._resolve_output_path(command.get("localRelativePath") or "")
            if path.exists():
                if path.suffix.lower() not in IMAGE_SUFFIXES:
                    raise RuntimeError("Local image extension is not allowed")
                path.unlink()
            response = await client.post(
                f"{self.cloud_url}/ai-worker/local-image-deletions/{command_id}/complete",
                json={"workerId": self.settings.ai_worker_id},
            )
            response.raise_for_status()
        except Exception as exc:
            response = await client.post(
                f"{self.cloud_url}/ai-worker/local-image-deletions/{command_id}/fail",
                json={
                    "workerId": self.settings.ai_worker_id,
                    "errorMessage": str(exc)[:1000],
                },
            )
            response.raise_for_status()

    def _resolve_output_path(self, relative_path: str) -> Path:
        normalized = str(relative_path or "").replace("\\", "/")
        if normalized.startswith("/") or (len(normalized) >= 2 and normalized[1] == ":"):
            raise RuntimeError("Local image path escapes OUTPUT_DIR")
        root = self.settings.output_dir.resolve()
        candidate = (root / normalized).resolve()
        if not normalized or not candidate.is_relative_to(root):
            raise RuntimeError("Local image path escapes OUTPUT_DIR")
        return candidate

    @staticmethod
    def _raise_for_status(response: httpx.Response, action: str) -> None:
        if response.status_code < 400:
            return
        body = response.text.strip()
        if len(body) > 500:
            body = body[:500] + "..."
        raise RuntimeError(f"{action} failed: HTTP {response.status_code} {body}")


async def main() -> None:
    worker = CloudWorker(get_settings())
    await worker.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
