MIN_DET_SCORE = 0.5
MIN_FACE_WIDTH_RATIO = 0.15
BLUR_THRESHOLD = 80.0  # matches the reference repo's BLUR_LAPLACIAN_VAR_THRESHOLD

ANGLE_LABELS = ["front", "left", "right", "up", "down"]
ANGLE_INSTRUCTIONS = {
    "front": "Look straight at the camera",
    "left": "Turn your head slightly left",
    "right": "Turn your head slightly right",
    "up": "Tilt your head slightly up",
    "down": "Tilt your head slightly down",
}

# Same values as the reference repo's COSINE_MATCH_THRESHOLD / MATCH_MARGIN
MATCH_THRESHOLD = 0.55
MATCH_MARGIN = 0.05
