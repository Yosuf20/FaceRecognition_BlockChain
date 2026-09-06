"""
End-to-end runner for Stage 1 + Stage 2:

    face photo -> embedding -> upload -> Google Lens search ->
    filter to social domains -> re-verify candidates -> best match

Usage:
    python run_search.py path/to/photo.jpg

Requires environment variables (put these in a .env file, see .env.example):
    IMGBB_KEY
    SERPAPI_KEY
"""

import sys
import json
from dotenv import load_dotenv

from face.encoder import FaceEncoder
from search.imgbb_client import ImgBBClient
from search.lens_client import LensClient
from search.matcher import find_best_match

load_dotenv()


def main(image_path: str):
    print(f"[1/4] Encoding face from '{image_path}'...")
    encoder = FaceEncoder()
    original = encoder.encode_image(image_path)
    print(f"      -> {original['num_faces_detected']} face(s) found, "
          f"det_score={original['det_score']:.3f}")

    print("[2/4] Uploading image to ImgBB for a public URL...")
    imgbb = ImgBBClient()
    public_url = imgbb.upload(image_path)
    print(f"      -> {public_url}")

    print("[3/4] Running Google Lens reverse image search via SerpApi...")
    lens = LensClient()
    all_results = lens.search(public_url)
    social_results = lens.filter_social_results(all_results)
    print(f"      -> {len(all_results)} total matches, "
          f"{len(social_results)} on known social platforms")

    print("[4/4] Re-verifying candidates against the original face...")
    match = find_best_match(original["embedding"], social_results, encoder)

    if match is None:
        print("\nNo confirmed match found (no candidate passed the face-similarity threshold).")
        return

    print("\nBest match found:")
    for key in ("platform", "post_url", "author", "text", "distance", "image_sha256"):
        print(f"  {key}: {match.get(key)}")

    output_path = "match.json"
    with open(output_path, "w") as f:
        json.dump(match, f, indent=2)
    print(f"\nSaved match to '{output_path}' -- use this with run_chain.py")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_search.py <image_path>")
        sys.exit(1)
    main(sys.argv[1])
