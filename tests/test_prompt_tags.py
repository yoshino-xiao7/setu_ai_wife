from __future__ import annotations

import unittest

from app.prompt_tags import (
    QUALITY_NEGATIVE,
    compose_stacked_negative,
    compose_stacked_prompt,
    rewrite_negative_tags,
    rewrite_positive_tags,
    rewrite_preset_fields,
    rewrite_style_tags,
)


class PromptTagRewriteTest(unittest.TestCase):
    def test_converts_prose_sitting_preset_into_short_tags(self) -> None:
        positive = rewrite_positive_tags(
            "beautiful girl sitting elegantly on a chair or bench, graceful posture, "
            "soft smile, legs together modestly, clean modest clothing, "
            "excellent composition and lighting, refined atmosphere"
        )
        self.assertIn("light smile", positive)
        self.assertIn("closed mouth", positive)
        self.assertIn("legs together", positive)
        self.assertNotIn("beautiful girl", positive)
        self.assertNotIn("composition", positive)

    def test_keeps_looking_back_and_from_behind_tags(self) -> None:
        self.assertEqual(
            rewrite_positive_tags("1girl, solo, looking back over shoulder"),
            "1girl, solo, looking back over shoulder",
        )
        self.assertEqual(
            rewrite_positive_tags("1girl, solo, from behind, back view, elegant pose"),
            "1girl, solo, from behind, back view, elegant pose",
        )

    def test_locks_expression_without_banning_over_shoulder_gaze(self) -> None:
        negative = rewrite_negative_tags(
            "lowres, bad anatomy, blurry, explicit, full front view, stiff neck",
            "1girl, solo, looking back over shoulder, closed mouth, calm expression",
        )
        self.assertIn("open mouth", negative)
        self.assertIn("winking", negative)
        self.assertNotIn("looking at viewer", negative)
        self.assertIn("bad hands", negative)

    def test_looking_down_presets_still_ban_eye_contact(self) -> None:
        negative = rewrite_negative_tags(
            "looking at viewer, eye contact, head up, facing camera",
            "looking down, head lowered, gaze down, closed mouth",
        )
        self.assertIn("looking at viewer", negative)
        self.assertIn(QUALITY_NEGATIVE.split(",")[0], negative)

    def test_scene_and_composition_layers_drop_leftover_clothes_and_forced_faces(self) -> None:
        from app.prompt_tags import sanitize_preset_layer

        portrait = sanitize_preset_layer(
            {
                "id": "sfw_cinematic_lighting",
                "category": "SFW",
                "category_type": "构图",
                "trigger_words": "1girl, solo, cinematic lighting",
                "default_positive": "beautiful lighting, modest outfit, closed mouth",
            }
        )
        self.assertNotIn("outfit", portrait["default_positive"])
        self.assertNotIn("closed mouth", portrait["default_positive"])
        self.assertIn("cinematic lighting", portrait["trigger_words"])

        reading = sanitize_preset_layer(
            {
                "id": "sfw_study_reading",
                "category": "SFW",
                "category_type": "场景",
                "trigger_words": "study room, library",
                "default_positive": "soft lamp light, calm expression, closed mouth, casual",
            }
        )
        self.assertNotIn("closed mouth", reading["default_positive"])
        self.assertNotIn("calm expression", reading["default_positive"])
        self.assertIn("study room", reading["trigger_words"])

    def test_flower_field_does_not_replace_bikini(self) -> None:
        from app.prompt_tags import sanitize_preset_layer

        scene = sanitize_preset_layer(
            {
                "id": "sfw_flower_field",
                "category": "SFW",
                "category_type": "场景",
                "trigger_words": "1girl, solo, flower field, sunlight, outdoors",
                "default_positive": "standing, wide flower field, breeze in hair, sundress, peaceful smile",
            }
        )
        self.assertIn("flower field", scene["trigger_words"])
        self.assertNotIn("sundress", scene["default_positive"])
        self.assertNotIn("dress", scene["default_positive"])

        swimsuit = sanitize_preset_layer(
            {
                "id": "sfw_cute_bikini",
                "category": "SFW",
                "category_type": "泳装",
                "trigger_words": "bikini, frilled bikini, beach, ocean",
                "default_positive": "frills, beach setting, happy expression",
            }
        )
        self.assertIn("bikini", swimsuit["trigger_words"])
        self.assertNotIn("beach", swimsuit["trigger_words"])
        self.assertNotIn("ocean", swimsuit["trigger_words"])
        self.assertNotIn("beach setting", swimsuit["default_positive"])

        composed = compose_stacked_prompt(
            "yae miko, fox ears, flower field, sunlight, sundress, peaceful smile, "
            "bikini, frilled bikini, two-piece swimsuit, frills"
        )
        self.assertIn("bikini", composed)
        self.assertIn("frilled bikini", composed)
        self.assertIn("flower field", composed)
        self.assertNotIn("sundress", composed)

    def test_try_on_bikini_in_mirror_composes_one_scene(self) -> None:
        composed = compose_stacked_prompt(
            "yae miko, fox ears, "
            "mirror, standing, nude, standing in front of mirror nude, "
            "looking at reflection with calm expression, closed mouth, "
            "trying on clothes, half undressed, different clothes, currently half undressed, "
            "bikini, two piece swimsuit, in adorable bikini, frills, beach setting, "
            "playful pose, happy expression, coverage"
        )
        self.assertIn("trying on bikini", composed)
        self.assertIn("putting on bikini", composed)
        self.assertIn("matching reflection", composed)
        self.assertIn("same pose in reflection", composed)
        self.assertIn("bikini", composed)
        self.assertNotIn("nude", composed)
        self.assertNotIn("different clothes", composed)
        self.assertNotIn("beach setting", composed)
        self.assertNotIn("closed mouth", composed)
        self.assertNotIn("coverage", composed)
        negative = compose_stacked_negative(
            "clothed, fully clothed, smiling, open mouth, grin",
            composed,
        )
        self.assertNotIn("clothed", negative)
        self.assertNotIn("smiling", negative)

    def test_style_tags_keep_lighting_and_add_highres(self) -> None:
        self.assertEqual(
            rewrite_style_tags("masterpiece, best quality, soft lighting, detailed eyes"),
            "masterpiece, best quality, highres, soft lighting, detailed eyes",
        )

    def test_rewrite_preset_fields_deduplicates_layers(self) -> None:
        rewritten = rewrite_preset_fields(
            {
                "id": "sfw_over_shoulder",
                "trigger_words": "1girl, solo, looking back over shoulder",
                "style_tags": "masterpiece, best quality, detailed eyes",
                "default_positive": (
                    "girl looking back over her shoulder, gentle or playful expression, "
                    "body slightly turned, hair flowing, modest clothing"
                ),
                "default_negative": "lowres, bad anatomy, blurry, explicit, full front view",
            }
        )
        self.assertEqual(rewritten["trigger_words"], "1girl, solo, looking back over shoulder")
        self.assertIn("closed mouth", rewritten["default_positive"])
        self.assertNotIn("looking back over shoulder", rewritten["default_positive"])
        self.assertIn("highres", rewritten["style_tags"])
        self.assertNotIn("looking at viewer", rewritten["default_negative"])


if __name__ == "__main__":
    unittest.main()
