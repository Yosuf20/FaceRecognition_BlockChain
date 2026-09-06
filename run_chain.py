"""
Blockchain CLI: anchor / verify / tamper
------------------------------------------
Usage:
    python run_chain.py anchor <match.json>
    python run_chain.py verify <match.json>
    python run_chain.py tamper <match.json>

<match.json> is expected to be a JSON file containing at least the
fields: platform, post_url, author, text, image_sha256 -- i.e. the
output of Stage 2's find_best_match().

For 'verify' and 'tamper', the post is re-fetched live from post_url
to get its current text/author, so this catches real edits made to
the post since anchoring (not just a local file check).
"""

import json
import sys

from chain.anchor import build_canonical_record, hash_record
from chain.local_chain import LocalChain
from search.post_extractor import extract_post


def cmd_anchor(match: dict):
    record = build_canonical_record(match)
    record_hash = hash_record(record)

    chain = LocalChain()
    block = chain.anchor(record_hash)

    print("Anchored new record on local chain.")
    print(f"  Record        : {record}")
    print(f"  Record hash   : {record_hash}")
    print(f"  Block #       : {block['index']}")
    print(f"  Block hash    : {block['block_hash']}")
    print(f"  Nonce         : {block['nonce']}")


from face.encoder import FaceEncoder, cosine_distance
import hashlib
import requests

def cmd_verify(match: dict, original_image_path: str):
    print(f"Re-fetching live post: {match['post_url']}")
    try:
        live_data = extract_post(match["post_url"], match.get("platform", "unknown"))
    except ValueError as e:
        print(f"FAIL: could not re-fetch the live post -> {e}")
        return

    live_record = {
        "platform": match.get("platform"),
        "post_url": match.get("post_url"),
        "author": live_data.get("author") or match.get("author"),
        "text": live_data.get("text") or match.get("text"),
        "image_sha256": match.get("image_sha256"),  # unchanged for now, checked below
    }

    # --- Image re-verification ---
    live_image_url = live_data.get("image_url") or match.get("image_url")
    if live_image_url:
        resp = requests.get(live_image_url, timeout=20)
        live_image_bytes = resp.content
        live_image_hash = hashlib.sha256(live_image_bytes).hexdigest()

        if live_image_hash == match.get("image_sha256"):
            print("  Image check  : PASS (raw file hash identical, byte-for-byte)")
        else:
            print("  Image check  : raw hash differs -- checking face similarity instead...")
            with open("_live_check.jpg", "wb") as f:
                f.write(live_image_bytes)
            encoder = FaceEncoder()
            original_embedding = encoder.encode_image(original_image_path)["embedding"]
            try:
                live_embedding = encoder.encode_image("_live_check.jpg")["embedding"]
                distance = cosine_distance(original_embedding, live_embedding)
                if distance < 0.35:
                    print(f"  Image check  : face still matches (distance={distance:.4f}), "
                          f"but the file itself was re-saved/modified since anchoring")
                else:
                    print(f"  Image check  : FAIL -- face no longer matches (distance={distance:.4f}). "
                          f"Image was likely swapped.")
            except ValueError:
                print("  Image check  : FAIL -- no face found in the current live image")
        live_record["image_sha256"] = live_image_hash
    else:
        print("  Image check  : skipped (no image_url available)")

    live_hash = hash_record(live_record)
    chain = LocalChain()
    found_block = chain.lookup(live_hash)

    print(f"  Live record : {live_record}")
    print(f"  Live hash   : {live_hash}")
    if found_block:
        print(f"PASS: hash matches on-chain block #{found_block['index']}.")
    else:
        print("FAIL: hash not found on-chain (text/author/image changed since anchoring).")


def cmd_tamper(match: dict):
    # Demonstrate tamper-evidence: mutate the text field, show the new
    # hash doesn't exist on-chain.
    record = build_canonical_record(match)
    original_hash = hash_record(record)

    tampered_record = dict(record)
    original_text = tampered_record.get("text") or ""
    tampered_record["text"] = original_text[:-1] + "X" if original_text else "X"
    tampered_hash = hash_record(tampered_record)

    chain = LocalChain()
    original_found = chain.lookup(original_hash)
    tampered_found = chain.lookup(tampered_hash)

    print(f"  Original text : {original_text!r}")
    print(f"  Tampered text : {tampered_record['text']!r}")
    print(f"  Original hash : {original_hash} -> {'FOUND on-chain' if original_found else 'NOT FOUND'}")
    print(f"  Tampered hash : {tampered_hash} -> {'FOUND on-chain' if tampered_found else 'NOT FOUND'}")

    if original_found and not tampered_found:
        print("Tamper detected: a single-character change produced a completely "
              "different hash, which does not exist on-chain. Confirms tamper-evidence.")
    else:
        print("Unexpected result -- did you run 'anchor' on this record first?")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python run_chain.py <anchor|verify|tamper> <match.json>")
        sys.exit(1)

    command = sys.argv[1]
    match_file = sys.argv[2]

    with open(match_file, "r") as f:
        match_data = json.load(f)

    if command == "anchor":
        cmd_anchor(match_data)
    elif command == "verify":
        if len(sys.argv) < 4:
            print("Usage: python run_chain.py verify <match.json> <original_photo.jpg>")
            sys.exit(1)
        cmd_verify(match_data, sys.argv[3])
    elif command == "tamper":
        cmd_tamper(match_data)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
