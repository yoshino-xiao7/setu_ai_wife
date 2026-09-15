from __future__ import annotations

import asyncio
import random
import urllib.parse
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


class ComfyUIExecutionError(RuntimeError):
    pass


def is_anima_checkpoint(checkpoint: str | None) -> bool:
    name = (checkpoint or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name.startswith("anima-")


def build_anima_workflow(
    *,
    positive: str,
    negative: str,
    seed: int,
    width: int,
    height: int,
    steps: int,
    cfg: float,
    unet_name: str,
    clip_name: str,
    vae_name: str,
    sampler: str = "er_sde",
    scheduler: str = "simple",
    filename_prefix: str = "local_ai_drawing_anima",
) -> dict[str, Any]:
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": unet_name, "weight_dtype": "default"},
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": clip_name, "type": "qwen_image", "device": "default"},
        },
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae_name}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["2", 0]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["2", 0]}},
        "6": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler,
                "scheduler": scheduler,
                "denoise": 1,
                "model": ["1", 0],
                "positive": ["4", 0],
                "negative": ["5", 0],
                "latent_image": ["6", 0],
            },
        },
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": filename_prefix, "images": ["8", 0]},
        },
    }


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
    second_lora_name: str = "",
    second_lora_strength: float = 0,
    regional_left_positive: str = "",
    regional_right_positive: str = "",
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
    model_ref: list[Any] = ["4", 0]
    clip_ref: list[Any] = ["4", 1]
    if lora_name and lora_strength > 0:
        workflow["10"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": lora_name,
                "strength_model": lora_strength,
                "strength_clip": lora_strength,
                "model": model_ref,
                "clip": clip_ref,
            },
        }
        model_ref = ["10", 0]
        clip_ref = ["10", 1]
    if second_lora_name and second_lora_strength > 0:
        workflow["11"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": second_lora_name,
                "strength_model": second_lora_strength,
                "strength_clip": second_lora_strength,
                "model": model_ref,
                "clip": clip_ref,
            },
        }
        model_ref = ["11", 0]
        clip_ref = ["11", 1]
    workflow["3"]["inputs"]["model"] = model_ref
    workflow["6"]["inputs"]["clip"] = clip_ref
    workflow["7"]["inputs"]["clip"] = clip_ref
    if regional_left_positive and regional_right_positive:
        left_width, right_width, right_x = regional_area_geometry(width)
        workflow["12"] = {"class_type": "CLIPTextEncode", "inputs": {"text": regional_left_positive, "clip": clip_ref}}
        workflow["13"] = {"class_type": "CLIPTextEncode", "inputs": {"text": regional_right_positive, "clip": clip_ref}}
        workflow["14"] = {
            "class_type": "ConditioningSetArea",
            "inputs": {
                "conditioning": ["12", 0],
                "width": left_width,
                "height": height,
                "x": 0,
                "y": 0,
                "strength": 1.15,
            },
        }
        workflow["15"] = {
            "class_type": "ConditioningSetArea",
            "inputs": {
                "conditioning": ["13", 0],
                "width": right_width,
                "height": height,
                "x": right_x,
                "y": 0,
                "strength": 1.15,
            },
        }
        workflow["16"] = {
            "class_type": "ConditioningCombine",
            "inputs": {"conditioning_1": ["6", 0], "conditioning_2": ["14", 0]},
        }
        workflow["17"] = {
            "class_type": "ConditioningCombine",
            "inputs": {"conditioning_1": ["16", 0], "conditioning_2": ["15", 0]},
        }
        workflow["3"]["inputs"]["positive"] = ["17", 0]
    return workflow


def build_mask_conditioning_workflow(
    *,
    positive: str,
    negative: str,
    regional_left_positive: str,
    regional_right_positive: str,
    left_mask_image: str,
    right_mask_image: str,
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
    second_lora_name: str = "",
    second_lora_strength: float = 0,
    mask_strength: float = 1.15,
    filename_prefix: str = "local_ai_drawing",
) -> dict[str, Any]:
    workflow: dict[str, Any] = {
        "1": {"class_type": "LoadImageMask", "inputs": {"image": left_mask_image, "channel": "red"}},
        "2": {"class_type": "LoadImageMask", "inputs": {"image": right_mask_image, "channel": "red"}},
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
                "positive": ["17", 0],
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
        "12": {"class_type": "CLIPTextEncode", "inputs": {"text": regional_left_positive, "clip": ["4", 1]}},
        "13": {"class_type": "CLIPTextEncode", "inputs": {"text": regional_right_positive, "clip": ["4", 1]}},
        "14": {
            "class_type": "ConditioningSetMask",
            "inputs": {
                "conditioning": ["12", 0],
                "mask": ["1", 0],
                "strength": mask_strength,
                "set_cond_area": "default",
            },
        },
        "15": {
            "class_type": "ConditioningSetMask",
            "inputs": {
                "conditioning": ["13", 0],
                "mask": ["2", 0],
                "strength": mask_strength,
                "set_cond_area": "default",
            },
        },
        "16": {
            "class_type": "ConditioningCombine",
            "inputs": {"conditioning_1": ["6", 0], "conditioning_2": ["14", 0]},
        },
        "17": {
            "class_type": "ConditioningCombine",
            "inputs": {"conditioning_1": ["16", 0], "conditioning_2": ["15", 0]},
        },
    }
    model_ref: list[Any] = ["4", 0]
    clip_ref: list[Any] = ["4", 1]
    if lora_name and lora_strength > 0:
        workflow["10"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": lora_name,
                "strength_model": lora_strength,
                "strength_clip": lora_strength,
                "model": model_ref,
                "clip": clip_ref,
            },
        }
        model_ref = ["10", 0]
        clip_ref = ["10", 1]
    if second_lora_name and second_lora_strength > 0:
        workflow["11"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": second_lora_name,
                "strength_model": second_lora_strength,
                "strength_clip": second_lora_strength,
                "model": model_ref,
                "clip": clip_ref,
            },
        }
        model_ref = ["11", 0]
        clip_ref = ["11", 1]
    workflow["3"]["inputs"]["model"] = model_ref
    workflow["6"]["inputs"]["clip"] = clip_ref
    workflow["7"]["inputs"]["clip"] = clip_ref
    workflow["12"]["inputs"]["clip"] = clip_ref
    workflow["13"]["inputs"]["clip"] = clip_ref
    return workflow


def build_inpaint_workflow(
    *,
    positive: str,
    negative: str,
    seed: int,
    steps: int,
    cfg: float,
    checkpoint: str,
    sampler: str,
    scheduler: str,
    base_image: str,
    mask_image: str,
    denoise: float,
    lora_name: str = "",
    lora_strength: float = 0,
    second_lora_name: str = "",
    second_lora_strength: float = 0,
    grow_mask_by: int = 12,
    filename_prefix: str = "local_ai_drawing_inpaint",
) -> dict[str, Any]:
    workflow: dict[str, Any] = {
        "1": {"class_type": "LoadImage", "inputs": {"image": base_image}},
        "2": {"class_type": "LoadImageMask", "inputs": {"image": mask_image, "channel": "red"}},
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler,
                "scheduler": scheduler,
                "denoise": denoise,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "5": {
            "class_type": "VAEEncodeForInpaint",
            "inputs": {
                "pixels": ["1", 0],
                "vae": ["4", 2],
                "mask": ["2", 0],
                "grow_mask_by": max(0, grow_mask_by),
            },
        },
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
    if second_lora_name and second_lora_strength > 0:
        previous_model = workflow["3"]["inputs"]["model"]
        previous_clip = workflow["6"]["inputs"]["clip"]
        workflow["11"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": second_lora_name,
                "strength_model": second_lora_strength,
                "strength_clip": second_lora_strength,
                "model": previous_model,
                "clip": previous_clip,
            },
        }
        workflow["3"]["inputs"]["model"] = ["11", 0]
        workflow["6"]["inputs"]["clip"] = ["11", 1]
        workflow["7"]["inputs"]["clip"] = ["11", 1]
    return workflow


def build_brushnet_inpaint_workflow(
    *,
    positive: str,
    negative: str,
    seed: int,
    steps: int,
    cfg: float,
    checkpoint: str,
    sampler: str,
    scheduler: str,
    base_image: str,
    mask_image: str,
    denoise: float,
    brushnet_model: str,
    brushnet_dtype: str = "float16",
    brushnet_scale: float = 1.0,
    lora_name: str = "",
    lora_strength: float = 0,
    second_lora_name: str = "",
    second_lora_strength: float = 0,
    filename_prefix: str = "local_ai_drawing_brushnet_inpaint",
) -> dict[str, Any]:
    workflow: dict[str, Any] = {
        "1": {"class_type": "LoadImage", "inputs": {"image": base_image}},
        "2": {"class_type": "LoadImageMask", "inputs": {"image": mask_image, "channel": "red"}},
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler,
                "scheduler": scheduler,
                "denoise": denoise,
                "model": ["12", 0],
                "positive": ["12", 1],
                "negative": ["12", 2],
                "latent_image": ["12", 3],
            },
        },
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "5": {
            "class_type": "BrushNetLoader",
            "inputs": {
                "brushnet": brushnet_model,
                "dtype": brushnet_dtype if brushnet_dtype in {"float16", "bfloat16", "float32", "float64"} else "float16",
            },
        },
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["4", 1]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": filename_prefix, "images": ["8", 0]}},
        "12": {
            "class_type": "BrushNet",
            "inputs": {
                "model": ["4", 0],
                "vae": ["4", 2],
                "image": ["1", 0],
                "mask": ["2", 0],
                "brushnet": ["5", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "scale": max(0.0, brushnet_scale),
                "start_at": 0,
                "end_at": 10000,
            },
        },
    }
    model_ref: list[Any] = ["4", 0]
    clip_ref: list[Any] = ["4", 1]
    if lora_name and lora_strength > 0:
        workflow["10"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": lora_name,
                "strength_model": lora_strength,
                "strength_clip": lora_strength,
                "model": model_ref,
                "clip": clip_ref,
            },
        }
        model_ref = ["10", 0]
        clip_ref = ["10", 1]
    if second_lora_name and second_lora_strength > 0:
        workflow["11"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": second_lora_name,
                "strength_model": second_lora_strength,
                "strength_clip": second_lora_strength,
                "model": model_ref,
                "clip": clip_ref,
            },
        }
        model_ref = ["11", 0]
        clip_ref = ["11", 1]
    workflow["12"]["inputs"]["model"] = model_ref
    workflow["6"]["inputs"]["clip"] = clip_ref
    workflow["7"]["inputs"]["clip"] = clip_ref
    return workflow


def regional_area_geometry(width: int) -> tuple[int, int, int]:
    overlap = round_to_multiple_of_8(max(64, min(160, width // 10)))
    half_width = round_to_multiple_of_8(width // 2)
    left_width = min(width, round_to_multiple_of_8(half_width + overlap))
    right_width = min(width, round_to_multiple_of_8(width - half_width + overlap))
    right_x = max(0, round_to_multiple_of_8(width - right_width))
    return left_width, right_width, right_x


def round_to_multiple_of_8(value: int) -> int:
    return max(64, int(round(value / 8)) * 8)


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

    async def upload_image(self, path: Path, filename: str | None = None) -> str:
        upload_name = filename or path.name
        data = {"type": "input", "overwrite": "true"}
        with path.open("rb") as file:
            files = {"image": (upload_name, file, "image/png")}
            async with httpx.AsyncClient(timeout=self.settings.comfyui_timeout_seconds) as client:
                response = await client.post(f"{self.base_url}/upload/image", data=data, files=files)
                response.raise_for_status()
        return response.json()["name"]

    async def wait_for_history(self, prompt_id: str, timeout_seconds: int = 600) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        async with httpx.AsyncClient(timeout=self.settings.comfyui_timeout_seconds) as client:
            while asyncio.get_running_loop().time() < deadline:
                response = await client.get(f"{self.base_url}/history/{prompt_id}")
                response.raise_for_status()
                data = response.json()
                if prompt_id in data:
                    return data[prompt_id]
                await asyncio.sleep(self.settings.generation_poll_seconds)
        raise TimeoutError("ComfyUI generation timed out.")

    async def download_first_image(self, history: dict[str, Any], output_dir: Path, job_id: str) -> Path:
        status = history.get("status", {})
        if status.get("status_str") == "error":
            raise ComfyUIExecutionError(comfyui_history_error_message(history))
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
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(response.content)
                self.cleanup_comfyui_image(image)
                return target
        raise RuntimeError("ComfyUI completed but returned no image outputs.")

    def cleanup_comfyui_image(self, image: dict[str, Any]) -> None:
        if image.get("type", "output") != "output":
            return
        filename = Path(str(image.get("filename", ""))).name
        if not filename or Path(filename).suffix.lower() not in IMAGE_SUFFIXES:
            return

        output_root = self.settings.comfyui_models_dir.parent / "output"
        subfolder = Path(str(image.get("subfolder", "")))
        candidate = output_root / subfolder / filename
        try:
            resolved_root = output_root.resolve()
            resolved_candidate = candidate.resolve()
        except OSError:
            return
        if not resolved_candidate.is_relative_to(resolved_root):
            return
        try:
            if resolved_candidate.exists():
                resolved_candidate.unlink()
        except OSError as exc:
            print(f"[comfyui] cleanup skipped for {filename}: {exc}")

    def cleanup_comfyui_input_file(self, filename: str) -> None:
        safe_name = Path(filename).name
        if not safe_name or Path(safe_name).suffix.lower() not in IMAGE_SUFFIXES:
            return

        input_root = self.settings.comfyui_models_dir.parent / "input"
        candidate = input_root / safe_name
        try:
            resolved_root = input_root.resolve()
            resolved_candidate = candidate.resolve()
        except OSError:
            return
        if not resolved_candidate.is_relative_to(resolved_root):
            return
        try:
            if resolved_candidate.exists():
                resolved_candidate.unlink()
        except OSError as exc:
            print(f"[comfyui] input cleanup skipped for {safe_name}: {exc}")


def random_seed() -> int:
    return random.randint(1, 2**32 - 1)


def comfyui_history_error_message(history: dict[str, Any]) -> str:
    messages = history.get("status", {}).get("messages", [])
    for event_name, payload in reversed(messages):
        if event_name == "execution_error" and isinstance(payload, dict):
            node_type = payload.get("node_type") or "unknown"
            node_id = payload.get("node_id") or "?"
            message = str(payload.get("exception_message") or payload.get("exception_type") or "unknown error").strip()
            return f"ComfyUI execution failed at node {node_id} ({node_type}): {message}"
    return "ComfyUI execution failed."
