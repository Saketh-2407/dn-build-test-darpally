"""Tool: list posts from the cached Disruption Now blog index."""

import re
from typing import Any

from ._common import BLOG_INDEX_PATH, error, load_json

MAX_LIMIT = 100
SAMPLE_SIZE = 10


def _words(topic: str | None) -> list[str]:
    return [w for w in re.split(r"[\s\-]+", (topic or "").lower()) if w]


def _slug_text(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1].lower().replace("-", " ")


def _matches(posts: list[dict[str, str]], words: list[str]) -> list[dict[str, str]]:
    """Posts whose title or slug contains every word, most title hits first (index order breaks ties)."""
    scored = []
    for post in posts:
        title = post["title"].lower()
        haystack = f"{title} {_slug_text(post['url'])}"
        if all(word in haystack for word in words):
            scored.append((sum(word in title for word in words), post))
    scored.sort(key=lambda pair: -pair[0])
    return [post for _, post in scored]


def list_blog_posts(topic: str | None = None, limit: int = 20) -> dict[str, Any]:
    """List Disruption Now blog posts from the local index, optionally filtered by topic.

    topic: one or more words, case-insensitive (e.g. "agents", "hackathon nonprofits"). A post matches
    when every word appears in its title or its URL slug, in any order; posts with more of the words
    in the title come first.
    limit: maximum posts to return (1-100).
    Returns {"count", "total_matches", "posts": [{"title", "url"}]}. When a topic matches nothing,
    posts is empty and "sample_titles" lists available titles so you can retry with a better topic.
    """
    try:
        index = load_json(BLOG_INDEX_PATH)
    except FileNotFoundError:
        return error(
            "Blog index cache not found.",
            "Run `python mcp_server/build_index.py` to build mcp_server/cache/blog-index.json.",
        )
    except ValueError as exc:
        return error(f"Blog index cache is not valid JSON: {exc}", "Rebuild it with `python mcp_server/build_index.py`.")

    limit = max(1, min(int(limit), MAX_LIMIT))
    posts = index.get("posts", [])
    words = _words(topic)
    matches = _matches(posts, words) if words else posts

    result: dict[str, Any] = {
        "count": min(len(matches), limit),
        "total_matches": len(matches),
        "posts": matches[:limit],
    }
    if words and not matches:
        result["message"] = f"No post title or URL contains every word of '{topic}'. Try fewer or broader words."
        result["sample_titles"] = [p["title"] for p in posts[:SAMPLE_SIZE]]
    return result
