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


def cmd_verify(match: dict):
    # Re-fetch the LIVE post -- this is what makes 'verify' meaningful
    # rather than just re-reading the same local file.
    print(f"Re-fetching live post: {match['post_url']}")
    try:
        live_data = extract_post(match["post_url"], match.get("platform", "unknown"))
    except ValueError as e:
        print(f"FAIL: could not re-fetch the live post -> {e}")
        return

    # Build a fresh record using the ORIGINAL image_sha256 (the image
    # itself isn't re-downloaded here; author/text are what we check
    # for live edits since those are cheap to re-fetch and compare).
    live_record = {
        "platform": match.get("platform"),
        "post_url": match.get("post_url"),
        "author": live_data.get("author") or match.get("author"),
        "text": live_data.get("text") or match.get("text"),
        "image_sha256": match.get("image_sha256"),
    }
    live_hash = hash_record(live_record)

    chain = LocalChain()
    found_block = chain.lookup(live_hash)

    print(f"  Live record : {live_record}")
    print(f"  Live hash   : {live_hash}")

    if found_block:
        print(f"PASS: hash matches on-chain block #{found_block['index']}. Record unchanged.")
    else:
        print("FAIL: hash not found on-chain. Either the post was edited/deleted "
              "since anchoring, or this record was never anchored.")


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
        cmd_verify(match_data)
    elif command == "tamper":
        cmd_tamper(match_data)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
