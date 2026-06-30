from __future__ import annotations

import unittest

from app.prompting import (
    apply_nsfw_visibility_negative,
    apply_nsfw_visibility_positive,
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

    def test_adds_visibility_conditions_without_adult_age_tag(self) -> None:
        positive = apply_nsfw_visibility_positive("yae miko, moonlight")
        negative = apply_nsfw_visibility_negative("low quality")

        self.assertIn("unobstructed anatomy", positive)
        self.assertIn("explicit anatomy visible", positive)
        self.assertNotIn("adult", positive)
        self.assertIn("convenient censoring", negative)
        self.assertIn("foreground obstruction", negative)


if __name__ == "__main__":
    unittest.main()
