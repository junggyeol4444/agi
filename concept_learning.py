"""Incremental concept formation from recurring feature structure."""

import json


class ConceptLearningMixin:
    """Create prototype concepts from experience without supplied class labels."""

    def _feature_value_key(self, value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), default=str)

    def _concept_similarity(self, prototype, features):
        if not prototype or not features:
            return 0.0
        keys = set(prototype) | set(features)
        score = 0.0
        for key in keys:
            if key not in prototype or key not in features:
                continue
            left, right = prototype[key], features[key]
            if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                scale = max(abs(float(left)), abs(float(right)), 1.0)
                score += max(0.0, 1.0 - abs(float(left) - float(right)) / scale)
            elif left == right:
                score += 1.0
        return score / len(keys)

    def recognize_concept(self, modality, features, threshold=0.7):
        features = {str(key): value for key, value in (features or {}).items()
                    if value is not None}
        candidates = []
        for concept in (getattr(self, "induced_concepts", {}) or {}).values():
            if concept.get("modality") != modality:
                continue
            similarity = self._concept_similarity(concept.get("prototype", {}), features)
            candidates.append((similarity, concept))
        if not candidates:
            return {"recognized": False, "concept_id": None, "similarity": 0.0}
        similarity, concept = max(candidates, key=lambda item: item[0])
        return {"recognized": similarity >= threshold,
                "concept_id": concept["id"] if similarity >= threshold else None,
                "nearest_id": concept["id"], "similarity": round(similarity, 6)}

    def observe_features(self, modality, features, threshold=0.7, source="direct"):
        if not isinstance(getattr(self, "induced_concepts", None), dict):
            self.induced_concepts = {}
        features = {str(key): value for key, value in (features or {}).items()
                    if value is not None}
        match = self.recognize_concept(modality, features, threshold)
        if match["recognized"]:
            concept = self.induced_concepts[match["concept_id"]]
        else:
            self.concept_seq = int(getattr(self, "concept_seq", 0)) + 1
            concept_id = f"concept-{self.concept_seq}"
            concept = {"id": concept_id, "modality": modality, "prototype": {},
                       "feature_counts": {}, "feature_stats": {}, "observations": 0,
                       "created_at": getattr(self, "lived", 0), "sources": []}
            self.induced_concepts[concept_id] = concept
        for key, value in features.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                stats = concept.setdefault("feature_stats", {}).setdefault(
                    key, {"sum": 0.0, "count": 0})
                stats["sum"] += float(value)
                stats["count"] += 1
                concept["prototype"][key] = stats["sum"] / stats["count"]
                continue
            encoded = self._feature_value_key(value)
            counts = concept["feature_counts"].setdefault(key, {})
            counts[encoded] = counts.get(encoded, 0) + 1
            best = max(counts, key=counts.get)
            concept["prototype"][key] = json.loads(best)
        concept["observations"] += 1
        if source not in concept["sources"]:
            concept["sources"].append(source)
            concept["sources"] = concept["sources"][-20:]
        concept["updated_at"] = getattr(self, "lived", 0)
        return {"concept_id": concept["id"], "created": not match["recognized"],
                "similarity": match.get("similarity", 0.0),
                "prototype": dict(concept["prototype"]),
                "observations": concept["observations"]}

    def learned_concepts(self, modality=None, limit=50):
        """Return the most experienced self-induced concepts for inspection."""
        concepts = [dict(concept) for concept in
                    (getattr(self, "induced_concepts", {}) or {}).values()
                    if modality is None or concept.get("modality") == modality]
        concepts.sort(key=lambda concept: (-concept.get("observations", 0),
                                           concept.get("id", "")))
        return concepts[:max(0, int(limit))]
