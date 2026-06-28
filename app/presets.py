from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.config import Settings


class CharacterPreset(BaseModel):
    id: str
    name: str
    lora_name: str = ""
    lora_strength: float = 0.8
    trigger_words: str = ""
    default_positive: str = ""
    style_tags: str = ""
    preview_image: str = ""
    recommended_checkpoint: str = ""
    notes: str = ""


class LoraMetadata(BaseModel):
    name: str
    display_name: str = ""
    trigger_words: str = ""
    recommended_strength: float = 1.0
    recommended_checkpoint: str = ""
    preview_image: str = ""
    notes: str = ""


def load_characters(path: Path) -> list[CharacterPreset]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("characters", [])
    return [CharacterPreset(**item) for item in data]


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


def find_character(settings: Settings, character_id: str | None) -> CharacterPreset | None:
    if not character_id:
        return None
    for character in load_characters(settings.characters_path):
        if character.id == character_id:
            return character
    return None


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
    return ", ".join(part.strip(" ,") for part in parts if part and part.strip(" ,"))
