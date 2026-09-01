import unittest

import baby
from motivation import IntrinsicMotivationMixin


class MotivationHost(IntrinsicMotivationMixin):
    drive_weights = dict(IntrinsicMotivationMixin.DEFAULT_DRIVE_WEIGHTS)


class IntrinsicMotivationTests(unittest.TestCase):
    def test_novelty_and_learning_progress_create_intrinsic_signal(self):
        signal = MotivationHost().intrinsic_motivation(
            novelty=1.0, uncertainty_before=1.0, uncertainty_after=0.25)

        self.assertGreater(signal["total"], 0)
        self.assertEqual(signal["components"]["uncertainty_reduction"], 0.75)

    def test_world_scripted_reward_is_off_by_default(self):
        world = baby.World(seed=1)
        world.objects = {"공": {"ko": "공"}}
        previous = ("known",)
        world.best[previous] = "reach"

        _, reward, _, _ = world.step("reach", previous, years=1)

        self.assertEqual(reward, 0.0)

    def test_scripted_reward_remains_available_only_for_benchmarking(self):
        world = baby.World(seed=1, scripted_rewards=True)
        world.objects = {"공": {"ko": "공"}}
        previous = ("known",)
        world.best[previous] = "reach"

        _, reward, _, _ = world.step("reach", previous, years=1)

        self.assertEqual(reward, 1.0)

    def test_baby_can_learn_without_scripted_external_reward(self):
        agent = baby.Baby()

        turn = agent.live_one(("new", "experience"))

        self.assertEqual(turn["external_reward"], 0.0)
        self.assertGreater(turn["intrinsic_reward"], 0.0)
        self.assertEqual(agent.events[-1]["outcome"]["intrinsic_reward"],
                         turn["intrinsic_reward"])
