"""Tool: return one category of Disruption Now brand doctrine from the local cache."""

from typing import Any

from ._common import BRAND_RULES_DIR, error, load_json

VALID_CATEGORIES = [
    "voice-principles",
    "the-gate",
    "anti-slop-catalog",
    "say-this-not-that",
    "mechanics",
    "where-the-brand-speaks",
    "logo-usage",
]


def get_brand_rule(category: str) -> dict[str, Any]:
    """Return the Disruption Now brand rules for one category, as parsed JSON.

    category: one of voice-principles, the-gate, anti-slop-catalog, say-this-not-that,
    mechanics, where-the-brand-speaks, logo-usage.
    On an unknown category returns {"error", "hint", "valid_categories"}.
    """
    normalized = (category or "").strip().lower().replace("_", "-").replace(" ", "-")
    if normalized not in VALID_CATEGORIES:
        return error(
            f"Unknown brand rule category '{category}'.",
            "Call get_brand_rule again with one of valid_categories.",
            valid_categories=VALID_CATEGORIES,
        )
    try:
        return load_json(BRAND_RULES_DIR / f"{normalized}.json")
    except FileNotFoundError:
        return error(f"Brand rule file for '{normalized}' is missing from the cache.", "Restore mcp_server/cache/brand-rules/.")
    except ValueError as exc:
        return error(f"Brand rule file for '{normalized}' is not valid JSON: {exc}", "Fix the JSON in mcp_server/cache/brand-rules/.")
