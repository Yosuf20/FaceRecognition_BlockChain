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


DEBUG_DIR = "debug_candidates"  # where downloaded candidate images are kept for inspection


def _download_image(url: str, debug_index: int | None = None) -> str:
    """
    Download an image URL to disk, return the local path.

    If debug_index is given, saves visibly into DEBUG_DIR/candidate_<i>.jpg
    (kept, not deleted) so you can open it and eyeball what was actually
    downloaded. If debug_index is None, saves to a normal OS temp file
    instead (old behavior).
    """
    response = requests.get(url, timeout=20)
    if response.status_code != 200:
        raise ValueError(f"Failed to download image '{url}' (HTTP {response.status_code})")

    if debug_index is not None:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        path = os.path.join(DEBUG_DIR, f"candidate_{debug_index}.jpg")
        with open(path, "wb") as f:
            f.write(response.content)
        return path

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

    for i, candidate in enumerate(candidates, 1):
        post_url = candidate.get("link")
        platform = candidate.get("source", "unknown")
        if not post_url:
            print(f"  [{i}] skip: no post URL in candidate")
            continue

        # Prefer SerpApi's own matched image for re-verification -- this is
        # the actual image Google Lens judged visually similar, and it's
        # reliably fetchable (unlike scraping Reddit/Instagram pages, which
        # often serve bot-blocked/login-walled HTML with no real og:image).
        reverify_image_url = candidate.get("thumbnail") or (
            candidate.get("image", {}).get("link") if isinstance(candidate.get("image"), dict) else None
        )

        # Page scraping is now only used for metadata (author/text) -- if it
        # fails, we still proceed using SerpApi's own title/source as a
        # fallback, since a failed scrape shouldn't block re-verification.
        try:
            post_data = extract_post(post_url, platform)
        except ValueError as e:
            print(f"  [{i}] note: page scrape failed, using SerpApi metadata instead -> {e}")
            post_data = {
                "platform": platform,
                "post_url": post_url,
                "author": candidate.get("source"),
                "text": candidate.get("title"),
                "image_url": None,
            }

        # If scraping didn't find an image either, that's fine now --
        # fall back further to SerpApi's thumbnail already resolved above.
        if not post_data.get("image_url"):
            post_data["image_url"] = reverify_image_url

        if not reverify_image_url:
            print(f"  [{i}] skip: no usable image found (page or SerpApi) for {post_url}")
            continue

        try:
            local_path = _download_image(reverify_image_url, debug_index=i)
            print(f"  [{i}] saved candidate image -> {local_path}  (source: {reverify_image_url})")
        except ValueError as e:
            print(f"  [{i}] skip: image download failed -> {e}")
            continue

        try:
            candidate_result = encoder.encode_image(local_path)
        except ValueError as e:
            print(f"  [{i}] skip: no face detected in candidate image -> {e}")
            continue
        finally:
            # NOTE: debug images are kept on disk (see DEBUG_DIR) so you can
            # open them and confirm what was actually downloaded. They are
            # NOT deleted here anymore -- clean up DEBUG_DIR manually when done.
            if os.path.exists(local_path):
                with open(local_path, "rb") as f:
                    image_bytes = f.read()

        distance = cosine_distance(original_embedding, candidate_result["embedding"])
        print(f"  [{i}] {platform} {post_url} -> distance={distance:.4f}")

        if distance < threshold and distance < best_distance:
            best_distance = distance
            best_match = {
                **post_data,
                "distance": distance,
                "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
            }

    return best_match
