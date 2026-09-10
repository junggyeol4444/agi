import unittest

from experience import ExperienceMemoryMixin


class ExperienceHost(ExperienceMemoryMixin):
    def __init__(self):
        self.events = []
        self.event_seq = 0
        self.lived = 4


class ExperienceMemoryTests(unittest.TestCase):
    def test_records_and_recalls_structured_events(self):
        host = ExperienceHost()
        host.record_event("interaction", actor="self", action="reach", obj="공",
                          outcome={"reward": 1}, context={"room": "play"})
        host.record_event("speech", actor="teacher", action="say", obj="공")

        recalled = host.recall_events(kind="interaction", action="reach",
                                      context={"room": "play"})

        self.assertEqual(len(recalled), 1)
        self.assertEqual(recalled[0]["object"], "공")
        self.assertEqual(recalled[0]["outcome"]["reward"], 1)
