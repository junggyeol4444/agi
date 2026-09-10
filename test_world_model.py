import unittest

import baby
from world_model import WorldModelMixin


class WorldModelHost(WorldModelMixin):
    def __init__(self):
        self.transition_model = {}


class WorldModelTests(unittest.TestCase):
    def test_learns_action_effect_distribution_from_experience(self):
        host = WorldModelHost()
        host.learn_transition(["near", "ball"], "reach", ["holding", "ball"], 1)
        host.learn_transition(["near", "ball"], "reach", ["holding", "ball"], 1)
        host.learn_transition(["near", "ball"], "reach", ["missed", "ball"], 0)

        model = host.predict_effects(["near", "ball"], "reach")

        self.assertTrue(model["known"])
        self.assertEqual(model["observations"], 3)
        self.assertAlmostEqual(model["outcomes"][0]["probability"], 2 / 3, places=4)
        self.assertAlmostEqual(model["expected_reward"], 2 / 3, places=4)

    def test_unknown_action_does_not_invent_an_outcome(self):
        model = WorldModelHost().predict_effects(["new"], "unknown")

        self.assertFalse(model["known"])
        self.assertEqual(model["outcomes"], [])
        self.assertEqual(model["uncertainty"], 1.0)

    def test_baby_turn_records_event_and_updates_world_model(self):
        agent = baby.Baby()

        turn = agent.live_one(("injected", "signal"))

        self.assertEqual(agent.events[-1]["kind"], "interaction")
        self.assertEqual(agent.events[-1]["outcome"]["state"],
                         ["injected", "signal"])
        learned = agent.predict_effects(None, turn["action"])
        self.assertTrue(learned["known"])
        self.assertEqual(learned["outcomes"][0]["state"],
                         ["injected", "signal"])
