from __future__ import annotations

import unittest

from app.main import filter_nsfw_incompatible_tags


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


if __name__ == "__main__":
    unittest.main()
