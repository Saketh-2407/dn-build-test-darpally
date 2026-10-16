"""Shared paths and helpers for the dn-repurposer tools."""

import json
import os
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = PROJECT_ROOT / "mcp_server" / "cache"
BRAND_RULES_DIR = CACHE_DIR / "brand-rules"
BLOG_INDEX_PATH = CACHE_DIR / "blog-index.json"
LINT_RULES_PATH = CACHE_DIR / "lint-rules.json"
DEFAULT_SAMPLES_DIR = PROJECT_ROOT / "samples"
SAMPLES_DIR_ENV = "DN_SAMPLES_DIR"

POST_CACHE_TTL_SECONDS = 15 * 60
_post_cache: dict[str, tuple[float, dict[str, Any]]] = {}

BLOG_URL_PREFIX = "https://disruptionnow.com/blog/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT_SECONDS = 15.0


def error(message: str, hint: str, **extra: Any) -> dict[str, Any]:
    """Structured, recoverable error: what went wrong plus what the agent should try next."""
    return {"error": message, "hint": hint, **extra}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def samples_dir() -> Path:
    """Where save_run writes; set DN_SAMPLES_DIR to redirect it (tests use a temp directory)."""
    override = os.environ.get(SAMPLES_DIR_ENV)
    return Path(override) if override else DEFAULT_SAMPLES_DIR


def _post_key(url: str) -> str:
    return url.strip().rstrip("/").lower()


def cached_post(url: str) -> dict[str, Any] | None:
    """A successful fetch_blog_post result from the last 15 minutes, so one run never refetches a post."""
    key = _post_key(url)
    entry = _post_cache.get(key)
    if entry is None:
        return None
    stored_at, post = entry
    if time.monotonic() - stored_at >= POST_CACHE_TTL_SECONDS:
        del _post_cache[key]
        return None
    return post


def cache_post(url: str, post: dict[str, Any]) -> None:
    _post_cache[_post_key(url)] = (time.monotonic(), post)
