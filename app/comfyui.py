from __future__ import annotations

import asyncio
import random
import urllib.parse
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings


def build_workflow(
    *,
    positive: str,
    negative: str,
    seed: int,
    width: int,
    height: int,
    steps: int,
    cfg: float,
    checkpoint: str,
    sampler: str,
    scheduler: str,
    lora_name: str = "",
    lora_strength: float = 0,
    filename_prefix: str = "local_ai_drawing",
) -> dict[str, Any]:
    workflow: dict[str, Any] = {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler,
                "scheduler": scheduler,
                "denoise": 1,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["4", 1]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": filename_prefix, "images": ["8", 0]}},
    }
    if lora_name and lora_strength > 0:
        workflow["10"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": lora_name,
                "strength_model": lora_strength,
                "strength_clip": lora_strength,
                "model": ["4", 0],
                "clip": ["4", 1],
            },
        }
        workflow["3"]["inputs"]["model"] = ["10", 0]
        workflow["6"]["inputs"]["clip"] = ["10", 1]
        workflow["7"]["inputs"]["clip"] = ["10", 1]
    return workflow


class ComfyUIClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.comfyui_url.rstrip("/")

    async def queue_prompt(self, workflow: dict[str, Any], client_id: str) -> str:
        payload = {"prompt": workflow, "client_id": client_id}
        async with httpx.AsyncClient(timeout=self.settings.comfyui_timeout_seconds) as client:
            response = await client.post(f"{self.base_url}/prompt", json=payload)
            if response.is_error:
                raise RuntimeError(f"ComfyUI rejected prompt: {response.status_code} {response.text}")
        return response.json()["prompt_id"]

    async def wait_for_history(self, prompt_id: str, timeout_seconds: int = 600) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        async with httpx.AsyncClient(timeout=self.settings.comfyui_timeout_seconds) as client:
            while asyncio.get_running_loop().time() < deadline:
                response = await client.get(f"{self.base_url}/history/{prompt_id}")
                response.raise_for_status()
                data = response.json()
                if prompt_id in data:
                    return data[prompt_id]
                await asyncio.sleep(2)
        raise TimeoutError("ComfyUI generation timed out.")

    async def download_first_image(self, history: dict[str, Any], output_dir: Path, job_id: str) -> Path:
        outputs = history.get("outputs", {})
        for node_output in outputs.values():
            for image in node_output.get("images", []):
                params = urllib.parse.urlencode(
                    {
                        "filename": image["filename"],
                        "subfolder": image.get("subfolder", ""),
                        "type": image.get("type", "output"),
                    }
                )
                async with httpx.AsyncClient(timeout=self.settings.comfyui_timeout_seconds) as client:
                    response = await client.get(f"{self.base_url}/view?{params}")
                    response.raise_for_status()
                suffix = Path(image["filename"]).suffix or ".png"
                target = output_dir / f"{job_id}{suffix}"
                target.write_bytes(response.content)
                return target
        raise RuntimeError("ComfyUI completed but returned no image outputs.")


def random_seed() -> int:
    return random.randint(1, 2**32 - 1)
