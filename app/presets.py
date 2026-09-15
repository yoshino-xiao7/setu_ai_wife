from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.config import Settings


class CharacterPreset(BaseModel):
    id: str
    name: str
    category: str = "未分类角色"
    category_type: str = ""
    lora_name: str = ""
    lora_strength: float = 0.8
    trigger_words: str = ""
    default_positive: str = ""
    default_outfit: str = ""
    style_tags: str = ""
    preview_image: str = ""
    recommended_checkpoint: str = ""
    notes: str = ""


class LoraMetadata(BaseModel):
    name: str
    display_name: str = ""
    category: str = "未分类"
    category_type: str = ""
    trigger_words: str = ""
    recommended_strength: float = 1.0
    recommended_checkpoint: str = ""
    preview_image: str = ""
    notes: str = ""


class CheckpointMetadata(BaseModel):
    name: str
    display_name: str = ""
    category: str = "未分类模型"
    category_type: str = "Checkpoint"
    preview_image: str = ""
    notes: str = ""


class PromptPreset(BaseModel):
    id: str
    name: str
    category: str = "未分类提示词"
    category_type: str = "提示词预设"
    trigger_words: str = ""
    style_tags: str = ""
    default_positive: str = ""
    default_negative: str = ""
    preview_image: str = ""
    recommended_checkpoint: str = ""
    recommended_lora: str = ""
    recommended_lora_strength: float = 0.0
    nsfw_only: bool = False
    notes: str = ""


def load_characters(path: Path) -> list[CharacterPreset]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("characters", [])
    return [CharacterPreset(**item) for item in data]


def load_prompt_presets(path: Path) -> list[PromptPreset]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("prompt_presets", [])
    return [PromptPreset(**item) for item in data]


def load_lora_metadata(path: Path) -> dict[str, LoraMetadata]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("loras", [])
    result: dict[str, LoraMetadata] = {}
    for item in data:
        metadata = LoraMetadata(**item)
        result[metadata.name] = metadata
    return result


def load_checkpoint_metadata(path: Path) -> dict[str, CheckpointMetadata]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("checkpoints", [])
    result: dict[str, CheckpointMetadata] = {}
    for item in data:
        metadata = CheckpointMetadata(**item)
        result[metadata.name] = metadata
    return result


def find_character(settings: Settings, character_id: str | None) -> CharacterPreset | None:
    if not character_id:
        return None
    for character in load_characters(settings.characters_path):
        if character.id == character_id:
            return character
    return None


def list_checkpoints(settings: Settings) -> list[dict[str, Any]]:
    checkpoint_dir = settings.comfyui_models_dir / "checkpoints"
    if not checkpoint_dir.exists():
        return []
    metadata_by_name = load_checkpoint_metadata(settings.checkpoint_metadata_path)
    suffixes = {".safetensors", ".pt", ".ckpt"}
    items: list[dict[str, Any]] = []
    for file in sorted(checkpoint_dir.rglob("*"), key=lambda item: str(item).lower()):
        if not file.is_file() or file.suffix.lower() not in suffixes:
            continue
        relative_name = str(file.relative_to(checkpoint_dir)).replace("\\", "/")
        metadata = metadata_by_name.get(relative_name) or metadata_by_name.get(file.name)
        if metadata is None:
            continue
        items.append(
            {
                "name": relative_name,
                "displayName": metadata.display_name or file.stem,
                "size": file.stat().st_size,
                "sizeBytes": file.stat().st_size,
                "metadataJson": metadata.model_dump_json(),
            }
        )
    return items


def anima_display_name(filename: str) -> str:
    stem = Path(filename).stem.replace("_", "-")
    return " ".join(part.upper() if part.lower() == "anima" else part for part in stem.split("-"))


def list_anima_models(settings: Settings) -> list[dict[str, Any]]:
    unet_dir = settings.comfyui_models_dir / "diffusion_models"
    if not unet_dir.exists():
        return []
    items: list[dict[str, Any]] = []
    for file in sorted(unet_dir.iterdir(), key=lambda item: item.name.lower()):
        if not file.is_file() or file.suffix.lower() != ".safetensors":
            continue
        if not file.name.lower().startswith("anima-"):
            continue
        display_name = anima_display_name(file.name)
        metadata = {
            "name": file.name,
            "display_name": display_name,
            "category": "Anima",
            "category_type": "工作流",
            "pipeline": "anima",
            "notes": "CircleStone Anima，使用独立 UNET / Qwen 工作流。现有 Illustrious LoRA 不会套用。",
        }
        items.append(
            {
                "name": file.name,
                "displayName": display_name,
                "size": file.stat().st_size,
                "sizeBytes": file.stat().st_size,
                "metadataJson": json.dumps(metadata, ensure_ascii=False),
            }
        )
    return items


def list_loras(settings: Settings) -> list[dict[str, Any]]:
    lora_dir = settings.comfyui_models_dir / "loras"
    if not lora_dir.exists():
        return []
    metadata_by_name = load_lora_metadata(settings.lora_metadata_path)
    suffixes = {".safetensors", ".pt", ".ckpt"}
    items: list[dict[str, Any]] = []
    for file in sorted(lora_dir.iterdir(), key=lambda item: item.name.lower()):
        if not file.is_file() or file.suffix.lower() not in suffixes:
            continue
        metadata = metadata_by_name.get(file.name)
        metadata_json = metadata.model_dump_json() if metadata else ""
        items.append(
            {
                "name": file.name,
                "displayName": metadata.display_name if metadata and metadata.display_name else file.stem,
                "size": file.stat().st_size,
                "sizeBytes": file.stat().st_size,
                "metadataJson": metadata_json,
            }
        )
    return items


def merge_tags(*parts: str) -> str:
    tags: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if not part or not part.strip(" ,"):
            continue
        for raw_tag in part.split(","):
            tag = raw_tag.strip()
            key = tag.lower()
            if not tag or key in seen:
                continue
            seen.add(key)
            tags.append(tag)
    return ", ".join(tags)
