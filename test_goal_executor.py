import unittest

from goal_discovery import GoalDiscoveryMixin
from goal_executor import GoalExecutionMixin


class GoalExecutionHost(GoalDiscoveryMixin, GoalExecutionMixin):
    def __init__(self):
        self.developmental_goals = {}
        self.induced_concepts = {}
        self.abstract_rules = {}
        self.verification_tasks = {}
        self.lived = 1


class GoalExecutionTests(unittest.TestCase):
    def test_concept_goal_requests_varied_observation(self):
        host = GoalExecutionHost()
        host.induced_concepts["concept-1"] = {
            "id": "concept-1", "modality": "vision", "observations": 1}
        goal = host.select_developmental_goal()

        plan = host.plan_developmental_goal(goal["id"])

        self.assertEqual(plan["steps"][0]["operation"], "seek_varied_observation")
        self.assertEqual(plan["steps"][0]["needed"], 2)

    def test_executor_does_not_fake_missing_real_observation(self):
        host = GoalExecutionHost()
        host.induced_concepts["concept-1"] = {
            "id": "concept-1", "modality": "vision", "observations": 1}
        goal = host.select_developmental_goal()

        result = host.advance_developmental_goal(goal["id"])

        self.assertFalse(result["executed"])
        self.assertEqual(host.developmental_goals[goal["id"]]["status"], "open")

    def test_real_learning_state_automatically_completes_goal(self):
        host = GoalExecutionHost()
        host.induced_concepts["concept-1"] = {
            "id": "concept-1", "modality": "vision", "observations": 1}
        goal = host.select_developmental_goal()
        host.induced_concepts["concept-1"]["observations"] = 3

        completed = host.refresh_developmental_goals()

        self.assertEqual(completed[0]["id"], goal["id"])
        self.assertEqual(completed[0]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
