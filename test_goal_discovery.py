import unittest

import baby
from goal_discovery import GoalDiscoveryMixin


class GoalHost(GoalDiscoveryMixin):
    def __init__(self):
        self.developmental_goals = {}
        self.induced_concepts = {}
        self.abstract_rules = {}
        self.verification_tasks = {}
        self.lived = 1


class GoalDiscoveryTests(unittest.TestCase):
    def test_new_concept_creates_its_own_learning_goal(self):
        host = GoalHost()
        host.induced_concepts["concept-1"] = {"id": "concept-1", "observations": 1}

        goal = host.select_developmental_goal()

        self.assertEqual(goal["kind"], "stabilize_concept")
        self.assertEqual(goal["target"], "concept-1")

    def test_variable_rule_becomes_exception_investigation(self):
        host = GoalHost()
        host.abstract_rules["rule"] = {"status": "variable", "reliability": 0.6}

        goals = host.discover_goals()

        self.assertEqual(goals[0]["kind"], "explain_exception")

    def test_repeated_discovery_does_not_duplicate_goal(self):
        host = GoalHost()
        host.induced_concepts["concept-1"] = {"id": "concept-1", "observations": 1}

        host.discover_goals()
        host.discover_goals()

        self.assertEqual(len(host.developmental_goals), 1)

    def test_progress_can_complete_a_goal(self):
        host = GoalHost()
        host.induced_concepts["concept-1"] = {"id": "concept-1", "observations": 2}
        goal = host.select_developmental_goal()

        result = host.record_goal_attempt(goal["id"], progress=True,
                                          evidence="다른 상황에서 재관찰")

        self.assertEqual(result["goal"]["status"], "completed")

    def test_lived_cognitive_cycle_can_focus_a_self_discovered_goal(self):
        agent = baby.Baby()
        agent.live_one(("bright", "quiet"), action_override="still")

        turn = agent.live_one(("bright", "quiet"), action_override="still")

        self.assertEqual(turn["cognitive_cycle"]["mode"], "investigate")
        self.assertEqual(turn["cognitive_cycle"]["focus"]["data"]["kind"],
                         "stabilize_concept")


if __name__ == "__main__":
    unittest.main()
