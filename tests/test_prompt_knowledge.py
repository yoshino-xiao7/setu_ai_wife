from pathlib import Path
from unittest import TestCase

from app.prompt_knowledge import knowledge_positive_tags, matched_knowledge_entries


KNOWLEDGE = Path(__file__).resolve().parents[1] / "config" / "prompt_knowledge.json"


class PromptKnowledgeTests(TestCase):
    def test_lighting_ying_does_not_match_raiden_ei(self) -> None:
        prompt = "边缘逆光，强烈阳光带来的明暗对比与光影，水面反光与光斑"
        tags = knowledge_positive_tags(prompt, KNOWLEDGE)
        names = [entry.target for entry in matched_knowledge_entries(prompt, KNOWLEDGE)]
        self.assertNotIn("Raiden Ei", names)
        self.assertNotIn("Raiden Shogun", names)
        self.assertNotIn("raiden", tags.lower())

    def test_explicit_raiden_aliases_still_match(self) -> None:
        for prompt in ("雷电影", "雷电将军", "影宝"):
            names = [entry.target for entry in matched_knowledge_entries(prompt, KNOWLEDGE)]
            self.assertTrue(
                "Raiden Ei" in names or "Raiden Shogun" in names,
                msg=prompt,
            )

    def test_standalone_ying_still_matches_raiden_ei(self) -> None:
        names = [entry.target for entry in matched_knowledge_entries("影", KNOWLEDGE)]
        self.assertIn("Raiden Ei", names)

    def test_genshin_plus_lighting_does_not_unlock_ying(self) -> None:
        prompt = "原神同人，泳池边，边缘逆光和光影"
        names = [entry.target for entry in matched_knowledge_entries(prompt, KNOWLEDGE)]
        self.assertIn("Genshin Impact", names)
        self.assertNotIn("Raiden Ei", names)
