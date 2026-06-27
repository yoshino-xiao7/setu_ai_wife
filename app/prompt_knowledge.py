from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


SHORT_ALIAS_BOUNDARIES = set(" \t\r\n,.;:!?，。；：！？、/\\|()（）[]【】{}<>《》\"'`~和与及跟同在的为是把将被")


@dataclass(frozen=True)
class KnowledgeEntry:
    aliases: tuple[str, ...]
    target: str
    franchise: str = ""
    tags: tuple[str, ...] = ()
    note: str = ""


def load_prompt_knowledge(path: Path) -> tuple[KnowledgeEntry, ...]:
    return _load_prompt_knowledge_cached(str(path.resolve()))


@lru_cache(maxsize=16)
def _load_prompt_knowledge_cached(path_value: str) -> tuple[KnowledgeEntry, ...]:
    path = Path(path_value)
    if not path.exists():
        return ()
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    entries = payload.get("entries", []) if isinstance(payload, dict) else []
    return tuple(_entry_from_payload(item) for item in entries if isinstance(item, dict))


def _entry_from_payload(item: dict[str, Any]) -> KnowledgeEntry:
    aliases = tuple(str(value).strip() for value in item.get("aliases", []) if str(value).strip())
    tags = tuple(str(value).strip() for value in item.get("tags", []) if str(value).strip())
    return KnowledgeEntry(
        aliases=aliases,
        target=str(item.get("target", "")).strip(),
        franchise=str(item.get("franchise", "")).strip(),
        tags=tags,
        note=str(item.get("note", "")).strip(),
    )


def matched_knowledge_context(prompt: str, path: Path, limit: int = 24) -> str:
    matched: list[KnowledgeEntry] = []
    seen_targets: set[str] = set()
    source = prompt or ""
    active_franchises = _active_franchises(source, path)

    for entry in load_prompt_knowledge(path):
        if not entry.target or entry.target in seen_targets:
            continue
        if _entry_matches(entry, source, active_franchises):
            matched.append(entry)
            seen_targets.add(entry.target)
        if len(matched) >= limit:
            break

    if not matched:
        return ""

    lines = [
        "Local prompt knowledge matched. Use these translations exactly and prefer the listed English tags:",
    ]
    for entry in matched:
        aliases = " / ".join(entry.aliases[:4])
        details = [f"{aliases} => {entry.target}"]
        if entry.franchise:
            details.append(f"franchise: {entry.franchise}")
        if entry.tags:
            details.append(f"tags: {', '.join(entry.tags)}")
        if entry.note:
            details.append(f"note: {entry.note}")
        lines.append(f"- {'; '.join(details)}")
    return "\n".join(lines)


def _active_franchises(source: str, path: Path) -> set[str]:
    franchises: set[str] = set()
    for entry in load_prompt_knowledge(path):
        if entry.franchise and any(alias and alias in source for alias in entry.aliases):
            franchises.add(entry.franchise)
    return franchises


def _entry_matches(entry: KnowledgeEntry, source: str, active_franchises: set[str]) -> bool:
    for alias in entry.aliases:
        if not alias:
            continue
        if len(alias) <= 1:
            if entry.franchise in active_franchises and alias in source:
                return True
            if _short_alias_matches(alias, source):
                return True
            continue
        if alias in source:
            return True
    return False


def _short_alias_matches(alias: str, source: str) -> bool:
    start = 0
    while True:
        index = source.find(alias, start)
        if index < 0:
            return False
        before = source[index - 1] if index > 0 else ""
        after_index = index + len(alias)
        after = source[after_index] if after_index < len(source) else ""
        before_ok = not before or before in SHORT_ALIAS_BOUNDARIES
        after_ok = not after or after in SHORT_ALIAS_BOUNDARIES
        if before_ok and after_ok:
            return True
        start = index + len(alias)
