import unittest

from belief_system import EvidenceBeliefMixin


class BeliefHost(EvidenceBeliefMixin):
    """Small host proving the belief module does not require the Baby world."""

    def __init__(self):
        self.isa = {}
        self.doubts = {}
        self.beliefs = {}
        self.belief_revisions = []
        self.answer_history = []
        self.verification_tasks = {}
        self.curiosity = {}
        self.lived = 0

    def _wonder(self, subject):
        self.curiosity[subject] = self.curiosity.get(subject, 0) + 1

    def _j(self, word, with_batchim, without_batchim):
        return f"{word}{with_batchim}"


class StandaloneBeliefSystemTests(unittest.TestCase):
    def test_belief_module_verifies_without_constructing_baby_world(self):
        host = BeliefHost()
        host.observe_belief("펭귄", "is_a", "조류", source="관찰-A")
        host.observe_belief("펭귄", "is_a", "조류", source="관찰-B")

        result = host.verify_belief("펭귄")

        self.assertTrue(result["verified"])
        self.assertEqual(host.isa["펭귄"], "조류")

    def test_belief_module_creates_standalone_verification_plan(self):
        host = BeliefHost()

        thought = host.deliberate("새로운것")

        self.assertEqual(thought["action"], "investigate")
        self.assertEqual(thought["verification_plan"]["status"], "open")
        self.assertEqual(host.curiosity["새로운것"], 1)


if __name__ == "__main__":
    unittest.main()
