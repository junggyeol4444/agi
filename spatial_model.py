"""Build an object-centered spatial map from tracked instances."""

import math


class SpatialModelMixin:
    """Represent relative space independently from names and language strings."""

    def update_spatial_model(self, at=None, near_threshold=0.3):
        if not isinstance(getattr(self, "spatial_relations", None), dict):
            self.spatial_relations = {}
        moment = int(getattr(self, "lived", 0) if at is None else at)
        visible = [track for track in (getattr(self, "object_tracks", {}) or {}).values()
                   if track.get("status") == "visible"
                   and isinstance(track.get("position"), (list, tuple))]
        updated = []
        for index, left in enumerate(visible):
            for right in visible[index + 1:]:
                if len(left["position"]) != len(right["position"]):
                    continue
                delta = [float(b) - float(a)
                         for a, b in zip(left["position"], right["position"])]
                distance = math.sqrt(sum(value * value for value in delta))
                forward = self._spatial_entry(left["id"], right["id"], delta,
                                              distance, near_threshold, moment)
                reverse = self._spatial_entry(right["id"], left["id"],
                                              [-value for value in delta], distance,
                                              near_threshold, moment)
                self.spatial_relations[f"{left['id']}\u241f{right['id']}"] = forward
                self.spatial_relations[f"{right['id']}\u241f{left['id']}"] = reverse
                updated.extend((forward, reverse))
        return {"at": moment, "objects": len(visible), "relations": updated}

    def _spatial_entry(self, subject, reference, delta, distance, near_threshold, at):
        relations = []
        if delta:
            if delta[0] > 0:
                relations.append("left_of")
            elif delta[0] < 0:
                relations.append("right_of")
        if len(delta) > 1:
            if delta[1] > 0:
                relations.append("above")
            elif delta[1] < 0:
                relations.append("below")
        relations.append("near" if distance <= near_threshold else "far")
        return {"subject": subject, "reference": reference,
                "delta": delta, "distance": round(distance, 6),
                "relations": relations, "observed_at": at}

    def spatial_relation(self, subject, reference, max_age=None, at=None):
        relation = (getattr(self, "spatial_relations", {}) or {}).get(
            f"{subject}\u241f{reference}")
        if not relation:
            return {"known": False, "subject": subject, "reference": reference,
                    "reason": "두 객체의 공간 관계를 함께 관찰한 적 없음"}
        result = dict(relation)
        moment = int(getattr(self, "lived", 0) if at is None else at)
        result["age"] = max(0, moment - int(relation.get("observed_at", moment)))
        result["stale"] = max_age is not None and result["age"] > int(max_age)
        result["known"] = not result["stale"]
        if result["stale"]:
            result["reason"] = "마지막 공동 관찰이 너무 오래됨"
        return result
