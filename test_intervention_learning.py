import unittest

import baby
from intervention_learning import InterventionLearningMixin


class InterventionHost(InterventionLearningMixin):
    def __init__(self):
        self.intervention_trials = {}


class InterventionLearningTests(unittest.TestCase):
    def test_sequence_without_intervention_is_not_treated_as_cause(self):
        host = InterventionHost()

        result = host.intervention_effect("dark", "switch")

        self.assertFalse(result["known"])
        self.assertEqual(host.intervention_trials, {})

    def test_requires_a_comparison_action_in_the_same_context(self):
        host = InterventionHost()
        host.record_intervention("dark", "switch", "light")
        host.record_intervention("dark", "switch", "light")

        result = host.intervention_effect("dark", "switch")

        self.assertFalse(result["known"])
        self.assertEqual(result["baseline_trials"], 0)

    def test_learns_effect_from_repeated_controlled_contrast(self):
        host = InterventionHost()
        for _ in range(2):
            host.record_intervention("dark", "switch", "light")
            host.record_intervention("dark", "wait", "dark")

        result = host.intervention_effect("dark", "switch")

        self.assertTrue(result["known"])
        light = next(item for item in result["effects"]
                     if item["outcome"] == "light")
        self.assertEqual(light["difference"], 1.0)

    def test_experiment_plan_prefers_untried_comparison(self):
        host = InterventionHost()
        host.record_intervention("dark", "switch", "light")

        plan = host.propose_intervention("dark", ["switch", "wait"])

        self.assertEqual(plan["next_action"], "wait")

    def test_baby_records_deliberate_actions_as_interventions(self):
        agent = baby.Baby()
        agent.live_one(("dark", "quiet"), action_override="still")
        agent.live_one(("dark", "quiet"), action_override="gaze")

        self.assertTrue(agent.intervention_trials)


if __name__ == "__main__":
    unittest.main()
