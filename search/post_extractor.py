"""
Post Extractor
--------------
Given a candidate social media post URL, scrape its metadata using
OpenGraph / Twitter Card tags (og:title, og:description, og:image, etc).
Most platforms expose these publicly even without login, since they're
meant for link-preview cards (e.g. when you paste a link into iMessage
or Slack).
"""

import requests
from bs4 import BeautifulSoup

HEADERS = {
    # A normal browser User-Agent avoids some basic bot-blocking.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


def _get_meta(soup: BeautifulSoup, *keys: str) -> str | None:
    """Try multiple possible meta tag names/properties, return first hit."""
    for key in keys:
        tag = soup.find("meta", property=key) or soup.find("meta", attrs={"name": key})
        if tag and tag.get("content"):
            return tag["content"]
    return None


def extract_post(url: str, platform: str) -> dict:
    """
    Scrape a candidate post URL for metadata.

    Parameters
    ----------
    url : str
        The post/page URL to scrape.
    platform : str
        A short label for which platform this came from (e.g. "instagram"),
        used only for bookkeeping/records, not for changing scrape logic.

    Returns
    -------
    dict
        {
            "platform": str,
            "post_url": str,
            "author": str | None,
            "text": str | None,
            "image_url": str | None,
        }
        Fields will be None if they couldn't be found — this is expected
        for some platforms/pages and should be handled gracefully by the
        caller (e.g. skip candidates with no image_url, since we need an
        image to re-verify the face).

    Raises
    ------
    ValueError
        If the page couldn't be fetched at all (network/HTTP error).
    """
    response = requests.get(url, headers=HEADERS, timeout=15)
    if response.status_code != 200:
        raise ValueError(f"Failed to fetch '{url}' (HTTP {response.status_code})")

    if "reddit.com" in url:
        return _extract_reddit(url)

    soup = BeautifulSoup(response.text, "html.parser")

    title = _get_meta(soup, "og:title", "twitter:title")
    description = _get_meta(soup, "og:description", "twitter:description")
    image_url = _get_meta(soup, "og:image", "twitter:image")
    site_name = _get_meta(soup, "og:site_name")

    # Best-effort "author" extraction — varies a lot by platform, so this
    # is intentionally simple; falls back to site name or None.
    author = site_name or title

    return {
        "platform": platform,
        "post_url": url,
        "author": author,
        "text": description or title,
        "image_url": image_url,
    }

def _extract_reddit(url: str) -> dict:
    """
    Reddit exposes a clean public JSON API for any post: just append
    '.json' to the URL. No auth needed, far more reliable than scraping
    Reddit's HTML (which serves bot-blocked pages with no og:image).
    """
    json_url = url.rstrip("/") + ".json"
    response = requests.get(json_url, headers=HEADERS, timeout=15)
    if response.status_code != 200:
        raise ValueError(f"Reddit JSON fetch failed (HTTP {response.status_code})")

    data = response.json()
    post = data[0]["data"]["children"][0]["data"]

    return {
        "platform": "reddit",
        "post_url": url,
        "author": post.get("author"),
        "text": post.get("title"),
        "image_url": post.get("url_overridden_by_dest") or post.get("thumbnail"),
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python post_extractor.py <post_url> [platform]")
        sys.exit(1)

    post_url = sys.argv[1]
    platform_label = sys.argv[2] if len(sys.argv) > 2 else "unknown"

    result = extract_post(post_url, platform_label)
    for k, v in result.items():
        print(f"{k}: {v}")
