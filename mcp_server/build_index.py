"""Fetch the Disruption Now blog listing and cache post titles + URLs.

Usage: python mcp_server/build_index.py
Writes mcp_server/cache/blog-index.json.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

BLOG_URL = "https://disruptionnow.com/blog"
OUTPUT_PATH = Path(__file__).parent / "cache" / "blog-index.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Exactly one path segment after /blog/, e.g. /blog/my-post-slug
POST_PATH_RE = re.compile(r"^/blog/([^/]+)/?$")
# Slugs that are listing pages rather than posts
NON_POST_SLUGS = {"page", "category", "categories", "tag", "tags", "author", "archive", "feed", "rss"}


def is_post_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.netloc and parsed.netloc.lower().removeprefix("www.") != "disruptionnow.com":
        return False
    if parsed.query and re.search(r"(^|&)(page|offset|category|tag)=", parsed.query):
        return False
    match = POST_PATH_RE.match(parsed.path)
    if not match:
        return False
    slug = match.group(1).lower()
    return slug not in NON_POST_SLUGS and not slug.isdigit()


def normalize(url: str) -> str:
    parsed = urlparse(url)
    return f"https://disruptionnow.com{parsed.path.rstrip('/')}"


def fetch_html() -> str:
    with httpx.Client(headers=HEADERS, timeout=15.0, follow_redirects=True) as client:
        response = client.get(BLOG_URL)
        response.raise_for_status()
        return response.text


def card_title(anchor) -> str:
    # Post links wrap whole cards (category, read time, excerpt), so prefer the card's heading.
    heading = anchor.find(["h1", "h2", "h3", "h4"])
    if heading:
        return heading.get_text(" ", strip=True)
    return anchor.get_text(" ", strip=True)


def extract_posts(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    posts: dict[str, str] = {}
    for anchor in soup.find_all("a", href=True):
        absolute = urljoin(BLOG_URL, anchor["href"].strip())
        if not is_post_url(absolute):
            continue
        url = normalize(absolute)
        title = card_title(anchor)
        if url not in posts:
            posts[url] = title
        elif not posts[url] and title:
            posts[url] = title
    return [{"title": title, "url": url} for url, title in posts.items()]


def main() -> None:
    posts = extract_posts(fetch_html())
    index = {
        "source": BLOG_URL,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(posts),
        "posts": posts,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Found {len(posts)} posts -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
