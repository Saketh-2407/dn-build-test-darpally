"""Fetch each Disruption Now brand hub page and cache its article text verbatim.

Usage: python mcp_server/build_brand_cache.py
Adds "verbatim", "fetched_at" and a note to each file in mcp_server/cache/brand-rules/.
Every existing structured field is kept as it is.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

HUB_URL = "https://dn-brand-hub.netlify.app"
BRAND_RULES_DIR = Path(__file__).parent / "cache" / "brand-rules"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

PAGES = {
    "/brand/voice": "voice-principles.json",
    "/brand/voice/the-gate": "the-gate.json",
    "/brand/voice/anti-slop-catalog": "anti-slop-catalog.json",
    "/brand/voice/say-this-not-that": "say-this-not-that.json",
    "/brand/voice/mechanics": "mechanics.json",
    "/brand/voice/where-the-brand-speaks": "where-the-brand-speaks.json",
    "/guide/basics/logo-files": "logo-usage.json",
}

NOTE = "verbatim is the exact page text as fetched; the other fields are a structured index of it."
# Two files already have a "note" of their own; it is kept and ours goes here instead.
FALLBACK_NOTE_KEY = "verbatim_note"
ADDED_KEYS = ("verbatim", "fetched_at", "note", FALLBACK_NOTE_KEY)

# Site chrome and UI text inside or around <main> that is not article text.
DROP_TAGS = ["script", "style", "noscript", "template", "svg", "nav", "aside", "button", "form", "input"]
DROP_SELECTORS = [
    ".wip",  # "work in progress" banner
    "[class*=search-hud]",  # search overlay
    ".hc-top",  # hero eyebrow with the HUB-*.md source chip
    ".sa",  # share button ("Copied")
    "[aria-hidden=true]",
]
KEEP_READING_RE = re.compile(r"^\s*Keep reading\b")
BLOCK_TAGS = [
    "address", "article", "blockquote", "dd", "div", "dl", "dt", "figcaption", "figure",
    "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "ol",
    "p", "pre", "section", "table", "tr", "td", "th", "ul", "br",
]


def fetch_html(client: httpx.Client, url: str) -> str:
    response = client.get(url)
    response.raise_for_status()
    return response.text


def extract_article(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main")
    if main is None:
        return ""
    for tag in main.find_all(DROP_TAGS):
        tag.decompose()
    for selector in DROP_SELECTORS:
        for tag in main.select(selector):
            tag.decompose()
    for section in main.find_all("section"):
        if KEEP_READING_RE.match(section.get_text(" ", strip=True)):
            section.decompose()
    # One line per block element; inline elements keep the page's own spacing.
    for tag in main.find_all(BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")
    lines = (re.sub(r"[ \t\r\f\v ]+", " ", line).strip() for line in main.get_text().split("\n"))
    return "\n".join(line for line in lines if line)


def update_cache_file(path: Path, verbatim: str, fetched_at: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    # A rerun replaces what an earlier run added; a file's own note always stays.
    has_own_note = "note" in data and data["note"] != NOTE
    for key in ADDED_KEYS:
        if not (key == "note" and has_own_note):
            data.pop(key, None)
    note_key = FALLBACK_NOTE_KEY if has_own_note else "note"
    data["verbatim"] = verbatim
    data["fetched_at"] = fetched_at
    data[note_key] = NOTE
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    fetched: dict[str, tuple[str, str]] = {}
    with httpx.Client(headers=HEADERS, timeout=15.0, follow_redirects=True) as client:
        for page, filename in PAGES.items():
            url = HUB_URL + page
            text = extract_article(fetch_html(client, url))
            if not text:
                # Write nothing rather than a partial cache.
                sys.exit(f"No article text found at {url} (the page may be JavaScript-rendered). Nothing was written.")
            fetched[filename] = (text, datetime.now(timezone.utc).isoformat())
    for filename, (text, fetched_at) in fetched.items():
        update_cache_file(BRAND_RULES_DIR / filename, text, fetched_at)
        print(f"{len(text):>6} chars -> {BRAND_RULES_DIR / filename}")


if __name__ == "__main__":
    main()
