import unittest

from answer_audit import AnswerAuditMixin


class AuditHost(AnswerAuditMixin):
    def __init__(self):
        self.isa = {"펭귄": "어류"}
        self.answer_history = []
        self.lived = 10

    def _belief_key(self, subject, relation, obj):
        return f"{subject}|{relation}|{obj}"

    def _j(self, word, with_batchim, without_batchim):
        return f"{word}{with_batchim}"


class StandaloneAnswerAuditTests(unittest.TestCase):
    def test_invalidated_answer_becomes_one_pending_correction(self):
        host = AuditHost()
        host._record_answer("펭귄은 뭐야?", {"say": "펭귄은 어류야."})

        host._invalidate_answers(
            host._belief_key("펭귄", "is_a", "어류"), "조류",
            revision={"subject": "펭귄", "relation": "is_a", "from": "어류"},
        )

        corrections = host.pending_corrections()
        self.assertEqual(len(corrections), 1)
        self.assertEqual(corrections[0]["replacement"], "조류")

    def test_attached_correction_is_marked_delivered(self):
        host = AuditHost()
        host._record_answer("펭귄은 뭐야?", {"say": "펭귄은 어류야."})
        host._invalidate_answers(
            host._belief_key("펭귄", "is_a", "어류"), "조류",
            revision={"subject": "펭귄", "relation": "is_a", "from": "어류"},
        )

        result = host._attach_pending_corrections("안녕", {"say": "안녕."})

        self.assertIn("정정할게", result["say"])
        self.assertEqual(host.pending_corrections(), [])

    def test_explicit_provenance_avoids_text_guessing(self):
        host = AuditHost()
        exact = host._belief_key("다른대상", "is_a", "다른분류")

        host._record_answer(
            "펭귄 이야기가 포함된 질문",
            {"say": "펭귄이라는 단어만 언급", "beliefs_used": [exact]},
        )

        self.assertEqual(host.answer_history[-1]["beliefs_used"], [exact])


if __name__ == "__main__":
    unittest.main()
