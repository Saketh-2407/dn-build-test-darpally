"""Tool: fetch one Disruption Now blog post and return its clean article text."""

import re
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from ._common import BLOG_INDEX_PATH, BLOG_URL_PREFIX, HEADERS, TIMEOUT_SECONDS, error, load_json

MIN_WORDS = 50
STRIP_TAGS = ["script", "style", "noscript", "template", "svg", "iframe", "nav", "footer", "aside", "form", "button"]
# Class/id tokens marking share bars, related-post rails, newsletter boxes, etc.
NOISE_TOKEN_RE = re.compile(r"share|social|related|newsletter|subscribe|comment|breadcrumb", re.I)
# Headings that start the back matter after the article body; that block and everything after it is dropped.
BACKMATTER_HEADING_RE = re.compile(r"^(frequently asked questions|faqs?|sources|references|related( posts| articles)?)$", re.I)
SOURCES_HEADING_RE = re.compile(r"^(sources|references)$", re.I)
BLOCK_TAGS = ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "figcaption", "caption", "tr", "div", "section"]


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _index_title(url: str) -> str | None:
    """The blog index has the clean listing title; the page <h1> is split across styled lines."""
    try:
        posts = load_json(BLOG_INDEX_PATH)["posts"]
    except (OSError, ValueError, KeyError):
        return None
    key = url.rstrip("/").lower()
    return next((p["title"] for p in posts if p["url"].rstrip("/").lower() == key), None)


def _h1_title(h1: Tag) -> str:
    """Join the <br>-separated parts of a headline with '. ' (no doubled punctuation)."""
    for br in h1.find_all("br"):
        br.replace_with("\n")
    parts = [_squash(part) for part in h1.get_text().split("\n") if part.strip()]
    title = ""
    for part in parts:
        if title:
            title += " " if title[-1] in ".?!:;" else ". "
        title += part
    return title


def _title(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return _h1_title(h1)
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"].strip()
    return soup.title.get_text(strip=True) if soup.title else ""


def _is_noise(tag: Tag) -> bool:
    tokens = list(tag.get("class") or []) + [tag.get("id") or ""]
    return any(NOISE_TOKEN_RE.search(token) for token in tokens if token)


def _section_heading(tag: Tag) -> str:
    heading = tag.find(["h2", "h3"]) if tag.name == "section" else None
    return heading.get_text(" ", strip=True) if heading else ""


def _sources(section: Tag) -> list[dict[str, str]]:
    sources = []
    for item in section.find_all("li") or section.find_all("a", href=True):
        link = item if item.name == "a" else item.find("a", href=True)
        text = _squash(item.get_text())
        if text:
            sources.append({"text": text, "href": urljoin(BLOG_URL_PREFIX, link["href"]) if link else ""})
    return sources


def _split_backmatter(root: Tag) -> list[dict[str, str]]:
    """Remove everything from the first back-matter section on (FAQ, Sources, author bio, CTA, Share).

    Returns the Sources list, which is kept as structured data rather than discarded.
    """
    start = next((s for s in root.find_all("section") if BACKMATTER_HEADING_RE.match(_section_heading(s))), None)
    if start is None:
        return []
    sources: list[dict[str, str]] = []
    for block in [start, *start.find_next_siblings()]:
        if not sources and SOURCES_HEADING_RE.match(_section_heading(block)):
            sources = _sources(block)
        block.decompose()
    return sources


def _lede(root: Tag) -> list[str]:
    """Hook/standfirst paragraphs live in the article's hero <header>; keep them before the header is stripped."""
    header = root.find("header")
    if not header:
        return []
    return [
        p.get_text(" ", strip=True)
        for p in header.find_all("p")
        if "sr-only" not in (p.get("class") or []) and p.get_text(strip=True)
    ]


def _clean_text(root: Tag) -> str:
    for br in root.find_all("br"):
        br.replace_with("\n")
    for block in root.find_all(BLOCK_TAGS):
        block.insert_before("\n")
        block.insert_after("\n")
    lines = (re.sub(r"[ \t ]+", " ", line).strip() for line in root.get_text().splitlines())
    return "\n".join(line for line in lines if line)


def extract_article(html: str) -> tuple[str, str, list[dict[str, str]]]:
    """Return (h1 title, clean body text, sources) from a post page."""
    soup = BeautifulSoup(html, "html.parser")
    title = _title(soup)
    root = soup.find("article") or soup.find("main") or soup.body or soup
    lede = _lede(root)

    for tag in root.find_all(STRIP_TAGS + ["header"]):
        tag.decompose()
    for tag in root.find_all(_is_noise):
        tag.decompose()
    sources = _split_backmatter(root)

    body = _clean_text(root)
    return title, "\n".join(lede + [body]).strip(), sources


async def fetch_blog_post(url: str) -> dict[str, Any]:
    """Fetch a Disruption Now blog post and return its title and clean body text.

    url: must start with https://disruptionnow.com/blog/ (get URLs from list_blog_posts).
    Returns {"title", "url", "text", "word_count", "sources"}. text is the article body only:
    navigation, share bars, key-takeaway asides, FAQ, author bio and calls to action are removed.
    sources is the post's cited sources as [{"text", "href"}] (empty if it has none), useful for
    checking any number before it goes into a draft. On failure returns {"error", "hint"}.
    """
    url = (url or "").strip()
    if not url.startswith(BLOG_URL_PREFIX) or not url[len(BLOG_URL_PREFIX):].strip("/"):
        return error(
            f"Refusing to fetch '{url}': only Disruption Now blog post URLs are allowed.",
            f"Pass a full post URL starting with {BLOG_URL_PREFIX}<slug>. Use list_blog_posts to find one.",
        )

    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(url)
    except httpx.TimeoutException:
        return error(f"Timed out after {TIMEOUT_SECONDS:.0f}s fetching {url}.", "The site may be slow; retry once, then pick another post.")
    except httpx.HTTPError as exc:
        return error(f"Network error fetching {url}: {type(exc).__name__}: {exc}", "Check connectivity and retry.")

    if response.status_code != 200:
        return error(
            f"{url} returned HTTP {response.status_code}.",
            "The post may have moved or been removed. Call list_blog_posts to get a current URL.",
            status_code=response.status_code,
        )

    try:
        h1_title, text, sources = extract_article(response.text)
    except Exception as exc:  # parser surprises should not crash the server
        return error(f"Could not parse {url}: {type(exc).__name__}: {exc}", "Try a different post; the page layout may be unusual.")

    title = _index_title(url) or _index_title(str(response.url)) or h1_title
    word_count = len(text.split())
    if word_count < MIN_WORDS:
        return error(
            f"Extracted only {word_count} words from {url}; the article body looks empty.",
            "The page may be rendered client-side or have an unusual layout. Try a different post.",
            title=title,
        )
    return {"title": title, "url": str(response.url), "text": text, "word_count": word_count, "sources": sources}
