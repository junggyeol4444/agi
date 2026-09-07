"""Measure whether the agent's confidence matches its actual outcomes."""


class MetacognitionMixin:
    """Keep calibration evidence instead of merely claiming uncertainty awareness."""

    def record_confidence_outcome(self, kind, confidence, succeeded, context=None):
        if not isinstance(getattr(self, "calibration_records", None), list):
            self.calibration_records = []
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.5
        record = {"kind": str(kind), "confidence": confidence,
                  "succeeded": bool(succeeded), "context": context or {},
                  "at": getattr(self, "lived", 0)}
        self.calibration_records.append(record)
        self.calibration_records = self.calibration_records[-2000:]
        return dict(record)

    def calibration_report(self, kind=None, bins=5):
        records = [record for record in (getattr(self, "calibration_records", []) or [])
                   if kind is None or record.get("kind") == kind]
        try:
            bins = max(1, min(20, int(bins)))
        except (TypeError, ValueError):
            bins = 5
        if not records:
            return {"kind": kind, "count": 0, "brier_score": None,
                    "calibration_error": None, "bins": []}
        grouped = [[] for _ in range(bins)]
        brier = 0.0
        for record in records:
            confidence = record["confidence"]
            outcome = 1.0 if record["succeeded"] else 0.0
            brier += (confidence - outcome) ** 2
            index = min(bins - 1, int(confidence * bins))
            grouped[index].append((confidence, outcome))
        summary = []
        weighted_error = 0.0
        for index, values in enumerate(grouped):
            if not values:
                continue
            mean_confidence = sum(value[0] for value in values) / len(values)
            success_rate = sum(value[1] for value in values) / len(values)
            error = abs(mean_confidence - success_rate)
            weighted_error += error * len(values)
            summary.append({"range": [round(index / bins, 3),
                                      round((index + 1) / bins, 3)],
                            "count": len(values),
                            "mean_confidence": round(mean_confidence, 4),
                            "success_rate": round(success_rate, 4),
                            "error": round(error, 4)})
        return {"kind": kind, "count": len(records),
                "brier_score": round(brier / len(records), 6),
                "calibration_error": round(weighted_error / len(records), 6),
                "bins": summary}

    def calibrated_confidence(self, kind, confidence, min_records=3):
        """Adjust a new confidence using observed outcomes from similar estimates."""
        try:
            raw = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            raw = 0.5
        records = [record for record in (getattr(self, "calibration_records", []) or [])
                   if record.get("kind") == kind
                   and abs(float(record.get("confidence", 0.5)) - raw) <= 0.15]
        if len(records) < min_records:
            return {"raw": raw, "calibrated": raw, "records": len(records),
                    "adjusted": False}
        successes = sum(1 for record in records if record.get("succeeded"))
        # Laplace smoothing prevents a few early outcomes from forcing confidence to 0 or 1.
        empirical = (successes + 1.0) / (len(records) + 2.0)
        evidence_weight = len(records) / (len(records) + 5.0)
        calibrated = raw * (1.0 - evidence_weight) + empirical * evidence_weight
        return {"raw": raw, "calibrated": round(calibrated, 6),
                "empirical_success": round(empirical, 6),
                "records": len(records), "adjusted": True}
