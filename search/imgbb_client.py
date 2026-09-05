"""
ImgBB Client
------------
Reverse-image-search APIs (like SerpApi's Google Lens engine) need a
publicly reachable image URL, not a local file. This module uploads
a local image to ImgBB and returns that public URL.
"""

import base64
import os

import requests

IMGBB_UPLOAD_ENDPOINT = "https://api.imgbb.com/1/upload"


class ImgBBClient:
    def __init__(self, api_key: str | None = None):
        """
        api_key: your ImgBB API key. If not passed explicitly, reads
                 the IMGBB_KEY environment variable.
        """
        self.api_key = api_key or os.environ.get("IMGBB_API_KEY")
        if not self.api_key:
            raise ValueError(
                "No ImgBB API key found. Pass api_key= explicitly or "
                "set the IMGBB_KEY environment variable."
            )

    def upload(self, image_path: str, expiration_seconds: int | None = None) -> str:
        """
        Upload a local image file to ImgBB.

        Parameters
        ----------
        image_path : str
            Path to a local image file (jpg/png).
        expiration_seconds : int, optional
            If set, ImgBB auto-deletes the image after this many seconds
            (60 - 15552000). Leave unset to keep it permanently.

        Returns
        -------
        str
            The public direct image URL (e.g. https://i.ibb.co/xxxx/photo.jpg)

        Raises
        ------
        ValueError
            If the upload fails or the API returns an error.
        """
        with open(image_path, "rb") as f:
            encoded_image = base64.b64encode(f.read())

        payload = {
            "key": self.api_key,
            "image": encoded_image,
        }
        if expiration_seconds:
            payload["expiration"] = expiration_seconds

        response = requests.post(IMGBB_UPLOAD_ENDPOINT, data=payload, timeout=30)

        if response.status_code != 200:
            raise ValueError(
                f"ImgBB upload failed (HTTP {response.status_code}): {response.text}"
            )

        data = response.json()
        if not data.get("success"):
            raise ValueError(f"ImgBB upload failed: {data}")

        return data["data"]["url"]


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python imgbb_client.py <image_path>")
        sys.exit(1)

    client = ImgBBClient()
    url = client.upload(sys.argv[1])
    print(f"Uploaded. Public URL: {url}")
