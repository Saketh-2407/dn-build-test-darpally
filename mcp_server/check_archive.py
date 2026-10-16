"""Run fetch_blog_post on every post in the blog index and report how the extraction holds up.

Usage (from the project root): python -m mcp_server.check_archive
Fetches one post at a time with a 1-second pause, then writes reports/archive-check.md.
"""

import asyncio
import re
import statistics
from datetime import datetime, timezone
from typing import Any

from mcp_server.tools import fetch_blog_post
from mcp_server.tools._common import BLOG_INDEX_PATH, PROJECT_ROOT, load_json

REPORT_PATH = PROJECT_ROOT / "reports" / "archive-check.md"
PAUSE_SECONDS = 1.0
THIN_WORDS = 300
# Back matter fetch_blog_post should strip; matched case-sensitively so ordinary body prose rarely trips it.
BACK_MATTER = ["Frequently Asked", "Share this", "Subscribe", "Read more", "About the author"]
CONTEXT_CHARS = 50


def _cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ") or "-"


def _context(text: str, start: int, end: int) -> str:
    left, right = max(0, start - CONTEXT_CHARS), min(len(text), end + CONTEXT_CHARS)
    return re.sub(r"\s+", " ", text[left:right]).strip()


def _back_matter_hits(text: str) -> list[str]:
    hits = []
    for phrase in BACK_MATTER:
        match = re.search(re.escape(phrase), text)
        if match:
            hits.append(f'"{phrase}" in "...{_context(text, match.start(), match.end())}..."')
    return hits


async def check_all(posts: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows = []
    for i, post in enumerate(posts, start=1):
        if i > 1:
            await asyncio.sleep(PAUSE_SECONDS)
        print(f"[{i}/{len(posts)}] {post['url']}", flush=True)
        try:
            result = await fetch_blog_post(post["url"])
        except Exception as exc:  # report every failure, never stop the sweep
            result = {"error": f"{type(exc).__name__}: {exc}"}
        row: dict[str, Any] = {"title": post["title"], "url": post["url"]}
        if "error" in result:
            row.update(status="error", error=result["error"], hint=result.get("hint"))
        else:
            byline = result.get("byline") or {}
            row.update(
                status="ok",
                title=result.get("title") or post["title"],
                word_count=result.get("word_count", 0),
                author=byline.get("author"),
                published=byline.get("published"),
                has_bio=bool(byline.get("bio")),
                sources=len(result.get("sources") or []),
                back_matter=_back_matter_hits(result.get("text", "")),
            )
        rows.append(row)
    return rows


def _flags(rows: list[dict[str, Any]]) -> list[str]:
    flags = []
    for row in rows:
        name = f"[{_cell(row['title'])}]({row['url']})"
        if row["status"] == "error":
            flags.append(f"- **error**: {name}: {row['error']}" + (f" (hint: {row['hint']})" if row.get("hint") else ""))
            continue
        if row["word_count"] < THIN_WORDS:
            flags.append(f"- **thin** ({row['word_count']} words): {name}")
        for hit in row["back_matter"]:
            flags.append(f"- **back matter**: {name}: {hit}")
    return flags


def render(rows: list[dict[str, Any]], checked_at: datetime) -> str:
    ok = [r for r in rows if r["status"] == "ok"]
    counts = [r["word_count"] for r in ok]
    words = f"{min(counts)} / {statistics.median(counts):g} / {max(counts)}" if counts else "n/a"
    summary = [
        f"- Posts checked: {len(rows)}",
        f"- OK: {len(ok)}",
        f"- Errors: {len(rows) - len(ok)}",
        f"- Word count (min / median / max): {words}",
        f"- With a byline author: {sum(1 for r in ok if r['author'])}",
        f"- With a published date: {sum(1 for r in ok if r['published'])}",
        f"- With an author bio: {sum(1 for r in ok if r['has_bio'])}",
        f"- With sources: {sum(1 for r in ok if r['sources'])}",
    ]
    table = ["| Title | Words | Author | Published | Sources | Status |", "|---|---:|---|---|---:|---|"]
    for r in rows:
        if r["status"] == "ok":
            table.append(
                f"| [{_cell(r['title'])}]({r['url']}) | {r['word_count']} | {_cell(r['author'])} | "
                f"{_cell(r['published'])} | {r['sources']} | ok |"
            )
        else:
            table.append(f"| [{_cell(r['title'])}]({r['url']}) | - | - | - | - | error |")
    flags = _flags(rows) or ["- None."]
    return "\n\n".join([
        "# Archive check: fetch_blog_post",
        f"Checked {checked_at.strftime('%Y-%m-%d %H:%M UTC')} against {BLOG_INDEX_PATH.relative_to(PROJECT_ROOT).as_posix()}.",
        "## Summary\n\n" + "\n".join(summary),
        f"## Flags\n\nThin means under {THIN_WORDS} words. Back matter means the cleaned text still contains one of: "
        + ", ".join(f'"{p}"' for p in BACK_MATTER) + " (case-sensitive).\n\n" + "\n".join(flags),
        "## All posts\n\n" + "\n".join(table),
    ]) + "\n"


def main() -> None:
    posts = load_json(BLOG_INDEX_PATH).get("posts", [])
    rows = asyncio.run(check_all(posts))
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render(rows, datetime.now(timezone.utc)), encoding="utf-8")
    print(f"Wrote {REPORT_PATH.relative_to(PROJECT_ROOT).as_posix()}")


if __name__ == "__main__":
    main()
