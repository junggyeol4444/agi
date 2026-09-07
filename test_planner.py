import unittest

from metacognition import MetacognitionMixin
from planner import PlannerMixin
from world_model import WorldModelMixin


class PlannerHost(PlannerMixin, WorldModelMixin):
    def __init__(self):
        self.transition_model = {}
        self.plans = []
        self.lived = 7


class CalibratingPlannerHost(PlannerMixin, MetacognitionMixin, WorldModelMixin):
    def __init__(self):
        self.transition_model = {}
        self.plans = []
        self.calibration_records = []
        self.lived = 7


class PlannerTests(unittest.TestCase):
    def test_connects_learned_transitions_into_multistep_plan(self):
        host = PlannerHost()
        host.learn_transition("room", "open", "hall", 0.0)
        host.learn_transition("hall", "walk", "garden", 0.0)

        plan = host.plan_actions("room", "garden", ["open", "walk"], max_depth=3)

        self.assertEqual(plan["status"], "planned")
        self.assertEqual(plan["actions"], ["open", "walk"])
        self.assertEqual(plan["states"], ["room", "hall", "garden"])

    def test_does_not_invent_missing_transition(self):
        host = PlannerHost()
        host.learn_transition("room", "open", "hall", 0.0)

        plan = host.plan_actions("room", "moon", ["open", "jump"], max_depth=3)

        self.assertEqual(plan["status"], "insufficient_model")
        self.assertEqual(plan["actions"], [])

    def test_dictionary_goal_can_match_partial_state(self):
        host = PlannerHost()
        host.learn_transition({"place": "room", "door": "closed"}, "open",
                              {"place": "room", "door": "open"}, 0.0)

        plan = host.plan_actions({"place": "room", "door": "closed"},
                                 {"door": "open"}, ["open"])

        self.assertEqual(plan["status"], "planned")
        self.assertEqual(plan["actions"], ["open"])

    def test_planner_lowers_confidence_after_similar_overconfidence(self):
        host = CalibratingPlannerHost()
        host.learn_transition("room", "open", "goal", 0.0)
        for _ in range(6):
            host.record_confidence_outcome("plan", 0.95, False)

        plan = host.plan_actions("room", "goal", ["open"])

        self.assertEqual(plan["raw_confidence"], 1.0)
        self.assertLess(plan["confidence"], plan["raw_confidence"])
        self.assertTrue(plan["calibration"]["adjusted"])


if __name__ == "__main__":
    unittest.main()
