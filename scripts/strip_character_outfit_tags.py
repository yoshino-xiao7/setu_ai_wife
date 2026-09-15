from __future__ import annotations

import json
from pathlib import Path

from app.prompting import filter_character_identity_tags, normalize_tag_key

ROOT = Path(__file__).resolve().parents[1]
CHARACTERS_PATH = ROOT / "config" / "characters.json"


def main() -> None:
    payload = json.loads(CHARACTERS_PATH.read_text(encoding="utf-8"))
    characters = payload.get("characters", payload)
    for character in characters:
        raw_positive = str(character.get("default_positive") or "")
        raw_style = str(character.get("style_tags") or "")
        identity = filter_character_identity_tags(raw_positive)
        kept = {normalize_tag_key(tag) for tag in identity.split(",") if tag.strip()}
        outfit_parts = [
            tag.strip()
            for source in (raw_positive, raw_style)
            for tag in source.split(",")
            if tag.strip() and normalize_tag_key(tag) not in kept
        ]
        outfit = ", ".join(dict.fromkeys(outfit_parts))
        character["default_positive"] = identity
        character["default_outfit"] = outfit or str(character.get("default_outfit") or "")
        character["style_tags"] = ""
    CHARACTERS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"rewrote {len(characters)} characters")


if __name__ == "__main__":
    main()
