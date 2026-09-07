"""
Central configuration for HH-FaceChain.

Keeping tunable values here (rather than scattered across modules) makes
it easy to see and adjust the pipeline's behavior in one place, and keeps
README/code/behavior from drifting out of sync.
"""

# --- Stage 2: face re-verification ---

# Max cosine distance to accept a candidate as a genuine face match.
# Lower = stricter (fewer false positives, more false negatives).
# Higher = looser (more false positives, fewer false negatives).
FACE_MATCH_THRESHOLD = 0.25

# Social media domains to keep from raw Google Lens results.
SOCIAL_DOMAINS = [
    "instagram.com",
    "x.com",
    "twitter.com",
    "reddit.com",
    "pinterest.com",
    "facebook.com",
    "linkedin.com",
]

# --- Stage 3: local simulated blockchain ---

# Number of leading hex zeros required for a block hash to be "mined".
# Higher = more computational work per block (slower to mine).
LOCAL_CHAIN_DIFFICULTY_PREFIX = "000"

LOCAL_CHAIN_FILE = "data/local_chain.json"

# --- Stage 3: Polygon Amoy testnet ---

AMOY_CHAIN_ID = 80002