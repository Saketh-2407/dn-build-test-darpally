"""Tool: prove every quoted fact appears word-for-word in the source blog post."""

import difflib
import re
import unicodedata
from typing import Any

from ._common import error
from .fetch_blog_post import fetch_blog_post

# NFKC leaves these alone; map them so typography differences never cause a false miss.
CHAR_MAP = str.maketrans({
    **dict.fromkeys("‘’‚‛′", "'"),  # curly/low/reversed single quotes, prime
    **dict.fromkeys("“”„‟″", '"'),  # curly/low/reversed double quotes, double prime
    **dict.fromkeys("‐‑‒–—―−", "-"),  # hyphens, figure/en/em dash, bar, minus
})
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def normalize(text: str) -> str:
    """NFKC, straight quotes, every dash to '-', collapsed whitespace, lowercase."""
    text = unicodedata.normalize("NFKC", text).translate(CHAR_MAP)
    return re.sub(r"\s+", " ", text).strip().lower()


def _sentences(body: str) -> list[str]:
    return [s.strip() for line in body.splitlines() for s in SENTENCE_SPLIT_RE.split(line) if s.strip()]


def _closest(quote: str, sentences: list[tuple[str, str]]) -> tuple[str, float]:
    """The body sentence most similar to the normalized quote, with its similarity ratio (0-1)."""
    best, best_ratio = "", 0.0
    for original, normalized in sentences:
        ratio = difflib.SequenceMatcher(None, quote, normalized).ratio()
        if ratio > best_ratio:
            best, best_ratio = original, ratio
    return best, round(best_ratio, 3)


def check_quotes(body: str, quotes: list[str]) -> dict[str, Any]:
    """Pure matching step: which quotes are substrings of the body after normalization."""
    normalized_body = normalize(body)
    sentences = [(s, normalize(s)) for s in _sentences(body)]
    found, missing = [], []
    for quote in quotes:
        normalized_quote = normalize(quote)
        if normalized_quote in normalized_body:
            found.append(quote)
        else:
            closest, similarity = _closest(normalized_quote, sentences)
            missing.append({"quote": quote, "closest_match": closest, "similarity": similarity})
    return {"checked": len(quotes), "found": found, "missing": missing}


async def verify_quotes(url: str, quotes: list[str]) -> dict[str, Any]:
    """Check that every quote appears word-for-word in a Disruption Now blog post.

    url: the post URL (from list_blog_posts). The body is the same text fetch_blog_post returns,
    reused from its 15-minute cache when the post was already fetched this run.
    quotes: the exact source sentences or phrases a draft relies on.
    Matching ignores case, Unicode width forms, curly vs straight quotes, dash variants (em, en,
    minus) and whitespace, but nothing else: a quote is found only if it is a substring of the body.
    Returns {"url", "checked", "found": [quote], "missing": [{"quote", "closest_match", "similarity"}]}.
    closest_match is the most similar body sentence, so a near-miss can be corrected to the real
    wording. On failure (no quotes, bad URL, fetch error) returns {"error", "hint"}.
    """
    if not isinstance(quotes, list) or not quotes:
        return error("No quotes to verify.", "Pass quotes as a non-empty list of exact source sentences from the post.")
    for i, quote in enumerate(quotes):
        if not isinstance(quote, str) or not quote.strip():
            return error(f"Quote {i} is empty or not a string.", "Remove it or replace it with the exact source wording.")

    post = await fetch_blog_post(url)
    if "error" in post:
        return post
    return {"url": post["url"], **check_quotes(post["text"], quotes)}
