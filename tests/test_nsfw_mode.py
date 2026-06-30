from __future__ import annotations

import unittest

from app.prompting import (
    apply_nsfw_visibility_negative,
    apply_nsfw_visibility_negative_profile,
    apply_nsfw_visibility_positive,
    apply_nsfw_visibility_profile,
    filter_nsfw_incompatible_tags,
    remove_cjk_tags,
)


class NsfwModeTest(unittest.TestCase):
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

    def test_adds_visibility_conditions_without_adult_age_tag(self) -> None:
        positive = apply_nsfw_visibility_positive("yae miko, moonlight")
        negative = apply_nsfw_visibility_negative("low quality")

        self.assertIn("unobstructed anatomy", positive)
        self.assertIn("explicit anatomy visible", positive)
        self.assertNotIn("adult", positive)
        self.assertIn("convenient censoring", negative)
        self.assertIn("foreground obstruction", negative)

    def test_visibility_profiles_preserve_close_up_and_only_expand_full_body_when_requested(self) -> None:
        close_up = apply_nsfw_visibility_profile("yae miko, close-up portrait", "STRONG")
        full_body = apply_nsfw_visibility_profile("yae miko, full body", "STRONG")

        self.assertNotIn("head-to-toe framing", close_up)
        self.assertIn("head-to-toe framing", full_body)
        self.assertIn("(unobstructed anatomy:1.25)", close_up)
        self.assertIn(
            "(censored:1.3)",
            apply_nsfw_visibility_negative_profile("low quality", "STRONG"),
        )

    def test_changing_visibility_level_replaces_old_profile_tags(self) -> None:
        light = apply_nsfw_visibility_profile(
            "yae miko, unobstructed anatomy, explicit anatomy visible, clear frontal view",
            "LIGHT",
        )

        self.assertIn("clear view", light)
        self.assertNotIn("explicit anatomy visible", light)


if __name__ == "__main__":
    unittest.main()
