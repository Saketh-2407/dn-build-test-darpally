"""Tool: list posts from the cached Disruption Now blog index."""

from typing import Any

from ._common import BLOG_INDEX_PATH, error, load_json

MAX_LIMIT = 100
SAMPLE_SIZE = 10


def list_blog_posts(topic: str | None = None, limit: int = 20) -> dict[str, Any]:
    """List Disruption Now blog posts from the local index, optionally filtered by topic.

    topic: case-insensitive substring matched against post titles (e.g. "agents", "MidwestCon").
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
    needle = (topic or "").strip().lower()
    matches = [p for p in posts if needle in p["title"].lower()] if needle else posts

    result: dict[str, Any] = {
        "count": min(len(matches), limit),
        "total_matches": len(matches),
        "posts": matches[:limit],
    }
    if needle and not matches:
        result["message"] = f"No post titles contain '{topic}'. Try a shorter or broader keyword."
        result["sample_titles"] = [p["title"] for p in posts[:SAMPLE_SIZE]]
    return result
