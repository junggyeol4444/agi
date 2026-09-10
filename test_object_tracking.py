import unittest

from concept_learning import ConceptLearningMixin
from object_tracking import ObjectTrackingMixin


class TrackingHost(ObjectTrackingMixin, ConceptLearningMixin):
    def __init__(self):
        self.object_tracks = {}
        self.object_seq = 0
        self.scene_history = []
        self.induced_concepts = {}
        self.concept_seq = 0
        self.lived = 0


class ObjectTrackingTests(unittest.TestCase):
    def test_moving_detection_retains_identity(self):
        host = TrackingHost()
        first = host.observe_scene(
            [{"features": {"shape": "round", "color": "red"}, "position": [0.1, 0.1]}], at=1)
        second = host.observe_scene(
            [{"features": {"shape": "round", "color": "red"}, "position": [0.2, 0.1]}], at=2)

        self.assertEqual(first["observed"][0]["track_id"], second["observed"][0]["track_id"])
        self.assertEqual(len(host.object_tracks), 1)

    def test_different_appearance_creates_distinct_object(self):
        host = TrackingHost()
        host.observe_scene([{"features": {"shape": "round", "color": "red"}}], at=1)
        host.observe_scene([{"features": {"shape": "square", "color": "blue"}}], at=2)

        self.assertEqual(len(host.object_tracks), 2)

    def test_temporarily_hidden_object_is_reacquired(self):
        host = TrackingHost()
        first = host.observe_scene(
            [{"features": {"shape": "round", "color": "red"}, "position": [0.1, 0.1]}], at=1)
        hidden = host.observe_scene([], at=2)
        returned = host.observe_scene(
            [{"features": {"shape": "round", "color": "red"}, "position": [0.2, 0.1]}], at=3)

        self.assertIn(first["observed"][0]["track_id"], hidden["occluded"])
        self.assertTrue(returned["observed"][0]["reacquired"])

    def test_long_missing_object_becomes_lost(self):
        host = TrackingHost()
        first = host.observe_scene([{"features": {"shape": "round"}}], at=1)
        lost = host.observe_scene([], at=5, max_gap=3)

        self.assertIn(first["observed"][0]["track_id"], lost["lost"])
        self.assertEqual(host.tracked_objects(), [])


if __name__ == "__main__":
    unittest.main()
