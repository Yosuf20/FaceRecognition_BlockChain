"""
face/encoder.py — Stage 1: Face Identification & Encoding
==========================================================

This module wraps the **insightface** library (buffalo_l model) to provide
a simple, reusable interface for:

1. Detecting faces in an image.
2. Extracting a 512-dimensional embedding for the *primary* face.
3. Comparing two embeddings via cosine distance.

Design decisions
----------------
* **L2-normalisation** — InsightFace embeddings are already close to unit-norm,
  but explicitly normalising guarantees that dot-product == cosine similarity,
  which simplifies downstream comparisons and indexing (e.g. FAISS inner-product).
* **Largest-face heuristic** — When a photo contains multiple people we assume
  the subject of interest occupies the largest bounding box.  This is a
  reasonable default for ID-photo or portrait-style images.
* **Cosine distance** — Defined as ``1 − cos(a, b)``.  Range is [0.0, 2.0]:
  0.0 means the vectors are identical, 1.0 means orthogonal, 2.0 means
  diametrically opposite.  Thresholds around 0.4–0.6 are typical for
  same-person / different-person decisions.
"""

from __future__ import annotations

import sys
from typing import Tuple

import cv2
import numpy as np
from insightface.app import FaceAnalysis


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Return the cosine distance between two embedding vectors.

    Both vectors are L2-normalised internally so the caller does not need to
    pre-process them.

    Parameters
    ----------
    a, b : np.ndarray
        1-D embedding vectors (typically 512-d from InsightFace).

    Returns
    -------
    float
        ``1.0 - cosine_similarity(a, b)``.
        * 0.0 → identical direction (same person).
        * 1.0 → orthogonal (unrelated).
        * 2.0 → opposite direction.

    Raises
    ------
    ValueError
        If either vector has zero norm (cannot be normalised).
    """
    a = np.asarray(a, dtype=np.float64).ravel()
    b = np.asarray(b, dtype=np.float64).ravel()

    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0.0 or norm_b == 0.0:
        raise ValueError("Cannot compute cosine distance for a zero-length vector.")

    a = a / norm_a
    b = b / norm_b

    similarity = float(np.dot(a, b))
    # Clamp to [-1, 1] to guard against floating-point drift.
    similarity = max(-1.0, min(1.0, similarity))

    return 1.0 - similarity


# ---------------------------------------------------------------------------
# Core encoder
# ---------------------------------------------------------------------------

class FaceEncoder:
    """High-level wrapper around InsightFace for single-image face encoding.

    Usage
    -----
    >>> enc = FaceEncoder(ctx_id=-1)          # CPU
    >>> result = enc.encode_image("photo.jpg")
    >>> result["embedding"].shape
    (512,)

    Parameters
    ----------
    ctx_id : int
        Execution context.  ``-1`` selects the CPU; ``0`` (or higher) selects
        the corresponding CUDA GPU.
    det_size : tuple of int
        Input size ``(width, height)`` for the face detector.  Larger values
        improve detection of small faces at the cost of speed / memory.
    """

    def __init__(self, ctx_id: int = -1, det_size: Tuple[int, int] = (640, 640)) -> None:
        self._app = FaceAnalysis(
            name="buffalo_l",
            # Restrict to detection + recognition (skip landmarks / age / gender)
            allowed_modules=["detection", "recognition"],
        )
        self._app.prepare(ctx_id=ctx_id, det_size=det_size)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def encode_image(self, image_path: str) -> dict:
        """Detect faces in *image_path* and return an embedding for the primary face.

        The "primary" face is the one with the **largest bounding-box area** —
        a simple heuristic that works well when the subject of interest is
        front-and-centre in the frame.

        Parameters
        ----------
        image_path : str
            Path to an image file readable by OpenCV (JPEG, PNG, BMP, …).

        Returns
        -------
        dict
            ``embedding``   — ``np.ndarray`` of shape ``(512,)``, L2-normalised.
            ``bbox``        — ``list[float]`` with ``[x1, y1, x2, y2]``.
            ``det_score``   — ``float``, detector confidence in [0, 1].
            ``num_faces_detected`` — ``int``, total faces found in the image.

        Raises
        ------
        ValueError
            If the image cannot be read or no face is detected.
        """
        # --- Load image ---------------------------------------------------
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(
                f"Unable to read image at '{image_path}'. "
                "Check the path and file format."
            )

        # --- Detect & recognise -------------------------------------------
        faces = self._app.get(img)

        if not faces:
            raise ValueError(
                f"No face detected in '{image_path}'. "
                "Ensure the image contains a clearly visible face."
            )

        # --- Select primary face (largest bbox area) ----------------------
        def _bbox_area(face) -> float:
            x1, y1, x2, y2 = face.bbox
            return float((x2 - x1) * (y2 - y1))

        primary = max(faces, key=_bbox_area)

        # --- L2-normalise embedding ---------------------------------------
        embedding = primary.embedding.astype(np.float32)
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return {
            "embedding": embedding,
            "bbox": [float(c) for c in primary.bbox],
            "det_score": float(primary.det_score),
            "num_faces_detected": len(faces),
        }


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # if len(sys.argv) < 2:
    #     print(f"Usage: python -m face.encoder <image_path>")
    #     sys.exit(1)

    print(f"[*] Initialising FaceEncoder (CPU) …")
    encoder = FaceEncoder(ctx_id=-1)

    image_path = sys.argv[1]

    image_path1 = r"test_images\WIN_20251108_21_56_21_Pro.jpg"
    image_path2 = r"test_images\WIN_20260902_18_30_07_Pro.jpg"


    result1 = encoder.encode_image(image_path1)
    result2 = encoder.encode_image(image_path2)

    distance = cosine_distance(result1['embedding'], result2['embedding'])
    print(f"Distance between {image_path1} and {image_path2}: {distance}")

    # print(f"[*] Processing: {image_path}")
    # result = encoder.encode_image(image_path)

    

    emb = result["embedding"]
    print()
    print(f"  Faces detected : {result['num_faces_detected']}")
    print(f"  Selected bbox  : {result['bbox']}")
    print(f"  Det. confidence: {result['det_score']:.4f}")
    print(f"  Embedding shape: {emb.shape}")
    print(f"  Embedding norm : {np.linalg.norm(emb):.6f}")

    # --- Draw bounding box on the image and display ----------------------
    import os

    img = cv2.imread(image_path)
    x1, y1, x2, y2 = [int(c) for c in result["bbox"]]

    # Green rectangle, 2 px thick
    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)

    # Label with confidence score
    label = f"Face ({result['det_score']:.2f})"
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale, thickness = 0.7, 2
    (tw, th), baseline = cv2.getTextSize(label, font, font_scale, thickness)
    cv2.rectangle(img, (x1, y1 - th - 10), (x1 + tw + 4, y1), (0, 255, 0), -1)
    cv2.putText(img, label, (x1 + 2, y1 - 6), font, font_scale, (0, 0, 0), thickness)

    # Save annotated image next to the original
    base, ext = os.path.splitext(image_path)
    output_path = f"{base}_bbox{ext}"
    cv2.imwrite(output_path, img)
    print(f"\n  Saved annotated image -> {output_path}")

    # Show in a window (press any key to close)
    cv2.imshow("Face Detection", img)
    print("  Press any key in the image window to close ...")
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    print("\n[✓] Done.")