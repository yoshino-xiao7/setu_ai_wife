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
    notes: str = ""


def load_characters(path: Path) -> list[CharacterPreset]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("characters", [])
    return [CharacterPreset(**item) for item in data]


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
    suffixes = {".safetensors", ".pt", ".ckpt"}
    return [
        {"name": file.name, "size": file.stat().st_size}
        for file in sorted(lora_dir.iterdir(), key=lambda item: item.name.lower())
        if file.is_file() and file.suffix.lower() in suffixes
    ]


def merge_tags(*parts: str) -> str:
    return ", ".join(part.strip(" ,") for part in parts if part and part.strip(" ,"))
