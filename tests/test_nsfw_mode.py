from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.main import build_positive_prompt
from app.prompting import (
    apply_nsfw_visibility_negative,
    apply_nsfw_visibility_negative_profile,
    apply_nsfw_visibility_positive,
    apply_nsfw_visibility_profile,
    filter_character_identity_tags,
    filter_nsfw_incompatible_tags,
    remove_cjk_tags,
)


class NsfwModeTest(unittest.TestCase):
    def test_character_identity_filter_keeps_face_and_drops_outfit(self) -> None:
        self.assertEqual(
            filter_character_identity_tags(
                "yae miko, fox ears, pink hair, large breasts, thighs, "
                "japanese clothes, nontraditional miko, anime style, detailed eyes"
            ),
            "yae miko, fox ears, pink hair",
        )

    def test_filters_clothing_tags_without_removing_identity_tags(self) -> None:
        prompt = (
            "1girl, purple eyes, purple kimono, detached sleeves, "
            "mole under eye, black pantyhose, cinematic lighting"
        )

        self.assertEqual(
            filter_nsfw_incompatible_tags(prompt),
            "1girl, purple eyes, mole under eye, cinematic lighting",
        )

    def test_filter_is_case_and_separator_insensitive(self) -> None:
        self.assertEqual(
            filter_nsfw_incompatible_tags("Pink Hair, JAPANESE_CLOTHES, White Gloves"),
            "Pink Hair",
        )

    def test_filters_colored_and_synonym_clothing_tags(self) -> None:
        self.assertEqual(
            filter_nsfw_incompatible_tags(
                "adult woman, (red dress:1.2), cropped jacket, thighhighs, detailed eyes, bedroom"
            ),
            "adult woman, detailed eyes, bedroom",
        )

    def test_removes_only_tags_that_still_contain_chinese(self) -> None:
        self.assertEqual(
            remove_cjk_tags("adult woman, 银发, rainy night, 霓虹灯, cinematic lighting"),
            "adult woman, rainy night, cinematic lighting",
        )

    def test_removes_miko_clothing_tag_but_keeps_yae_miko_identity(self) -> None:
        self.assertEqual(
            filter_nsfw_incompatible_tags(
                "yae miko, genshin impact, fox ears, nontraditional miko, purple eyes"
            ),
            "yae miko, genshin impact, fox ears, purple eyes",
        )

    def test_filters_censorship_occlusion_and_cropping_tags(self) -> None:
        self.assertEqual(
            filter_nsfw_incompatible_tags(
                "yae miko, convenient censoring, hands covering body, "
                "(mosaic censorship:1.2), cropped body, moonlight"
            ),
            "yae miko, moonlight",
        )

    def test_preserves_requested_anatomy_visibility_tags(self) -> None:
        self.assertEqual(
            filter_nsfw_incompatible_tags(
                "yae miko, cutaway view, x-ray view, internal anatomy, purple kimono"
            ),
            "yae miko, cutaway view, x-ray view, internal anatomy",
        )

    def test_does_not_add_positive_visibility_or_anatomy_tags_by_default(self) -> None:
        positive = apply_nsfw_visibility_positive("yae miko, moonlight")
        negative = apply_nsfw_visibility_negative("low quality")

        self.assertEqual(positive, "yae miko, moonlight")
        self.assertNotIn("anatomy", positive)
        self.assertNotIn("clear view", positive)
        self.assertNotIn("front-facing pose", positive)
        self.assertNotIn("adult", positive)
        self.assertIn("convenient censoring", negative)
        self.assertIn("foreground obstruction", negative)

    def test_visibility_profiles_preserve_close_up_and_only_expand_full_body_when_requested(self) -> None:
        close_up = apply_nsfw_visibility_profile("yae miko, close-up portrait", "STRONG")
        full_body = apply_nsfw_visibility_profile("yae miko, full body", "STRONG")

        self.assertNotIn("head-to-toe framing", close_up)
        self.assertIn("head-to-toe framing", full_body)
        self.assertIn("(uncensored adult nude body:1.2)", close_up)
        self.assertIn("explicit nude anatomy visible", close_up)
        self.assertIn("front-facing pose", close_up)
        self.assertIn("clothing coverage", apply_nsfw_visibility_negative_profile("low quality", "STRONG"))
        self.assertIn(
            "(censored:1.3)",
            apply_nsfw_visibility_negative_profile("low quality", "STRONG"),
        )

    def test_changing_visibility_level_replaces_old_profile_tags(self) -> None:
        light = apply_nsfw_visibility_profile(
            "yae miko, unobstructed anatomy, explicit anatomy visible, clear frontal view",
            "LIGHT",
        )

        self.assertEqual(light, "yae miko")
        self.assertNotIn("unobstructed anatomy", light)
        self.assertNotIn("explicit anatomy visible", light)
        self.assertNotIn("clear frontal view", light)

    def test_nsfw_generation_filters_character_preset_only(self) -> None:
        payload = SimpleNamespace(
            nsfw_mode=True,
            trigger_words="user dress tag",
            style_tags="preset dress tag, cinematic lighting",
        )
        character = SimpleNamespace(
            trigger_words="yae miko",
            default_positive="purple kimono, detached sleeves, purple eyes",
            style_tags="anime style",
        )

        positive = build_positive_prompt(
            payload,
            "translated dress tag, rainy night",
            character,
            None,
            False,
        )

        self.assertIn("yae miko", positive)
        self.assertIn("purple eyes", positive)
        self.assertNotIn("purple kimono", positive)
        self.assertNotIn("detached sleeves", positive)
        self.assertIn("user dress tag", positive)
        self.assertIn("preset dress tag", positive)
        self.assertIn("translated dress tag", positive)

    def test_nsfw_generation_filters_character_preset_when_positive_is_provided(self) -> None:
        payload = SimpleNamespace(
            nsfw_mode=True,
            trigger_words="",
            style_tags="",
        )
        character = SimpleNamespace(
            trigger_words="yae miko",
            default_positive="purple kimono, detached sleeves, purple eyes",
            style_tags="",
        )

        positive = build_positive_prompt(
            payload,
            "provided positive prompt, red dress requested by user",
            character,
            None,
            False,
        )

        self.assertIn("yae miko", positive)
        self.assertIn("purple eyes", positive)
        self.assertNotIn("purple kimono", positive)
        self.assertNotIn("detached sleeves", positive)
        self.assertIn("red dress requested by user", positive)


if __name__ == "__main__":
    unittest.main()
