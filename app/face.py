import os

import cv2
import numpy as np
from insightface.app import FaceAnalysis

from app.config import MIN_DET_SCORE, MIN_FACE_WIDTH_RATIO, BLUR_THRESHOLD

_face_app: FaceAnalysis | None = None

# Defaults to ~/.insightface; on a host with an ephemeral filesystem this
# should point at the same persistent volume as DB_PATH, so the model
# doesn't get re-downloaded on every redeploy.
INSIGHTFACE_ROOT = os.environ.get("INSIGHTFACE_ROOT", "~/.insightface")


def get_face_app() -> FaceAnalysis:
    global _face_app
    if _face_app is None:
        _face_app = FaceAnalysis(
            name="buffalo_s",
            root=INSIGHTFACE_ROOT,
            providers=["CPUExecutionProvider"],
            allowed_modules=["detection", "recognition"],  # skip genderage/landmark — unused, costs time per frame
        )
        _face_app.prepare(ctx_id=-1, det_size=(640, 640))  # -1 = CPU, matches the reference repo
    return _face_app


def decode_image(image_bytes: bytes) -> np.ndarray | None:
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img


def _blur_score(img_bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def validate_and_embed(img_bgr: np.ndarray) -> dict:
    """Detect, quality-check, and embed a single face in a frame.

    Returns a dict with 'ok': bool. On success also includes 'embedding'
    (list[float], L2-normalized 512-d) and 'det_score'. On failure includes
    'reason'.
    """
    if img_bgr is None:
        return {"ok": False, "reason": "Could not decode image"}

    h, w = img_bgr.shape[:2]
    faces = get_face_app().get(img_bgr)

    if len(faces) == 0:
        return {"ok": False, "reason": "No face detected"}
    if len(faces) > 1:
        return {"ok": False, "reason": "Multiple faces detected — only one person should be in frame"}

    face = faces[0]

    x1, y1, x2, y2 = face.bbox
    bbox = [
        float(max(0, min(w, x1))),
        float(max(0, min(h, y1))),
        float(max(0, min(w, x2))),
        float(max(0, min(h, y2))),
    ]

    if face.det_score < MIN_DET_SCORE:
        return {"ok": False, "reason": "Face not clear enough — try again", "bbox": bbox}

    face_w = x2 - x1
    if face_w / w < MIN_FACE_WIDTH_RATIO:
        return {"ok": False, "reason": "Face too small — move closer to the camera", "bbox": bbox}

    x1c, y1c, x2c, y2c = [int(v) for v in bbox]
    crop = img_bgr[y1c:y2c, x1c:x2c]
    if crop.size == 0:
        return {"ok": False, "reason": "Face crop out of bounds — try again", "bbox": bbox}

    blur = _blur_score(crop)
    if blur < BLUR_THRESHOLD:
        return {"ok": False, "reason": "Image too blurry — hold still", "bbox": bbox}

    embedding = face.normed_embedding.astype(np.float32).tolist()

    return {"ok": True, "embedding": embedding, "det_score": float(face.det_score), "blur": float(blur), "bbox": bbox}


def detect_and_embed_all(img_bgr: np.ndarray) -> list[dict]:
    """Detect every face in a frame and embed each one.

    Used by the live scanner, which tracks and labels every face in view
    instead of refusing to process a frame with more than one person in it.
    Unlike validate_and_embed (used at enrollment time), this applies no
    confidence/blur/size quality gate at all — every face the detector
    returns gets boxed (as a match or "unknown"), so the box stays glued to
    a face for as long as it's in frame instead of blinking out whenever
    detector confidence dips for a frame.
    """
    if img_bgr is None:
        return []

    h, w = img_bgr.shape[:2]
    faces = get_face_app().get(img_bgr)

    out = []
    for face in faces:
        x1, y1, x2, y2 = face.bbox
        bbox = [
            float(max(0, min(w, x1))),
            float(max(0, min(h, y1))),
            float(max(0, min(w, x2))),
            float(max(0, min(h, y2))),
        ]
        out.append({
            "bbox": bbox,
            "embedding": face.normed_embedding.astype(np.float32).tolist(),
        })
    return out


def embedding_to_blob(embedding: list[float]) -> bytes:
    return np.array(embedding, dtype=np.float32).tobytes()


def blob_to_embedding(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)
