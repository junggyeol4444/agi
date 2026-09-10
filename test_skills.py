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

    def test_skill_generalizes_only_shared_start_conditions(self):
        host = SkillHost()
        for room in ("kitchen", "bedroom"):
            host.observe_skill_run({
                "start": {"room": room, "door": "closed"},
                "goal": {"door": "open"}, "status": "completed",
                "steps": [{"action": "open"}],
            })

        reusable = host.recall_skill(
            {"room": "office", "door": "closed"}, {"door": "open"})
        rejected = host.recall_skill(
            {"room": "office", "door": "open"}, {"door": "open"})

        self.assertIsNotNone(reusable)
        self.assertEqual(reusable["preconditions"]["required"], {"door": "closed"})
        self.assertIsNone(rejected)

    def test_failed_reuse_lowers_skill_reliability(self):
        host = SkillHost()
        run = {"start": "room", "goal": "garden", "status": "completed",
               "steps": [{"action": "walk"}]}
        skill = host.observe_skill_run(run)
        skill = host.observe_skill_run(run)

        failed = host.observe_skill_run({"start": "room", "goal": "garden",
                                         "status": "incomplete",
                                         "skill_id": skill["id"],
                                         "steps": [{"action": "walk"}]})

        self.assertEqual(failed["status"], "unreliable")
        self.assertIn("room", failed["excluded_states"])
        self.assertIsNone(host.recall_skill("room", "garden"))

    def test_no_shared_condition_does_not_generalize_everywhere(self):
        host = SkillHost()
        for start in ({"mode": "a"}, {"place": "b"}):
            host.observe_skill_run({"start": start, "goal": "done",
                                    "status": "completed",
                                    "steps": [{"action": "act"}]})

        self.assertIsNone(host.recall_skill({"unseen": "c"}, "done"))


if __name__ == "__main__":
    unittest.main()
