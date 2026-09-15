from __future__ import annotations

import unittest

from app.comfyui import (
    CLASSIC_LIGHT_HIRES_CFG,
    CLASSIC_LIGHT_HIRES_CLIP_SKIP,
    CLASSIC_LIGHT_HIRES_DENOISE,
    CLASSIC_LIGHT_HIRES_SAMPLER,
    CLASSIC_LIGHT_HIRES_SCALE,
    CLASSIC_LIGHT_HIRES_STEPS,
    build_workflow,
    classic_hires_scale_for_size,
    resolve_classic_sampling,
)


class ClassicLightHiresTest(unittest.TestCase):
    def test_default_sampling_keeps_euler_and_skips_hires(self) -> None:
        sampling = resolve_classic_sampling(
            light_hires=False,
            cfg=4.5,
            default_sampler="euler",
            default_scheduler="normal",
            width=832,
            height=1216,
        )
        self.assertEqual(sampling["sampler"], "euler")
        self.assertEqual(sampling["cfg"], 4.5)
        self.assertEqual(sampling["clip_skip"], 0)
        self.assertEqual(sampling["hires_scale"], 1.0)

    def test_light_hires_sampling_uses_euler_a_and_cfg_55(self) -> None:
        sampling = resolve_classic_sampling(
            light_hires=True,
            cfg=4.5,
            default_sampler="euler",
            default_scheduler="normal",
            width=832,
            height=1216,
        )
        self.assertEqual(sampling["sampler"], CLASSIC_LIGHT_HIRES_SAMPLER)
        self.assertEqual(sampling["cfg"], CLASSIC_LIGHT_HIRES_CFG)
        self.assertEqual(sampling["clip_skip"], CLASSIC_LIGHT_HIRES_CLIP_SKIP)
        self.assertEqual(sampling["hires_scale"], CLASSIC_LIGHT_HIRES_SCALE)

    def test_light_hires_keeps_custom_cfg(self) -> None:
        sampling = resolve_classic_sampling(
            light_hires=True,
            cfg=7,
            default_sampler="euler",
            default_scheduler="normal",
            width=832,
            height=1216,
        )
        self.assertEqual(sampling["cfg"], 7)

    def test_tall_canvas_caps_hires_scale(self) -> None:
        scale = classic_hires_scale_for_size(832, 1472)
        self.assertLess(scale, CLASSIC_LIGHT_HIRES_SCALE)
        self.assertGreater(scale, 1.0)
        self.assertLessEqual(1472 * scale, 1600)

    def test_workflow_adds_clip_skip_and_second_pass(self) -> None:
        workflow = build_workflow(
            positive="1girl, solo",
            negative="low quality",
            seed=20260915,
            width=832,
            height=1216,
            steps=28,
            cfg=5.5,
            checkpoint="waiIllustriousSDXL_v170.safetensors",
            sampler="euler_ancestral",
            scheduler="normal",
            clip_skip=-2,
            hires_scale=1.25,
            hires_steps=CLASSIC_LIGHT_HIRES_STEPS,
            hires_denoise=CLASSIC_LIGHT_HIRES_DENOISE,
        )
        self.assertEqual(workflow["18"]["class_type"], "CLIPSetLastLayer")
        self.assertEqual(workflow["18"]["inputs"]["stop_at_clip_layer"], -2)
        self.assertEqual(workflow["6"]["inputs"]["clip"], ["18", 0])
        self.assertEqual(workflow["3"]["inputs"]["sampler_name"], "euler_ancestral")
        self.assertEqual(workflow["19"]["class_type"], "LatentUpscaleBy")
        self.assertEqual(workflow["19"]["inputs"]["scale_by"], 1.25)
        self.assertEqual(workflow["20"]["inputs"]["denoise"], 0.4)
        self.assertEqual(workflow["20"]["inputs"]["steps"], 16)
        self.assertEqual(workflow["8"]["inputs"]["samples"], ["20", 0])

    def test_workflow_without_hires_keeps_single_sampler(self) -> None:
        workflow = build_workflow(
            positive="1girl, solo",
            negative="low quality",
            seed=1,
            width=832,
            height=1216,
            steps=28,
            cfg=4.5,
            checkpoint="waiIllustriousSDXL_v170.safetensors",
            sampler="euler",
            scheduler="normal",
        )
        self.assertNotIn("18", workflow)
        self.assertNotIn("19", workflow)
        self.assertNotIn("20", workflow)
        self.assertEqual(workflow["8"]["inputs"]["samples"], ["3", 0])
        self.assertEqual(workflow["3"]["inputs"]["sampler_name"], "euler")
