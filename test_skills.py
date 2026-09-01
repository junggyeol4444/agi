import unittest

from planner import PlannerMixin
from skills import SkillLearningMixin
from world_model import WorldModelMixin


class SkillHost(SkillLearningMixin, PlannerMixin, WorldModelMixin):
    def __init__(self):
        self.skills = {}
        self.plans = []
        self.transition_model = {}
        self.lived = 5


class SkillLearningTests(unittest.TestCase):
    def test_repeated_success_compresses_action_sequence(self):
        host = SkillHost()
        run = {"start": "room", "goal": "garden", "status": "completed",
               "steps": [{"action": "open"}, {"action": "walk"}]}

        first = host.observe_skill_run(run)
        second = host.observe_skill_run(run)

        self.assertEqual(first["status"], "candidate")
        self.assertEqual(second["status"], "learned")
        self.assertEqual(second["actions"], ["open", "walk"])

    def test_planner_reuses_learned_skill_without_researching_path(self):
        host = SkillHost()
        run = {"start": "room", "goal": "garden", "status": "completed",
               "steps": [{"action": "open"}, {"action": "walk"}]}
        host.observe_skill_run(run)
        host.observe_skill_run(run)

        plan = host.plan_actions("room", "garden", ["open", "walk"])

        self.assertEqual(plan["actions"], ["open", "walk"])
        self.assertIn("기술", plan["reason"])
        self.assertIn("skill_id", plan)

    def test_single_success_is_not_promoted_to_skill(self):
        host = SkillHost()
        run = {"start": "room", "goal": "garden", "status": "completed",
               "steps": [{"action": "open"}]}

        host.observe_skill_run(run)

        self.assertIsNone(host.recall_skill("room", "garden"))

    def test_replanned_detour_is_not_compressed_as_skill(self):
        host = SkillHost()
        run = {"start": "room", "goal": "garden", "status": "completed",
               "replans": 1,
               "steps": [{"action": "wrong", "matched": False},
                         {"action": "walk", "matched": True}]}

        learned = host.observe_skill_run(run)

        self.assertIsNone(learned)
        self.assertEqual(host.skills, {})


if __name__ == "__main__":
    unittest.main()
