import unittest

from intention_model import IntentionModelMixin


class IntentionHost(IntentionModelMixin):
    def __init__(self):
        self.intention_models = {}
        self.stated_intentions = []
        self.lived = 1


class IntentionModelTests(unittest.TestCase):
    def test_repeated_achieved_state_becomes_goal_hypothesis(self):
        host = IntentionHost()
        host.observe_agent_action("alice", "switch", {"lamp": "off"}, {"lamp": "on"})
        host.observe_agent_action("alice", "repair", {"lamp": "broken"}, {"lamp": "on"})
        result = host.observe_agent_action(
            "alice", "replace", {"lamp": "missing"}, {"lamp": "on"})

        self.assertTrue(result["inferred"])
        self.assertEqual(result["goal_hypothesis"], {"attribute": "lamp", "value": "on"})

    def test_single_action_does_not_reveal_intention(self):
        host = IntentionHost()

        result = host.observe_agent_action("alice", "switch", {"lamp": "off"}, {"lamp": "on"})

        self.assertFalse(result["inferred"])

    def test_conflicting_results_withhold_intention(self):
        host = IntentionHost()
        host.observe_agent_action("alice", "move", {"place": "a"}, {"place": "b"})
        host.observe_agent_action("alice", "move", {"place": "b"}, {"place": "a"})
        result = host.observe_agent_action("alice", "move", {"place": "a"}, {"place": "b"})

        self.assertFalse(result["inferred"])

    def test_stated_and_inferred_difference_is_not_called_deception(self):
        host = IntentionHost()
        for action in ("switch", "repair", "replace"):
            host.observe_agent_action("alice", action, {"lamp": "off"}, {"lamp": "on"})
        host.stated_intention("alice", {"attribute": "door", "value": "open"})

        comparison = host.compare_stated_and_inferred_intention("alice")

        self.assertEqual(comparison["status"], "different")
        self.assertIn("기만", comparison["note"])


if __name__ == "__main__":
    unittest.main()
