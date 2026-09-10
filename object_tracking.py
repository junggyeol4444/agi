"""Learn persistent object identities across changing visual scenes."""

import math


class ObjectTrackingMixin:
    """Track instances from appearance and motion without supplied object IDs."""

    def _appearance_similarity(self, left, right):
        if not left or not right:
            return 0.0
        keys = set(left) | set(right)
        score = 0.0
        for key in keys:
            if key not in left or key not in right:
                continue
            a, b = left[key], right[key]
            if isinstance(a, (int, float)) and not isinstance(a, bool) \
                    and isinstance(b, (int, float)) and not isinstance(b, bool):
                scale = max(abs(float(a)), abs(float(b)), 1.0)
                score += max(0.0, 1.0 - abs(float(a) - float(b)) / scale)
            elif a == b:
                score += 1.0
        return score / len(keys)

    def _position_distance(self, left, right):
        if not isinstance(left, (list, tuple)) or not isinstance(right, (list, tuple)):
            return None
        if len(left) != len(right) or not left:
            return None
        return math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(left, right)))

    def observe_scene(self, detections, at=None, appearance_threshold=0.7,
                      max_distance=0.35, max_gap=3):
        """Associate detections with prior tracks and retain temporarily hidden objects."""
        if not isinstance(getattr(self, "object_tracks", None), dict):
            self.object_tracks = {}
        if not isinstance(getattr(self, "scene_history", None), list):
            self.scene_history = []
        moment = int(getattr(self, "lived", 0) if at is None else at)
        used, observed = set(), []
        for raw in detections or []:
            detection = dict(raw) if isinstance(raw, dict) else {}
            position = detection.pop("position", None)
            appearance = detection.get("features", detection)
            if "features" in detection:
                appearance = dict(appearance or {})
            candidates = []
            for track_id, track in self.object_tracks.items():
                if track_id in used or track.get("status") == "lost":
                    continue
                gap = max(1, moment - int(track.get("last_seen", moment)))
                if gap > max_gap + 1:
                    continue
                visual = self._appearance_similarity(track.get("appearance", {}), appearance)
                distance = self._position_distance(track.get("position"), position)
                within_motion = distance is None or distance <= max_distance * gap
                if visual >= appearance_threshold and within_motion:
                    spatial = 1.0 if distance is None else max(0.0, 1.0 - distance / (max_distance * gap))
                    candidates.append((0.75 * visual + 0.25 * spatial, track_id, visual))
            if candidates:
                _, track_id, visual = max(candidates, key=lambda item: (item[0], item[1]))
                track = self.object_tracks[track_id]
                track["appearance"] = dict(appearance)
                track["position"] = position
                track["last_seen"] = moment
                track["observations"] += 1
                track["status"] = "visible"
                reacquired = bool(track.pop("was_occluded", False))
            else:
                self.object_seq = int(getattr(self, "object_seq", 0)) + 1
                track_id = f"object-{self.object_seq}"
                concept = (self.observe_features("object", appearance, source="direct")
                           if appearance and hasattr(self, "observe_features") else None)
                track = {"id": track_id, "appearance": dict(appearance),
                         "position": position, "first_seen": moment,
                         "last_seen": moment, "observations": 1, "status": "visible",
                         "concept_id": concept.get("concept_id") if concept else None}
                self.object_tracks[track_id] = track
                visual, reacquired = 0.0, False
            used.add(track_id)
            observed.append({"track_id": track_id, "reacquired": reacquired,
                             "appearance_similarity": round(visual, 6),
                             "concept_id": track.get("concept_id")})

        for track_id, track in self.object_tracks.items():
            if track_id in used or track.get("status") == "lost":
                continue
            gap = moment - int(track.get("last_seen", moment))
            if gap <= max_gap:
                track["status"] = "occluded"
                track["was_occluded"] = True
            else:
                track["status"] = "lost"
        snapshot = {"at": moment, "observed": observed,
                    "occluded": [key for key, value in self.object_tracks.items()
                                 if value.get("status") == "occluded"],
                    "lost": [key for key, value in self.object_tracks.items()
                             if value.get("status") == "lost"]}
        self.scene_history.append(snapshot)
        self.scene_history = self.scene_history[-500:]
        update_space = getattr(self, "update_spatial_model", None)
        if callable(update_space):
            snapshot["spatial"] = update_space(at=moment)
        return snapshot

    def tracked_objects(self, include_lost=False):
        return [dict(track) for track in (getattr(self, "object_tracks", {}) or {}).values()
                if include_lost or track.get("status") != "lost"]
