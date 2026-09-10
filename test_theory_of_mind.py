import unittest

from theory_of_mind import TheoryOfMindMixin


class MindHost(TheoryOfMindMixin):
    def __init__(self):
        self.situational_facts = {}
        self.perspective_states = {}
        self.lived = 0


class TheoryOfMindTests(unittest.TestCase):
    def test_absent_agent_keeps_last_witnessed_location(self):
        host = MindHost()
        host.record_world_change("ball", "location", "basket", ["alice", "bob"], at=1)
        host.record_world_change("ball", "location", "box", ["bob"], at=2)

        alice = host.expected_search_location("alice", "ball")
        bob = host.expected_search_location("bob", "ball")

        self.assertEqual(alice["location"], "basket")
        self.assertEqual(alice["perspective_status"], "outdated")
        self.assertEqual(bob["location"], "box")
        self.assertEqual(bob["perspective_status"], "current")

    def test_global_change_does_not_overwrite_absent_mind(self):
        host = MindHost()
        host.record_world_change("lamp", "state", "off", ["alice"], at=1)
        host.record_world_change("lamp", "state", "on", [], at=2)

        self.assertEqual(host.perspective_state("alice", "lamp", "state")["value"], "off")

    def test_unknown_viewpoint_is_not_filled_from_actual_world(self):
        host = MindHost()
        host.record_world_change("ball", "location", "box", ["bob"], at=1)

        result = host.expected_search_location("carol", "ball")

        self.assertFalse(result["known"])
        self.assertIsNone(result["location"])

    def test_reobserving_updates_outdated_perspective(self):
        host = MindHost()
        host.record_world_change("ball", "location", "basket", ["alice"], at=1)
        host.record_world_change("ball", "location", "box", [], at=2)
        host.record_world_change("ball", "location", "box", ["alice"], at=3)

        result = host.compare_situational_perspective("alice", "ball", "location")

        self.assertEqual(result["status"], "current")


if __name__ == "__main__":
    unittest.main()
