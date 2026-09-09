import unittest

import baby
from concept_learning import ConceptLearningMixin


class ConceptHost(ConceptLearningMixin):
    def __init__(self):
        self.induced_concepts = {}
        self.concept_seq = 0
        self.lived = 1


class ConceptLearningTests(unittest.TestCase):
    def test_recurring_structure_forms_concept_without_label(self):
        host = ConceptHost()
        first = host.observe_features("vision", {
            "shape": "round", "color": "red", "size": "small", "solid": True})
        second = host.observe_features("vision", {
            "shape": "round", "color": "red", "size": "medium", "solid": True})

        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["concept_id"], second["concept_id"])
        self.assertEqual(len(host.induced_concepts), 1)

    def test_different_structure_creates_new_concept(self):
        host = ConceptHost()
        host.observe_features("vision", {"shape": "round", "color": "red"})

        different = host.observe_features(
            "vision", {"shape": "square", "color": "blue"})

        self.assertTrue(different["created"])
        self.assertEqual(len(host.induced_concepts), 2)

    def test_recognition_does_not_create_memory(self):
        host = ConceptHost()
        host.observe_features("sound", {"pitch": "high", "rhythm": "short"})

        result = host.recognize_concept(
            "sound", {"pitch": "high", "rhythm": "short"})

        self.assertTrue(result["recognized"])
        self.assertEqual(len(host.induced_concepts), 1)

    def test_numeric_prototype_learns_the_observed_mean(self):
        host = ConceptHost()
        host.observe_features("touch", {"temperature": 10.0})
        host.observe_features("touch", {"temperature": 12.0})

        concept = host.learned_concepts("touch")[0]

        self.assertEqual(concept["prototype"]["temperature"], 11.0)
        self.assertEqual(concept["observations"], 2)

    def test_baby_turn_links_event_to_self_induced_concept(self):
        agent = baby.Baby()

        turn = agent.live_one(("bright", "quiet"))

        self.assertIn(turn["induced_concept"]["concept_id"], agent.induced_concepts)
        self.assertEqual(agent.events[-1]["metadata"]["induced_concept"],
                         turn["induced_concept"]["concept_id"])
        self.assertEqual(agent.events[-1]["metadata"]["cognitive_cycle"],
                         turn["cognitive_cycle"]["id"])


if __name__ == "__main__":
    unittest.main()
