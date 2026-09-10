import unittest

from perspective_model import PerspectiveModelMixin


class PerspectiveHost(PerspectiveModelMixin):
    def __init__(self):
        self.perspective_models = {}
        self.isa = {}
        self.contextual_conclusions = {}
        self.lived = 1


class PerspectiveModelTests(unittest.TestCase):
    def test_private_observation_is_not_copied_to_bystander(self):
        host = PerspectiveHost()
        host.observe_for_agent("alice", "box", "contains", "ball", source="view-1")
        host.observe_for_agent("alice", "box", "contains", "ball", source="view-2")

        self.assertTrue(host.perspective_belief("alice", "box", "contains")["known"])
        self.assertFalse(host.perspective_belief("bob", "box", "contains")["known"])

    def test_same_source_repetition_is_not_independent_evidence(self):
        host = PerspectiveHost()
        host.observe_for_agent("alice", "box", "contains", "ball", source="same-view")
        belief = host.observe_for_agent(
            "alice", "box", "contains", "ball", source="same-view")

        self.assertFalse(belief["known"])
        self.assertEqual(belief["candidates"][0]["support"], 1)

    def test_disagreement_is_not_automatically_called_falsehood(self):
        host = PerspectiveHost()
        host.isa["whale"] = "mammal"
        host.observe_for_agent("alice", "whale", "is_a", "fish", source="lesson-1")
        host.observe_for_agent("alice", "whale", "is_a", "fish", source="lesson-2")

        comparison = host.compare_perspective("alice", "whale")

        self.assertEqual(comparison["status"], "disagrees")
        self.assertIn("자동 판정", comparison["note"])

    def test_shared_event_updates_only_named_observers(self):
        host = PerspectiveHost()

        host.share_observation(["alice", "bob"], "lamp", "state", "on", event_id=7)

        self.assertIn("alice", host.perspective_models)
        self.assertIn("bob", host.perspective_models)
        self.assertNotIn("carol", host.perspective_models)


if __name__ == "__main__":
    unittest.main()
