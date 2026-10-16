"""Tool: fetch one Disruption Now blog post and return its clean article text."""

import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from ._common import BLOG_INDEX_PATH, BLOG_URL_PREFIX, HEADERS, TIMEOUT_SECONDS, cache_post, cached_post, error, load_json

MIN_WORDS = 50
STRIP_TAGS = ["script", "style", "noscript", "template", "svg", "iframe", "nav", "footer", "aside", "form", "button"]
# Class/id tokens marking share bars, related-post rails, newsletter boxes, etc.
NOISE_TOKEN_RE = re.compile(r"share|social|related|newsletter|subscribe|comment|breadcrumb", re.I)
# Headings that start the back matter after the article body; that block and everything after it is dropped.
BACKMATTER_HEADING_RE = re.compile(r"^(frequently asked questions|faqs?|sources|references|related( posts| articles)?)$", re.I)
SOURCES_HEADING_RE = re.compile(r"^(sources|references)$", re.I)
ISO_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
VISIBLE_DATE_FORMATS = ["%B %d, %Y", "%b %d, %Y", "%d %B %Y"]
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


def _meta(soup: BeautifulSoup, *keys: str) -> str | None:
    for key in keys:
        tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        if tag and tag.get("content", "").strip():
            return tag["content"].strip()
    return None


def _iso_date(value: str | None) -> str | None:
    """YYYY-MM-DD from an ISO timestamp or a visible date like 'August 29, 2025'."""
    value = _squash(value or "")
    match = ISO_DATE_RE.match(value)
    if match:
        return match.group(1)
    for fmt in VISIBLE_DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _visible_author(header: Tag | None) -> str | None:
    """The hero byline pairs the author's avatar with their name: <img alt="Name"><span>Name</span>."""
    for img in header.find_all("img", alt=True) if header else []:
        name = _squash(img["alt"])
        if name and img.parent and _squash(img.parent.get_text()) == name:
            return name
    return None


def _pop_byline(soup: BeautifulSoup, root: Tag) -> dict[str, str | None]:
    """Read the author, published date and author bio, then remove the bio card so it never reaches the body."""
    header = root.find("header")
    author = _meta(soup, "article:author", "author") or _visible_author(header)
    byline_time = header.find("time") if header else None
    published = (
        _iso_date(_meta(soup, "article:published_time", "datePublished"))
        or (_iso_date(byline_time.get("datetime")) if byline_time else None)
        or (_iso_date(byline_time.get_text()) if byline_time else None)
    )

    # The bio card opens with the author's name, followed by role and bio paragraphs.
    bio = None
    for tag in root.find_all(["p", "span", "strong", "h3", "h4"]) if author else []:
        if tag.find_parent("header") or _squash(tag.get_text()) != author:
            continue
        paragraphs = [_squash(p.get_text()) for p in tag.find_next_siblings("p")]
        if any(paragraphs):
            bio = "\n".join(p for p in paragraphs if p)
            tag.parent.decompose()
            break
    return {"author": author, "published": published, "bio": bio}


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


def extract_article(html: str) -> tuple[str, str, list[dict[str, str]], dict[str, str | None]]:
    """Return (h1 title, clean body text, sources, byline) from a post page."""
    soup = BeautifulSoup(html, "html.parser")
    title = _title(soup)
    root = soup.find("article") or soup.find("main") or soup.body or soup
    byline = _pop_byline(soup, root)
    lede = _lede(root)

    for tag in root.find_all(STRIP_TAGS + ["header"]):
        tag.decompose()
    for tag in root.find_all(_is_noise):
        tag.decompose()
    sources = _split_backmatter(root)

    body = _clean_text(root)
    return title, "\n".join(lede + [body]).strip(), sources, byline


async def fetch_blog_post(url: str) -> dict[str, Any]:
    """Fetch a Disruption Now blog post and return its title and clean body text.

    url: must start with https://disruptionnow.com/blog/ (get URLs from list_blog_posts).
    Returns {"title", "url", "text", "word_count", "sources", "byline"}. text is the article body
    only: navigation, share bars, key-takeaway asides, FAQ, author bio and calls to action are
    removed, and verify_quotes searches only this text. sources is the post's cited sources as
    [{"text", "href"}] (empty if it has none), useful for checking any number before it goes into
    a draft. byline is {"author", "published", "bio"}: the author's name, the published date as
    YYYY-MM-DD (from article:published_time or the visible byline), and the author bio card text,
    each null when the page does not show it. The bio can say who runs or convenes what the post
    describes. Successful results are cached in-process for 15 minutes. On failure returns
    {"error", "hint"}.
    """
    url = (url or "").strip()
    if not url.startswith(BLOG_URL_PREFIX) or not url[len(BLOG_URL_PREFIX):].strip("/"):
        return error(
            f"Refusing to fetch '{url}': only Disruption Now blog post URLs are allowed.",
            f"Pass a full post URL starting with {BLOG_URL_PREFIX}<slug>. Use list_blog_posts to find one.",
        )
    cached = cached_post(url)
    if cached is not None:
        return cached

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
        h1_title, text, sources, byline = extract_article(response.text)
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
    post = {
        "title": title,
        "url": str(response.url),
        "text": text,
        "word_count": word_count,
        "sources": sources,
        "byline": byline,
    }
    cache_post(url, post)
    return post
