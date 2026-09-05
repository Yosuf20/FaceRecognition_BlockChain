"""
Matcher
-------
Orchestrates Stage 2 end-to-end:

  original face embedding
      + list of candidate social posts (from LensClient + post_extractor)
      -> download each candidate's image
      -> encode with the SAME FaceEncoder used on the original
      -> compute cosine distance vs. the original embedding
      -> keep candidates under a distance threshold
      -> return the best (lowest-distance) match

This re-verification step exists because Google Lens results are only
"visually similar" in a general sense (pose, lighting, background) -- not
face-verified. Without this step we'd get false positives (e.g. a
different person captured in a similar pose/angle).
"""

import os
import tempfile

import requests

from face.encoder import FaceEncoder, cosine_distance
from search.post_extractor import extract_post

DEFAULT_THRESHOLD = 0.35  # same convention as the reference implementation


def _download_image(url: str) -> str:
    """Download an image URL to a temp file, return the local path."""
    response = requests.get(url, timeout=20)
    if response.status_code != 200:
        raise ValueError(f"Failed to download image '{url}' (HTTP {response.status_code})")

    suffix = ".jpg"
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(response.content)
    return path


def find_best_match(
    original_embedding,
    candidates: list[dict],
    encoder: FaceEncoder,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict | None:
    """
    Parameters
    ----------
    original_embedding : np.ndarray
        The 512-d embedding of the input face (from Stage 1).
    candidates : list[dict]
        Raw social-media results from LensClient.filter_social_results(),
        each expected to have at least a 'link' key (the post URL) and
        ideally a 'source' key (platform label).
    encoder : FaceEncoder
        The same encoder instance used for the original image, so
        embeddings are directly comparable.
    threshold : float
        Max cosine distance to accept as a genuine match.

    Returns
    -------
    dict | None
        The best-matching candidate's post metadata (platform, post_url,
        author, text, image_url) plus 'distance' and 'image_sha256',
        or None if no candidate passed the threshold.
    """
    import hashlib

    best_match = None
    best_distance = float("inf")

    for candidate in candidates:
        post_url = candidate.get("link")
        platform = candidate.get("source", "unknown")
        if not post_url:
            continue

        try:
            post_data = extract_post(post_url, platform)
        except ValueError:
            continue  # page fetch failed, skip this candidate

        if not post_data.get("image_url"):
            continue  # nothing to re-verify against, skip

        try:
            local_path = _download_image(post_data["image_url"])
        except ValueError:
            continue

        try:
            candidate_result = encoder.encode_image(local_path)
        except ValueError:
            continue  # no face found in candidate image, skip
        finally:
            if os.path.exists(local_path):
                with open(local_path, "rb") as f:
                    image_bytes = f.read()
                os.remove(local_path)

        distance = cosine_distance(original_embedding, candidate_result["embedding"])

        if distance < threshold and distance < best_distance:
            best_distance = distance
            best_match = {
                **post_data,
                "distance": distance,
                "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
            }

    return best_match
