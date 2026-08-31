import numpy as np

from app.db import db_session
from app.config import MATCH_THRESHOLD, MATCH_MARGIN

EMBEDDING_DIM = 512


class _Gallery:
    """In-memory embedding cache for the live scanner.

    Rebuilding this from the database and matching against it in a Python
    loop on every single scanned frame was the main source of per-frame lag.
    Loaded once at startup and refreshed only when enrollment actually
    changes (enroll / recapture / delete), not on every scan.
    """

    def __init__(self):
        self.ids: list[str] = []
        self.names: list[str] = []
        self.id_arr = np.array([], dtype=object)
        self.matrix = np.zeros((0, EMBEDDING_DIM), dtype=np.float32)

    def reload(self):
        with db_session() as conn:
            rows = conn.execute(
                """
                SELECT e.student_id, e.embedding, s.name
                FROM embeddings e
                JOIN students s ON s.student_id = e.student_id
                """
            ).fetchall()

        if not rows:
            self.ids, self.names = [], []
            self.id_arr = np.array([], dtype=object)
            self.matrix = np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
            return

        self.ids = [row["student_id"] for row in rows]
        self.names = [row["name"] for row in rows]
        self.id_arr = np.array(self.ids, dtype=object)
        self.matrix = np.vstack(
            [np.frombuffer(row["embedding"], dtype=np.float32) for row in rows]
        ).astype(np.float32)


_gallery = _Gallery()


def reload_gallery():
    """Call after any enrollment change (enroll / recapture / delete)."""
    _gallery.reload()


def match_embedding(embedding: list[float]) -> dict | None:
    """Match a query embedding against the cached gallery via one vectorized
    cosine-similarity pass (embeddings are L2-normalized, so this is a plain
    dot product).

    Requires the best match to clear an absolute similarity threshold AND
    lead the best-scoring row of any *other* identity by a margin, to avoid
    false matches between similar-looking faces or near-duplicate enrollments.
    """
    if _gallery.matrix.shape[0] == 0:
        return None

    query = np.asarray(embedding, dtype=np.float32)
    scores = _gallery.matrix @ query

    best_idx = int(np.argmax(scores))
    best_score = float(scores[best_idx])
    best_id = _gallery.ids[best_idx]
    best_name = _gallery.names[best_idx]

    other_mask = _gallery.id_arr != best_id
    runner_up = float(scores[other_mask].max()) if other_mask.any() else -1.0

    if best_score < MATCH_THRESHOLD or (best_score - runner_up) < MATCH_MARGIN:
        return None

    return {
        "student_id": best_id,
        "name": best_name,
        "similarity": best_score,
        "margin": best_score - runner_up,
    }
