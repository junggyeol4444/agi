import unittest

from metacognition import MetacognitionMixin


class MetacognitionHost(MetacognitionMixin):
    def __init__(self):
        self.calibration_records = []
        self.lived = 1


class MetacognitionTests(unittest.TestCase):
    def test_reports_overconfidence_from_actual_failures(self):
        host = MetacognitionHost()
        host.record_confidence_outcome("plan", 0.9, False)
        host.record_confidence_outcome("plan", 0.8, False)

        report = host.calibration_report("plan")

        self.assertEqual(report["count"], 2)
        self.assertGreater(report["brier_score"], 0.6)
        self.assertGreater(report["calibration_error"], 0.7)

    def test_well_calibrated_history_has_lower_error(self):
        calibrated = MetacognitionHost()
        overconfident = MetacognitionHost()
        for success in (True, True, False, False):
            calibrated.record_confidence_outcome("belief", 0.5, success)
            overconfident.record_confidence_outcome("belief", 0.95, success)

        self.assertLess(calibrated.calibration_report("belief")["calibration_error"],
                        overconfident.calibration_report("belief")["calibration_error"])

    def test_empty_history_admits_no_measurement(self):
        report = MetacognitionHost().calibration_report("plan")

        self.assertIsNone(report["brier_score"])
        self.assertEqual(report["count"], 0)

    def test_repeated_failures_reduce_future_similar_confidence(self):
        host = MetacognitionHost()
        for _ in range(6):
            host.record_confidence_outcome("plan", 0.95, False)

        adjusted = host.calibrated_confidence("plan", 0.9)

        self.assertTrue(adjusted["adjusted"])
        self.assertLess(adjusted["calibrated"], adjusted["raw"])

    def test_too_little_history_does_not_overcorrect(self):
        host = MetacognitionHost()
        host.record_confidence_outcome("plan", 0.9, False)

        adjusted = host.calibrated_confidence("plan", 0.9)

        self.assertFalse(adjusted["adjusted"])
        self.assertEqual(adjusted["calibrated"], 0.9)

    def test_invalid_bin_count_falls_back_safely(self):
        host = MetacognitionHost()
        host.record_confidence_outcome("plan", 0.5, True)

        report = host.calibration_report("plan", bins="invalid")

        self.assertEqual(report["count"], 1)


if __name__ == "__main__":
    unittest.main()
