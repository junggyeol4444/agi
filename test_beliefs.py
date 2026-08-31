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

    def test_different_urls_from_same_publisher_are_one_evidence_group(self):
        self.b.observe_belief("펭귄", "is_a", "조류",
                              source="https://news.example/a")
        self.b.observe_belief("펭귄", "is_a", "조류",
                              source="https://www.news.example/copied")

        claim = self.b.belief_about("펭귄")[0]

        self.assertEqual(claim["support"], 1.0)
        self.assertEqual(claim["support_groups"], ["publisher:news.example"])
        self.assertFalse(self.b.verify_belief("펭귄")["verified"])

    def test_explicit_independence_group_deduplicates_syndicated_sources(self):
        for source in ("신문-A", "포털에 복제된 신문-A 기사"):
            self.b.observe_belief("펭귄", "is_a", "조류", source=source,
                                  independence_group="wire-story-42")

        claim = self.b.belief_about("펭귄")[0]

        self.assertEqual(claim["support"], 1.0)
        self.assertEqual(len(claim["support_sources"]), 2)
        self.assertEqual(claim["support_groups"], ["wire-story-42"])

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
        self.assertEqual(answer["correction"]["subject"], "펭귄")
        self.assertFalse(answer["correction"]["delivered"])

    def test_next_response_admits_a_pending_correction_once(self):
        self.b.isa["펭귄"] = "어류"
        self.b._record_answer("펭귄은 뭐야?", {"say": "펭귄은 어류야."})
        for source in ("관찰-A", "관찰-B"):
            self.b.learn_isa("펭귄", "펭귄은 조류이다.", source=source)
        self.b.verify_belief("펭귄")

        first = self.b.respond("안녕")
        self.assertIn("정정할게", first["say"])
        self.assertIn("어류", first["say"])
        self.assertIn("조류", first["say"])
        self.assertEqual(len(first["corrections"]), 1)
        self.assertEqual(self.b.pending_corrections(), [])

        second = self.b.respond("안녕")
        self.assertNotIn("정정할게", second["say"])

    def test_duplicate_invalidated_answers_make_one_pending_correction(self):
        self.b.isa["펭귄"] = "어류"
        for question in ("펭귄은 뭐야?", "펭귄 종류는?"):
            self.b._record_answer(question, {"say": "펭귄은 어류야."})
        for source in ("관찰-A", "관찰-B"):
            self.b.learn_isa("펭귄", "펭귄은 조류이다.", source=source)
        self.b.verify_belief("펭귄")
        self.assertEqual(len(self.b.pending_corrections()), 1)

    def test_counterevidence_suspends_an_accepted_belief(self):
        for source in ("관찰-A", "관찰-B"):
            self.b.observe_belief("백조", "is_a", "흰새", source=source)
        self.assertTrue(self.b.verify_belief("백조")["verified"])
        self.b._record_answer("백조는 뭐야?", {"say": "백조는 흰새야."})

        for source in ("검증-A", "검증-B"):
            self.b.observe_belief("백조", "is_a", "흰새", source=source,
                                  supports=False)
        result = self.b.verify_belief("백조")

        self.assertFalse(result["verified"])
        self.assertTrue(result["suspended"])
        self.assertNotIn("백조", self.b.isa)
        self.assertIsNone(self.b.belief_revisions[-1]["to"])
        correction = self.b.pending_corrections("백조")[0]
        self.assertIsNone(correction["replacement"])

    def test_suspended_belief_is_admitted_as_uncertain(self):
        self.b.isa["백조"] = "흰새"
        self.b._record_answer("백조는 뭐야?", {"say": "백조는 흰새야."})
        for source in ("검증-A", "검증-B"):
            self.b.observe_belief("백조", "is_a", "흰새", source=source,
                                  supports=False)
        self.b.verify_belief("백조")

        response = self.b.respond("안녕")
        self.assertIn("그 결론을 취소하고 판단을 보류했어", response["say"])

    def test_equally_supported_conflict_removes_old_answer_from_reasoning(self):
        self.b.isa["박쥐"] = "조류"
        for source in ("새-A", "새-B"):
            self.b.observe_belief("박쥐", "is_a", "조류", source=source)
        for source in ("포유-A", "포유-B"):
            self.b.observe_belief("박쥐", "is_a", "포유류", source=source)

        result = self.b.verify_belief("박쥐")

        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "근거가 맞서 결론 보류")
        self.assertNotIn("박쥐", self.b.isa)
        self.assertEqual(self.b.belief_revisions[-1]["status"], "suspended")

    def test_deliberation_turns_uncertainty_into_verification_plan(self):
        self.b.observe_belief("박쥐", "is_a", "조류", source="한사람")

        thought = self.b.deliberate("박쥐")

        plan = thought["verification_plan"]
        self.assertEqual(thought["action"], "withhold")
        self.assertEqual(plan["status"], "open")
        self.assertEqual(plan["hypotheses"][0]["claim"], "조류")
        self.assertGreater(plan["hypotheses"][0]["need"], 0)
        self.assertTrue(any("반례" in action for action in plan["next_actions"]))

    def test_verification_task_tracks_new_evidence_and_resolution(self):
        self.b.make_verification_plan("펭귄")
        self.b.observe_belief("펭귄", "is_a", "조류", source="관찰-A")
        task = self.b.verification_tasks[self.b._verification_key("펭귄", "is_a")]
        self.assertEqual(task["evidence_seen"], 1)

        self.b.observe_belief("펭귄", "is_a", "조류", source="관찰-B")
        result = self.b.verify_belief("펭귄")

        self.assertTrue(result["verified"])
        self.assertEqual(task["status"], "resolved")
        self.assertEqual(task["conclusion"], "조류")

    def test_belief_and_revision_survive_save_load(self):
        self.b.isa["펭귄"] = "어류"
        self.b.make_verification_plan("펭귄")
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
        task = restored.verification_tasks[restored._verification_key("펭귄", "is_a")]
        self.assertEqual(task["status"], "resolved")


if __name__ == "__main__":
    unittest.main()
