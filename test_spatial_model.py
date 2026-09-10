import unittest

from concept_learning import ConceptLearningMixin
from object_tracking import ObjectTrackingMixin
from spatial_model import SpatialModelMixin


class SpatialHost(ObjectTrackingMixin, ConceptLearningMixin, SpatialModelMixin):
    def __init__(self):
        self.object_tracks = {}
        self.object_seq = 0
        self.scene_history = []
        self.spatial_relations = {}
        self.induced_concepts = {}
        self.concept_seq = 0
        self.lived = 0


class SpatialModelTests(unittest.TestCase):
    def _scene(self, host, at=1):
        return host.observe_scene([
            {"features": {"color": "red"}, "position": [0.1, 0.2]},
            {"features": {"color": "blue"}, "position": [0.3, 0.2]},
        ], at=at)

    def test_pairwise_relations_are_symmetric(self):
        host = SpatialHost()
        scene = self._scene(host)
        first, second = [item["track_id"] for item in scene["observed"]]

        forward = host.spatial_relation(first, second, at=1)
        reverse = host.spatial_relation(second, first, at=1)

        self.assertIn("left_of", forward["relations"])
        self.assertIn("right_of", reverse["relations"])
        self.assertIn("near", forward["relations"])

    def test_old_relation_is_retained_but_marked_stale(self):
        host = SpatialHost()
        scene = self._scene(host, at=1)
        first, second = [item["track_id"] for item in scene["observed"]]

        relation = host.spatial_relation(first, second, max_age=2, at=5)

        self.assertFalse(relation["known"])
        self.assertTrue(relation["stale"])

    def test_scene_observation_updates_spatial_map_automatically(self):
        host = SpatialHost()

        self._scene(host)

        self.assertEqual(len(host.spatial_relations), 2)


if __name__ == "__main__":
    unittest.main()
