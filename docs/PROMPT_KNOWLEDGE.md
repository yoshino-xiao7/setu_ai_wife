# Local Prompt Knowledge Base

## Purpose

The local prompt knowledge base gives the prompt translation pipeline reusable style, quality, and LoRA trigger guidance without hard-coding every rule in Python.

## Location

The path is configured by `PROMPT_KNOWLEDGE_PATH` and defaults to:

```text
config/prompt_knowledge.json
```

## Usage

The local service loads the knowledge file during prompt construction. Restart the service after changing the file to guarantee the new content is active.

## Entry Guidance

Keep entries short and model-oriented:

- Trigger words for known LoRAs.
- Style notes that improve local checkpoint output.
- Lighting, skin, and palette recipes such as glossy/wet skin or pastel color locks.
- Negative prompt fragments for common artifacts.
- NSFW visibility guidance when applicable.

Translated prompts should stay as comma-separated Danbooru tags. Do not store English prose in knowledge tags.

Do not put secrets, cloud tokens, or machine-specific absolute paths in this file.
