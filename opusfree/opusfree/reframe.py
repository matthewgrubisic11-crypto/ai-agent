"""Auto-reframe a horizontal clip to vertical 9:16, tracking the speaker.

Samples frames across the clip, finds the dominant face with OpenCV, and
computes a horizontal crop centred on the speaker. Falls back to a centre crop
if OpenCV isn't available or no face is found — so it always produces output.
"""

from __future__ import annotations


def _detect_face_center_x(video_path: str, start: float, end: float,
                          src_w: int, src_h: int, samples: int = 12) -> float:
    """Return the average face centre-x (in pixels), or src_w/2 if none found."""
    try:
        import cv2
    except ImportError:
        return src_w / 2.0

    # Some headless/preview builds omit the objdetect module; fall back cleanly.
    if not hasattr(cv2, "CascadeClassifier") or not hasattr(cv2, "data"):
        return src_w / 2.0

    try:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        face_cascade = cv2.CascadeClassifier(cascade_path)
    except Exception:
        return src_w / 2.0
    if face_cascade.empty():
        return src_w / 2.0

    cap = cv2.VideoCapture(video_path)
    centers = []
    duration = max(end - start, 0.1)
    try:
        for k in range(samples):
            t = start + duration * (k + 0.5) / samples
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, frame = cap.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
            if len(faces):
                # Largest face wins (closest speaker).
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                centers.append(x + w / 2.0)
    finally:
        cap.release()

    if not centers:
        return src_w / 2.0
    return sum(centers) / len(centers)


def compute_crop(video_path: str, start: float, end: float, src_w: int,
                 src_h: int, target_ratio: float = 9 / 16) -> tuple[int, int, int, int]:
    """Return an ffmpeg crop rect (w, h, x, y) for a 9:16 output.

    Keeps full height and crops width to the target aspect, centred on the
    speaker's face. If the source is already tall enough, crops height instead.
    """
    desired_w = src_h * target_ratio
    if desired_w <= src_w:
        crop_w = int(round(desired_w))
        crop_h = src_h
        center_x = _detect_face_center_x(video_path, start, end, src_w, src_h)
        x = int(round(center_x - crop_w / 2.0))
        x = max(0, min(x, src_w - crop_w))
        return crop_w, crop_h, x, 0

    # Source narrower than 9:16 -> crop height, keep width.
    crop_w = src_w
    crop_h = int(round(src_w / target_ratio))
    crop_h = min(crop_h, src_h)
    y = max(0, (src_h - crop_h) // 2)
    return crop_w, crop_h, 0, y
