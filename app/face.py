import os
import cv2
import numpy as np
from insightface.app import FaceAnalysis

from app.config import MIN_DET_SCORE, MIN_FACE_WIDTH_RATIO, BLUR_THRESHOLD

_face_app: FaceAnalysis | None = None
INSIGHTFACE_ROOT = os.environ.get("INSIGHTFACE_ROOT", "~/.insightface")


def get_face_app() -> FaceAnalysis:
    global _face_app
    if _face_app is None:
        _face_app = FaceAnalysis(
            name="buffalo_s",
            root=INSIGHTFACE_ROOT,
            providers=["CPUExecutionProvider"],
            allowed_modules=["detection", "recognition"],  # skip genderage/landmark for maximum speed
        )
        _face_app.prepare(ctx_id=-1, det_size=(640, 640))
    return _face_app


def decode_image(image_bytes: bytes) -> np.ndarray | None:
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _blur_score(img_bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def validate_and_embed_single(img_bgr: np.ndarray) -> dict:
    """Validate a single photo and extract embedding with auto-augmentation.

    Returns primary embedding plus horizontal flip and brightness-augmented
    variations, giving multi-angle invariance from a single camera snapshot.
    """
    if img_bgr is None:
        return {"ok": False, "reason": "Could not decode image from camera"}

    h, w = img_bgr.shape[:2]
    face_app = get_face_app()
    faces = face_app.get(img_bgr)

    if len(faces) == 0:
        return {"ok": False, "reason": "No face detected — please face the camera"}
    if len(faces) > 1:
        return {"ok": False, "reason": "Multiple faces detected — only one staff member should be in frame"}

    face = faces[0]
    x1, y1, x2, y2 = face.bbox
    bbox = [
        float(max(0, min(w, x1))),
        float(max(0, min(h, y1))),
        float(max(0, min(w, x2))),
        float(max(0, min(h, y2))),
    ]

    if face.det_score < MIN_DET_SCORE:
        return {"ok": False, "reason": "Face not clear enough — ensure good lighting", "bbox": bbox}

    face_w = x2 - x1
    if face_w / w < MIN_FACE_WIDTH_RATIO:
        return {"ok": False, "reason": "Move slightly closer to the camera", "bbox": bbox}

    x1c, y1c, x2c, y2c = [int(v) for v in bbox]
    crop = img_bgr[y1c:y2c, x1c:x2c]
    if crop.size == 0:
        return {"ok": False, "reason": "Face crop invalid — please try again", "bbox": bbox}

    blur = _blur_score(crop)
    if blur < BLUR_THRESHOLD:
        return {"ok": False, "reason": "Image slightly blurry — please hold still", "bbox": bbox}

    primary_emb = face.normed_embedding.astype(np.float32).tolist()
    photos = [{"embedding": primary_emb, "angle_label": "original"}]

    # Auto-augmentation 1: Horizontal Flip (Mirrored perspective)
    try:
        img_flip = cv2.flip(img_bgr, 1)
        flip_faces = face_app.get(img_flip)
        if flip_faces:
            photos.append({
                "embedding": flip_faces[0].normed_embedding.astype(np.float32).tolist(),
                "angle_label": "augmented_flip"
            })
    except Exception:
        pass

    # Auto-augmentation 2: Enhanced Contrast / Brightness adjustment
    try:
        img_bright = cv2.convertScaleAbs(img_bgr, alpha=1.12, beta=8)
        bright_faces = face_app.get(img_bright)
        if bright_faces:
            photos.append({
                "embedding": bright_faces[0].normed_embedding.astype(np.float32).tolist(),
                "angle_label": "augmented_bright"
            })
    except Exception:
        pass

    return {
        "ok": True,
        "photos": photos,
        "det_score": float(face.det_score),
        "blur": float(blur),
        "bbox": bbox
    }


def validate_and_embed(img_bgr: np.ndarray) -> dict:
    """Legacy helper for multi-step enroll compatibility."""
    res = validate_and_embed_single(img_bgr)
    if not res["ok"]:
        return res
    return {
        "ok": True,
        "embedding": res["photos"][0]["embedding"],
        "det_score": res["det_score"],
        "blur": res["blur"],
        "bbox": res["bbox"]
    }


def detect_and_embed_all(img_bgr: np.ndarray) -> list[dict]:
    """Detect every face in a frame and embed each one for live scanner."""
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
