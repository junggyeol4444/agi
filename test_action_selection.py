import random
import unittest

from action_selection import ActionSelectionMixin
from world_model import WorldModelMixin


class SelectionHost(ActionSelectionMixin, WorldModelMixin):
    def __init__(self):
        self.transition_model = {}
        self.action_decisions = []
        self.lived = 0
        self.world = type("WorldStub", (), {"rng": random.Random(3)})()


class ActionSelectionTests(unittest.TestCase):
    def test_untried_action_is_selected_for_information(self):
        host = SelectionHost()
        for _ in range(4):
            host.learn_transition(["room"], "still", ["room"], 0.0)

        decision = host.select_action(["room"], ["still", "reach"])

        self.assertEqual(decision["action"], "reach")
        self.assertIn("모르는 행동", decision["reason"])

    def test_cost_can_prevent_pointless_exploration(self):
        host = SelectionHost()

        decision = host.select_action(
            ["safe"], ["safe_action", "expensive_unknown"],
            action_costs={"expensive_unknown": 2.0},
        )

        self.assertEqual(decision["action"], "safe_action")

    def test_decision_keeps_auditable_comparison(self):
        host = SelectionHost()

        decision = host.select_action(["state"], ["a", "b"])

        self.assertEqual(len(decision["evaluations"]), 2)
        self.assertEqual(host.action_decisions[-1]["action"], decision["action"])


if __name__ == "__main__":
    unittest.main()
