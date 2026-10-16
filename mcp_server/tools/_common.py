"""Shared paths and helpers for the dn-repurposer tools."""

import json
from pathlib import Path
from typing import Any

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"
BRAND_RULES_DIR = CACHE_DIR / "brand-rules"
BLOG_INDEX_PATH = CACHE_DIR / "blog-index.json"
LINT_RULES_PATH = CACHE_DIR / "lint-rules.json"

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
