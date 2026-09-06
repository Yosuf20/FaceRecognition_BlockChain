"""
Canonical Record & Hashing
--------------------------
Turns a Stage 2 match result into a deterministic JSON record and a
SHA-256 fingerprint of it. "Deterministic" matters: the same logical
data must always produce the exact same hash, regardless of dict
insertion order -- hence sort_keys=True.

Only this hash (+ the public post URL) ever goes on-chain. The raw
image/text itself is never stored on-chain, only its fingerprint.
"""

import hashlib
import json

# Fields we commit to the canonical record. Anything not listed here
# (e.g. distance score, embedding) is excluded on purpose -- those are
# our internal confidence metrics, not part of "what we're proving
# about the post itself".
RECORD_FIELDS = ["platform", "post_url", "author", "text", "image_sha256"]


def build_canonical_record(match: dict) -> dict:
    """
    Extract only the stable, provable fields from a Stage 2 match dict.
    Missing fields become None rather than being omitted, so the record
    shape is always consistent.
    """
    return {field: match.get(field) for field in RECORD_FIELDS}


def canonical_json(record: dict) -> str:
    """
    Serialize a record with sorted keys and no extra whitespace, so the
    same data always produces byte-identical JSON.
    """
    return json.dumps(record, sort_keys=True, separators=(",", ":"))


def hash_record(record: dict) -> str:
    """Return the SHA-256 hex digest of a record's canonical JSON form."""
    return hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()


if __name__ == "__main__":
    # Quick self-test with a fake match
    example = {
        "platform": "reddit",
        "post_url": "https://www.reddit.com/r/Presidents/comments/184odwq/",
        "author": "some_user",
        "text": "Who was a better president...",
        "image_sha256": "6e0e0d895e53b62decb4e0063615457029b94cb7181a91f4d26426a9cb3b541c",
        "distance": 0.035,  # intentionally NOT part of the canonical record
    }
    record = build_canonical_record(example)
    print("Canonical record:", record)
    print("Canonical JSON  :", canonical_json(record))
    print("SHA-256 hash    :", hash_record(record))
