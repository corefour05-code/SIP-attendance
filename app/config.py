HOTEL_NAME = "Hotel"
HOTEL_SUBTITLE = "Staff Biometric Attendance & Shift Hours Portal"

# Face Detection & Quality Thresholds
MIN_DET_SCORE = 0.50
MIN_FACE_WIDTH_RATIO = 0.12  # Minimum face size in frame (12% width)
BLUR_THRESHOLD = 70.0        # Laplacian variance threshold for sharpness

# Matching Thresholds (ArcFace Cosine Similarity)
MATCH_THRESHOLD = 0.52
MATCH_MARGIN = 0.04

# Shift and Timezone Settings
DEFAULT_TIMEZONE_HOURS = 5
DEFAULT_TIMEZONE_MINUTES = 30  # Indian Standard Time (IST)

# Debounce between punch updates for the same staff member in seconds
PUNCH_DEBOUNCE_SECONDS = 20
