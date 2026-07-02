# Dual-Character Generation

## Current Strategy

Dual-character generation supports two character/LoRA selections, separate strengths, optional painted character regions, and prompt hints that describe left/right or region-specific placement.

`DUAL_CHARACTER_STRATEGY` controls behavior:

- `auto`: default single-pass dual generation; painted regions become layout hints.
- `mask-conditioning`: use A/B masks as prompt-conditioning regions in one sampling pass.
- `inpaint`: legacy experimental mode that composes first and repaints masked regions.

## Why Separation Is Imperfect

Two LoRAs in one diffusion pass can bleed identity, clothing, or style across subjects. Region prompts and masks reduce the issue but do not fully isolate character identity.

## Writing Interaction Prompts

Write the scene as one coherent interaction, then use character A/B notes for identity, outfit, and placement. Avoid contradictory placement language between the global prompt and region hints.

## Tunables

- `DUAL_LORA_STRENGTH_CAP`
- `DUAL_MASK_CONDITIONING_STRENGTH`
- `DUAL_INPAINT_DENOISE`
- `DUAL_INPAINT_MASK_OVERLAP_RATIO`

Use lower LoRA strengths when faces or outfits bleed between characters.

## Future Direction

More reliable isolation may require dedicated regional conditioning, stronger mask-aware workflows, or separate passes with compositing and repair.
