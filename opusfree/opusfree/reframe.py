"""Smart reframing: find faces, track the speaker(s), pick the crop.

Improvements over v1:
- Works on small/low-res sources (upscales frames before detection, lower
  minimum face size, frontal + profile cascades).
- Samples many frames across the clip and clusters face positions into
  speakers.
- Two stable speakers -> automatic split-screen (stacked) crop spec.
- Never crops to a face-less region: with no detections we fall back to a
  center crop, but with any detections we center on people.

The result is a "crop spec" dict consumed by render.py:
    {"mode": "single", "crop": (w, h, x, y)}
    {"mode": "split",  "crops": [(w, h, x, y), (w, h, x, y)]}   # top, bottom
"""

from __future__ import annotations

from typing import List, Tuple

Rect = Tuple[float, float, float]  # center_x, center_y, size (face width)


def _detect_faces_timed(video_path: str, start: float, end: float,
                        samples: int = 40):
    """Sample frames; return (all_rects, timeline) where timeline is a list of
    (t_rel, center_x or None) -- one entry per sample for tracking."""
    try:
        import cv2
    except ImportError:
        return [], []
    if not hasattr(cv2, "CascadeClassifier") or not hasattr(cv2, "data"):
        return [], []
    try:
        frontal = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        profile = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_profileface.xml")
    except Exception:
        return [], []
    if frontal.empty():
        return [], []

    cap = cv2.VideoCapture(video_path)
    found: List[Rect] = []
    timeline = []
    duration = max(end - start, 0.1)
    # More samples for longer clips (denser tracking), capped.
    samples = int(max(12, min(samples, duration * 3)))
    try:
        for k in range(samples):
            frac = (k + 0.5) / samples
            t = start + duration * frac
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, frame = cap.read()
            if not ok:
                timeline.append((duration * frac, None))
                continue
            h, w = frame.shape[:2]
            zoom = 2.0 if w < 900 else 1.0
            if zoom != 1.0:
                frame = cv2.resize(frame, None, fx=zoom, fy=zoom,
                                   interpolation=cv2.INTER_LINEAR)
            gray = cv2.equalizeHist(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
            min_side = max(24, int(gray.shape[0] * 0.10))
            faces = list(frontal.detectMultiScale(
                gray, 1.08, 5, minSize=(min_side, min_side)))
            if not faces and not profile.empty():
                faces = list(profile.detectMultiScale(
                    gray, 1.08, 5, minSize=(min_side, min_side)))
            if faces:
                # biggest (closest) face for this frame
                x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
                cx = (x + fw / 2) / zoom
                found.append((cx, (y + fh / 2) / zoom, fw / zoom))
                timeline.append((duration * frac, cx))
            else:
                timeline.append((duration * frac, None))
    finally:
        cap.release()
    return found, timeline


def _detect_faces(video_path: str, start: float, end: float,
                  samples: int = 16) -> List[Rect]:
    found, _ = _detect_faces_timed(video_path, start, end, samples)
    return found


def _smooth_path(timeline, crop_w: int, src_w: int, win: int = 5):
    """Fill gaps + moving-average smooth the face-x timeline into crop-x
    keyframes (clamped so the crop stays on-screen)."""
    xs = [x for _, x in timeline]
    # forward/back fill Nones
    last = None
    for i, v in enumerate(xs):
        if v is None:
            xs[i] = last
        else:
            last = v
    last = None
    for i in range(len(xs) - 1, -1, -1):
        if xs[i] is None:
            xs[i] = last
        else:
            last = xs[i]
    if all(v is None for v in xs):
        return None
    xs = [src_w / 2 if v is None else v for v in xs]
    # moving average
    sm = []
    for i in range(len(xs)):
        lo, hi = max(0, i - win), min(len(xs), i + win + 1)
        sm.append(sum(xs[lo:hi]) / (hi - lo))
    # to crop-left x, clamped, reduce jitter by keyframe thinning
    keys = []
    for (t, _), cx in zip(timeline, sm):
        x = max(0, min(int(cx - crop_w / 2), src_w - crop_w))
        if not keys or abs(x - keys[-1][1]) > 4 or t - keys[-1][0] > 1.0:
            keys.append((round(t, 3), x))
    return keys


def _cluster_speakers(faces: List[Rect], src_w: int) -> List[List[Rect]]:
    """Group face detections into speaker clusters by horizontal position."""
    if not faces:
        return []
    xs = sorted(faces, key=lambda r: r[0])
    clusters: List[List[Rect]] = [[xs[0]]]
    gap = src_w * 0.18  # faces further apart than this are different people
    for r in xs[1:]:
        if r[0] - clusters[-1][-1][0] > gap:
            clusters.append([r])
        else:
            clusters[-1].append(r)
    clusters.sort(key=len, reverse=True)
    return clusters


def _centered_crop(center_x: float, crop_w: int, crop_h: int, src_w: int,
                   src_h: int) -> Tuple[int, int, int, int]:
    x = int(round(center_x - crop_w / 2.0))
    x = max(0, min(x, src_w - crop_w))
    y = max(0, (src_h - crop_h) // 2)
    return crop_w, crop_h, x, y


def _map_keys_to_output(keys, spans, clip_start):
    """Map source-clip-relative keyframes onto the tightened output timeline
    using the kept spans (drop keys inside removed regions)."""
    if not spans:
        return keys
    out, acc = [], 0.0
    for (s, e) in spans:
        s_rel, e_rel = s - clip_start, e - clip_start
        span_len = e_rel - s_rel
        for (t, x) in keys:
            if s_rel - 1e-6 <= t <= e_rel + 1e-6:
                out.append((round(acc + (t - s_rel), 3), x))
        acc += span_len
    return out or keys


def compute_crop_spec(video_path: str, start: float, end: float, src_w: int,
                      src_h: int, target_ratio: float = 9 / 16,
                      allow_split: bool = True, spans=None) -> dict:
    """Return a crop spec for this clip. When a single speaker moves, includes
    a smoothed ``track_x`` path (output-timeline (t, x) keyframes) so the crop
    follows them."""
    desired_w = src_h * target_ratio

    if desired_w > src_w:
        crop_h = min(int(round(src_w / target_ratio)), src_h)
        return {"mode": "single",
                "crop": (src_w, crop_h, 0, max(0, (src_h - crop_h) // 2))}

    crop_w = int(round(desired_w))
    faces, timeline = _detect_faces_timed(video_path, start, end)
    clusters = _cluster_speakers(faces, src_w)

    # Two stable speakers -> split-screen.
    if allow_split and len(clusters) >= 2 and len(clusters[1]) >= max(
            3, len(faces) // 4):
        panel_ratio = target_ratio * 2
        pw = min(src_w, int(round(src_h * panel_ratio)))
        two = sorted(clusters[:2], key=lambda cl: sum(r[0] for r in cl) / len(cl))
        panels = [_centered_crop(sum(r[0] for r in cl) / len(cl), pw, src_h,
                                 src_w, src_h) for cl in two]
        return {"mode": "split", "crops": panels}

    if clusters and len(clusters[0]) >= 2:
        keys = _smooth_path(timeline, crop_w, src_w)
        best = clusters[0]
        total = sum(r[2] for r in best) or 1.0
        cx = sum(r[0] * r[2] for r in best) / total
        spec = {"mode": "single",
                "crop": _centered_crop(cx, crop_w, src_h, src_w, src_h)}
        if keys and len(keys) >= 2:
            spec["track_x"] = _map_keys_to_output(keys, spans, start)
            spec["crop_wh"] = (crop_w, src_h)
        return spec

    # No confident face: blurred fill, full scene visible (no blank walls).
    return {"mode": "blur"}


def compute_crop(video_path: str, start: float, end: float, src_w: int,
                 src_h: int, target_ratio: float = 9 / 16
                 ) -> Tuple[int, int, int, int]:
    """Back-compat single-crop API used by older examples."""
    spec = compute_crop_spec(video_path, start, end, src_w, src_h,
                             target_ratio, allow_split=False)
    return spec["crop"]
