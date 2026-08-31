import tempfile
import unittest
from unittest import mock

import baby


class BeliefLearningTests(unittest.TestCase):
    def setUp(self):
        self.b = baby.Baby()

    def test_one_source_does_not_verify_a_claim(self):
        self.b.learn_isa("펭귄", "펭귄은 어류이다.", source="한사람")
        result = self.b.verify_belief("펭귄")
        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "독립 근거 부족")

    def test_repetition_from_same_source_is_not_independent_evidence(self):
        for _ in range(5):
            self.b.learn_isa("펭귄", "펭귄은 조류이다.", source="복제된글")
        claim = self.b.belief_about("펭귄")[0]
        self.assertEqual(claim["support"], 1.0)
        self.assertFalse(self.b.verify_belief("펭귄")["verified"])

    def test_unverified_statement_is_not_available_for_reasoning(self):
        self.b.learn_isa("펭귄", "펭귄은 조류이다.", source="한사람")
        self.assertNotIn("펭귄", self.b.isa)
        thought = self.b.deliberate("펭귄")
        self.assertEqual(thought["action"], "withhold")
        self.assertIsNone(thought["conclusion"])

    def test_revision_records_what_changed_and_why(self):
        self.b.isa["펭귄"] = "어류"
        self.b.learn_isa("펭귄", "펭귄은 조류이다.", source="관찰-A")
        self.b.learn_isa("펭귄", "펭귄은 조류이다.", source="관찰-B")
        result = self.b.verify_belief("펭귄")
        self.assertTrue(result["verified"])
        self.assertTrue(result["changed"])
        self.assertEqual(self.b.isa["펭귄"], "조류")
        self.assertEqual(self.b.belief_revisions[-1]["from"], "어류")
        self.assertEqual(self.b.belief_revisions[-1]["to"], "조류")
        accepted = [x for x in self.b.belief_about("펭귄") if x["object"] == "조류"][0]
        self.assertEqual(accepted["status"], "accepted")

    def test_conflicting_candidates_are_withheld(self):
        for source in ("새-A", "새-B"):
            self.b.learn_isa("박쥐", "박쥐는 조류이다.", source=source)
        for source in ("포유-A", "포유-B"):
            self.b.learn_isa("박쥐", "박쥐는 포유류이다.", source=source)
        result = self.b.verify_belief("박쥐")
        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "근거가 맞서 결론 보류")
        self.assertEqual(self.b.deliberate("박쥐")["action"], "verify")

    def test_direct_experiments_can_be_independent_evidence(self):
        for n in range(2):
            self.b.observe_belief("얼음", "is_a", "고체", source="직접실험",
                                  kind="experiment", evidence_id=f"실험-{n}")
        result = self.b.verify_belief("얼음")
        self.assertTrue(result["verified"])
        self.assertEqual(result["conclusion"], "고체")

    def test_revision_marks_past_answer_for_correction(self):
        self.b.isa["펭귄"] = "어류"
        self.b._record_answer("펭귄은 뭐야?", {"say": "펭귄은 어류야."})
        for source in ("관찰-A", "관찰-B"):
            self.b.learn_isa("펭귄", "펭귄은 조류이다.", source=source)
        self.b.verify_belief("펭귄")
        answer = self.b.answer_history[-1]
        self.assertTrue(answer["invalidated"])
        self.assertEqual(answer["correction"]["replacement"], "조류")

    def test_belief_and_revision_survive_save_load(self):
        self.b.isa["펭귄"] = "어류"
        for source in ("관찰-A", "관찰-B"):
            self.b.learn_isa("펭귄", "펭귄은 조류이다.", source=source)
        self.b.verify_belief("펭귄")
        with tempfile.TemporaryDirectory() as td:
            path = f"{td}/memory.json"
            with mock.patch.object(baby, "MEMORY_FILE", path):
                self.b.save()
                restored = baby.Baby()
                self.assertTrue(restored.load())
        self.assertEqual(restored.isa["펭귄"], "조류")
        self.assertEqual(restored.belief_revisions[-1]["from"], "어류")


if __name__ == "__main__":
    unittest.main()
