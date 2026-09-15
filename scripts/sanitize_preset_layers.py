from __future__ import annotations

import json
from pathlib import Path

from app.prompt_tags import sanitize_preset_layer

ROOT = Path(__file__).resolve().parents[1]
PRESETS_PATH = ROOT / "config" / "prompt_presets.json"


def main() -> None:
    payload = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
    presets = [sanitize_preset_layer(item) for item in payload["prompt_presets"]]
    payload["prompt_presets"] = presets
    meta = payload.get("_meta")
    if isinstance(meta, dict):
        meta["version"] = "2026-09-15"
        rules = meta.get("organization_rules")
        if isinstance(rules, dict):
            rules["stacking"] = (
                "场景只写地点和光，不准写衣服。"
                "衣服只写那件衣服，不准写沙滩/花海/房间。"
                "叠用时服装层优先于场景里残留的连衣裙等默认衣服。"
            )
    PRESETS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"sanitized {len(presets)} presets")


if __name__ == "__main__":
    main()
