import unittest

from event_language import EventLanguageMixin
from grammar_induction import GrammarInductionMixin


class GrammarHost(EventLanguageMixin, GrammarInductionMixin):
    def __init__(self):
        self.event_lexicon = {}
        self.grammar_memory = {}


class GrammarInductionTests(unittest.TestCase):
    def _teach_lexicon(self, host):
        words = {"alice": "alice", "bob": "bob", "ball": "ball", "box": "box",
                 "pushes": "push", "pulls": "pull"}
        for agent in ("alice", "bob"):
            for obj in ("ball", "box"):
                for verb in ("pushes", "pulls"):
                    host.observe_utterance_event(
                        "en", [agent, verb, obj],
                        {"agent": words[agent], "action": words[verb], "object": words[obj]})

    def test_role_order_is_learned_from_grounded_tokens(self):
        host = GrammarHost()
        self._teach_lexicon(host)
        for _ in range(3):
            host.observe_grounded_utterance("en", ["alice", "pushes", "ball"])

        grammar = host.learned_role_order("en")

        self.assertTrue(grammar["grounded"])
        self.assertEqual(grammar["roles"], ["agent", "action", "object"])

    def test_unresolved_tokens_do_not_train_syntax(self):
        host = GrammarHost()

        result = host.observe_grounded_utterance("en", ["unknown", "moves"])

        self.assertFalse(result["learned"])
        self.assertEqual(host.grammar_memory, {})

    def test_composition_uses_learned_order_not_input_dictionary_order(self):
        host = GrammarHost()
        self._teach_lexicon(host)
        for _ in range(3):
            host.observe_grounded_utterance("en", ["alice", "pushes", "ball"])

        result = host.compose_event_utterance(
            "en", {"object": "ball", "action": "push", "agent": "alice"})

        self.assertEqual(result["tokens"], ["alice", "pushes", "ball"])

    def test_composition_refuses_role_shape_never_learned(self):
        host = GrammarHost()
        self._teach_lexicon(host)
        for _ in range(3):
            host.observe_grounded_utterance("en", ["alice", "pushes", "ball"])

        result = host.compose_event_utterance("en", {"action": "push"})

        self.assertFalse(result["expressed"])


if __name__ == "__main__":
    unittest.main()
