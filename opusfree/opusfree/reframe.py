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


def _detect_faces(video_path: str, start: float, end: float,
                  samples: int = 16) -> List[Rect]:
    """Sample frames across [start, end] and return detected face rects."""
    try:
        import cv2
    except ImportError:
        return []
    if not hasattr(cv2, "CascadeClassifier") or not hasattr(cv2, "data"):
        return []

    try:
        frontal = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        profile = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_profileface.xml")
    except Exception:
        return []
    if frontal.empty():
        return []

    cap = cv2.VideoCapture(video_path)
    found: List[Rect] = []
    duration = max(end - start, 0.1)
    try:
        for k in range(samples):
            t = start + duration * (k + 0.5) / samples
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, frame = cap.read()
            if not ok:
                continue
            h, w = frame.shape[:2]
            # Low-res sources (podcast rips are often 640x360): upscale so the
            # cascade has enough pixels to find small faces.
            zoom = 1.0
            if w < 900:
                zoom = 2.0
                frame = cv2.resize(frame, None, fx=zoom, fy=zoom,
                                   interpolation=cv2.INTER_LINEAR)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)
            min_side = max(24, int(gray.shape[0] * 0.10))
            faces = list(frontal.detectMultiScale(
                gray, scaleFactor=1.08, minNeighbors=5,
                minSize=(min_side, min_side)))
            if not faces and not profile.empty():
                faces = list(profile.detectMultiScale(
                    gray, scaleFactor=1.08, minNeighbors=5,
                    minSize=(min_side, min_side)))
            for (x, y, fw, fh) in faces:
                found.append(((x + fw / 2) / zoom, (y + fh / 2) / zoom, fw / zoom))
    finally:
        cap.release()
    return found


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


def compute_crop_spec(video_path: str, start: float, end: float, src_w: int,
                      src_h: int, target_ratio: float = 9 / 16,
                      allow_split: bool = True) -> dict:
    """Return a crop spec for this clip (see module docstring)."""
    desired_w = src_h * target_ratio

    # Source narrower than target: crop height instead, keep width.
    if desired_w > src_w:
        crop_h = min(int(round(src_w / target_ratio)), src_h)
        return {"mode": "single",
                "crop": (src_w, crop_h, 0, max(0, (src_h - crop_h) // 2))}

    crop_w = int(round(desired_w))
    faces = _detect_faces(video_path, start, end)
    clusters = _cluster_speakers(faces, src_w)

    # Two stable speakers on screen -> split-screen, one panel each.
    if allow_split and len(clusters) >= 2 and len(clusters[1]) >= max(
            3, len(faces) // 4):
        panel_ratio = target_ratio * 2  # each panel is half the output height
        pw = min(src_w, int(round(src_h * panel_ratio)))
        panels = []
        # Keep on-screen order (left person on top) for a natural look.
        two = sorted(clusters[:2], key=lambda cl: sum(r[0] for r in cl) / len(cl))
        for cl in two:
            cx = sum(r[0] for r in cl) / len(cl)
            panels.append(_centered_crop(cx, pw, src_h, src_w, src_h))
        return {"mode": "split", "crops": panels}

    if clusters:
        # Weight face centers by detection size (bigger face = closer speaker).
        best = clusters[0]
        total = sum(r[2] for r in best) or 1.0
        cx = sum(r[0] * r[2] for r in best) / total
        return {"mode": "single",
                "crop": _centered_crop(cx, crop_w, src_h, src_w, src_h)}

    # No faces found anywhere: center crop as a last resort.
    return {"mode": "single",
            "crop": _centered_crop(src_w / 2.0, crop_w, src_h, src_w, src_h)}


def compute_crop(video_path: str, start: float, end: float, src_w: int,
                 src_h: int, target_ratio: float = 9 / 16
                 ) -> Tuple[int, int, int, int]:
    """Back-compat single-crop API used by older examples."""
    spec = compute_crop_spec(video_path, start, end, src_w, src_h,
                             target_ratio, allow_split=False)
    return spec["crop"]
