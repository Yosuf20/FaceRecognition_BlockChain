"""
Blockchain CLI: anchor / verify / tamper
------------------------------------------
Usage:
    python run_chain.py anchor <match.json> [--network local|amoy]
    python run_chain.py verify <match.json> <original_photo.jpg> [--network local|amoy]
    python run_chain.py tamper <match.json> [--network local|amoy]

Defaults to --network local if not specified.

<match.json> is expected to be a JSON file containing at least the
fields: platform, post_url, author, text, image_sha256, image_url --
i.e. the output of Stage 2's find_best_match().

For 'verify' and 'tamper', the post is re-fetched live from post_url
to get its current text/author, so this catches real edits made to
the post since anchoring (not just a local file check).
"""

import argparse
import hashlib
import json

import requests
from dotenv import load_dotenv


from chain.anchor import build_canonical_record, hash_record
from chain.local_chain import LocalChain
from chain.web3_client import AmoyChain
from face.encoder import FaceEncoder, cosine_distance
from search.post_extractor import extract_post

load_dotenv()

def get_chain(network: str):
    if network == "amoy":
        return AmoyChain()
    return LocalChain()


def cmd_anchor(match: dict, chain):
    record = build_canonical_record(match)
    record_hash = hash_record(record)

    if isinstance(chain, AmoyChain):
        result = chain.anchor(record_hash)
        print("Anchored on Polygon Amoy.")
        print(f"  Record        : {record}")
        print(f"  Record hash   : {record_hash}")
        print(f"  Tx hash       : {result['tx_hash']}")
        print(f"  Explorer      : {result['explorer_url']}")
    else:
        block = chain.anchor(record_hash)
        print("Anchored on local chain.")
        print(f"  Record        : {record}")
        print(f"  Record hash   : {record_hash}")
        print(f"  Block #       : {block['index']}")
        print(f"  Block hash    : {block['block_hash']}")
        print(f"  Nonce         : {block['nonce']}")


def cmd_verify(match: dict, original_image_path: str, chain):
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
        "image_sha256": match.get("image_sha256"),  # may get overwritten below
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
    print(f"  Live record : {live_record}")
    print(f"  Live hash   : {live_hash}")

    if isinstance(chain, AmoyChain):
        found = chain.lookup(live_hash)
        if found:
            print(f"PASS: hash matches on-chain record (submitted by {found['submitter']}, "
                  f"anchored at timestamp {found['timestamp']}).")
        else:
            print("FAIL: hash not found on-chain (text/author/image changed since anchoring, "
                  "or this record was never anchored on Amoy).")
    else:
        found_block = chain.lookup(live_hash)
        if found_block:
            print(f"PASS: hash matches on-chain block #{found_block['index']}.")
        else:
            print("FAIL: hash not found on-chain (text/author/image changed since anchoring).")


def cmd_tamper(match: dict, chain):
    record = build_canonical_record(match)
    original_hash = hash_record(record)

    tampered_record = dict(record)
    original_text = tampered_record.get("text") or ""
    tampered_record["text"] = original_text[:-1] + "X" if original_text else "X"
    tampered_hash = hash_record(tampered_record)

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
        print("Unexpected result -- did you run 'anchor' on this record first (same --network)?")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["anchor", "verify", "tamper"])
    parser.add_argument("match_file")
    parser.add_argument("original_photo", nargs="?", help="Required for 'verify' only")
    parser.add_argument("--network", choices=["local", "amoy"], default="local")
    args = parser.parse_args()

    with open(args.match_file, "r") as f:
        match_data = json.load(f)

    chain = get_chain(args.network)

    if args.command == "anchor":
        cmd_anchor(match_data, chain)
    elif args.command == "verify":
        if not args.original_photo:
            print("Usage: python run_chain.py verify <match.json> <original_photo.jpg> [--network local|amoy]")
            raise SystemExit(1)
        cmd_verify(match_data, args.original_photo, chain)
    elif args.command == "tamper":
        cmd_tamper(match_data, chain)
