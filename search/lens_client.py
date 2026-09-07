"""
SerpApi Google Lens Client
---------------------------
Sends a public image URL to SerpApi's Google Lens engine, which returns
visually-similar images/pages from across the web. We then filter those
raw results down to known social media platforms, since Lens itself has
no concept of "social post" — it just returns general visual matches.
"""

import os

import requests

SERPAPI_ENDPOINT = "https://serpapi.com/search"

from config.config import SOCIAL_DOMAINS

# Platforms we care about for this pipeline, ranked by how likely they
# are to have public, scrapeable content without hitting a login wall.


class LensClient:
    def __init__(self, api_key: str | None = None):
        """
        api_key: your SerpApi key. If not passed explicitly, reads
                 the SERPAPI_KEY environment variable.
        """
        self.api_key = api_key or os.environ.get("SERPAPI_KEY")
        if not self.api_key:
            raise ValueError(
                "No SerpApi key found. Pass api_key= explicitly or "
                "set the SERPAPI_KEY environment variable."
            )

    def search(self, image_url: str) -> list[dict]:
        """
        Run a Google Lens reverse-image search on a public image URL.

        Parameters
        ----------
        image_url : str
            Publicly accessible URL of the image to search (e.g. from
            ImgBBClient.upload()).

        Returns
        -------
        list[dict]
            Raw "visual matches" results from SerpApi, each typically
            containing keys like: title, link, source, thumbnail,
            image (dict with 'link').
        """
        params = {
            "engine": "google_lens",
            "url": image_url,
            "api_key": self.api_key,
        }

        response = requests.get(SERPAPI_ENDPOINT, params=params, timeout=30)
        if response.status_code != 200:
            raise ValueError(
                f"SerpApi request failed (HTTP {response.status_code}): {response.text}"
            )

        data = response.json()
        if "error" in data:
            raise ValueError(f"SerpApi returned an error: {data['error']}")

        return data.get("visual_matches", [])

    @staticmethod
    def filter_social_results(
        results: list[dict], domains: list[str] = SOCIAL_DOMAINS
    ) -> list[dict]:
        """
        Keep only results whose 'link' (source page URL) belongs to one
        of the known social media domains.
        """
        filtered = []
        for result in results:
            link = result.get("link", "")
            if any(domain in link for domain in domains):
                filtered.append(result)
        return filtered


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python lens_client.py <public_image_url>")
        sys.exit(1)

    client = LensClient()
    all_results = client.search(sys.argv[1])
    social_results = client.filter_social_results(all_results)

    print(f"Total visual matches: {len(all_results)}")
    print(f"Social media matches: {len(social_results)}")
    for r in social_results:
        print(f" - {r.get('source', '?')}: {r.get('link')}")
