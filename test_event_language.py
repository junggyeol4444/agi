import unittest

from event_language import EventLanguageMixin


class LanguageHost(EventLanguageMixin):
    def __init__(self):
        self.event_lexicon = {}


class EventLanguageTests(unittest.TestCase):
    def _teach_push(self, host):
        host.observe_utterance_event("ko", ["철수", "공", "민다"],
                                     {"agent": "철수", "object": "공", "action": "push"})
        host.observe_utterance_event("ko", ["영희", "상자", "민다"],
                                     {"agent": "영희", "object": "상자", "action": "push"})
        host.observe_utterance_event("ko", ["아이", "문", "민다"],
                                     {"agent": "아이", "object": "문", "action": "push"})

    def test_cross_situational_learning_discovers_action_symbol(self):
        host = LanguageHost()
        self._teach_push(host)

        meaning = host.event_meaning("ko", "민다")

        self.assertTrue(meaning["grounded"])
        self.assertEqual((meaning["role"], meaning["value"]), ("action", "push"))

    def test_one_sentence_does_not_assign_roles(self):
        host = LanguageHost()
        host.observe_utterance_event("ko", ["철수", "공", "민다"],
                                     {"agent": "철수", "object": "공", "action": "push"})

        self.assertFalse(host.event_meaning("ko", "민다")["grounded"])

    def test_understanding_uses_only_learned_event_meaning(self):
        host = LanguageHost()
        self._teach_push(host)

        understood = host.understand_event_utterance("ko", ["누군가", "무언가", "민다"])

        self.assertEqual(understood["event"], {"action": "push"})
        self.assertIn("누군가", understood["unresolved_tokens"])

    def test_expression_refuses_to_invent_unknown_symbol(self):
        host = LanguageHost()
        self._teach_push(host)

        result = host.express_event("ko", {"action": "pull"})

        self.assertFalse(result["expressed"])
        self.assertEqual(result["tokens"], [])


if __name__ == "__main__":
    unittest.main()
