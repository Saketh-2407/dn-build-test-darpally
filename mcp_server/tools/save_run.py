"""Tool: write one finished repurposing run to samples/<slug>/ behind a final lint gate."""

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from ._common import error, samples_dir
from .lint_draft import lint_draft

SLUG_RE = re.compile(r"^[a-z0-9-]{3,80}$")
VALID_VERDICTS = ["PASS", "SHIP_WITH_FLAGS", "BLOCKED"]
FINAL_TEXT_FIELDS = ["linkedin_text", "instagram_caption", "visual_note"]
ROUND_FILE_GLOBS = ["draft-r*.json", "review-r*.json"]
AI_DISCLOSURE = (
    "Drafted by an AI system from the source post and checked against DN's published voice doctrine. "
    "A human approves before anything is published."
)


def _hashtags(final: dict[str, Any]) -> list[str]:
    tags = [str(tag).strip() for tag in final.get("instagram_hashtags") or [] if str(tag).strip()]
    return [tag if tag.startswith("#") else f"#{tag}" for tag in tags]


def _validate(run: Any) -> dict[str, Any] | None:
    if not isinstance(run, dict):
        return error("run must be an object.", "Pass {source, brief, drafts, reviews, final}.")
    source = run.get("source")
    if not isinstance(source, dict) or not source.get("url") or not source.get("title"):
        return error("run.source needs url and title.", "Copy them from fetch_blog_post.")
    if not isinstance(run.get("brief"), dict):
        return error("run.brief must be an object.", "Pass the brief the drafts were written from.")
    for key in ("drafts", "reviews"):
        if not isinstance(run.get(key), list):
            return error(f"run.{key} must be a list.", f"Pass one entry per round in run.{key}, oldest first.")
    final = run.get("final")
    if not isinstance(final, dict):
        return error("run.final must be an object.", "Pass {verdict, linkedin_text, instagram_caption, instagram_hashtags, visual_note, flags}.")
    if final.get("verdict") not in VALID_VERDICTS:
        return error(f"Unknown verdict '{final.get('verdict')}'.", "Use one of valid_verdicts.", valid_verdicts=VALID_VERDICTS)
    for key in FINAL_TEXT_FIELDS:
        if not isinstance(final.get(key), str) or not final[key].strip():
            return error(f"run.final.{key} is empty.", f"Pass the final {key.replace('_', ' ')} as a string.")
    if not isinstance(final.get("instagram_hashtags", []), list) or not isinstance(final.get("flags", []), list):
        return error("run.final.instagram_hashtags and run.final.flags must be lists.", "Pass [] when there are none.")
    return None


def _final_lint(final: dict[str, Any]) -> dict[str, dict[str, Any]]:
    instagram = f"{final['instagram_caption']}\n\n{' '.join(_hashtags(final))}".strip()
    return {
        "linkedin": lint_draft(final["linkedin_text"], "linkedin"),
        "instagram": lint_draft(instagram, "instagram"),
    }


def _facts(brief: dict[str, Any]) -> list[str]:
    lines = []
    for i, fact in enumerate(brief.get("facts") or [], start=1):
        text = fact.get("fact", "") if isinstance(fact, dict) else str(fact)
        quote = fact.get("source_quote") if isinstance(fact, dict) else None
        lines.append(f"{i}. {text}\n   > " + (f'"{quote}"' if quote else "(no source quote recorded)"))
    return lines or ["_The brief lists no facts._"]


def _review_summary(run: dict[str, Any], lint: dict[str, dict[str, Any]]) -> list[str]:
    lines = [f"- Rounds: {len(run['reviews'])}"]
    for i, review in enumerate(run["reviews"], start=1):
        if isinstance(review, dict) and (review.get("verdict") or review.get("summary")):
            detail = " - ".join(str(review[k]) for k in ("verdict", "summary") if review.get(k))
            lines.append(f"- Round {i}: {detail}")
    flags = run["final"].get("flags") or []
    lines.append("- Flags: none" if not flags else "- Flags:")
    lines += [f"  - {flag}" for flag in flags]
    for platform, result in lint.items():
        for finding in result["hard_failures"]:
            lines.append(f"- Lint hard failure ({platform}): {finding['rule']} \"{finding['match']}\" in \"{finding['context']}\"")
        for finding in result["soft_flags"]:
            lines.append(f"- Lint soft flag ({platform}): {finding['rule']} \"{finding['match']}\"")
    return lines


def render_final_md(run: dict[str, Any], lint: dict[str, dict[str, Any]], today: date) -> str:
    source, final = run["source"], run["final"]
    sections = [
        f"# {source['title']}",
        f"Source: {source['url']}  \nDate: {today.isoformat()}",
        f"**Verdict:** {final['verdict']}",
        f"## LinkedIn post\n\n{final['linkedin_text'].strip()}",
        f"## Instagram caption\n\n{final['instagram_caption'].strip()}\n\n{' '.join(_hashtags(final))}".rstrip(),
        f"## Visual note\n\n{final['visual_note'].strip()}",
        "## Facts used\n\n" + "\n".join(_facts(run["brief"])),
        "## Review summary\n\n" + "\n".join(_review_summary(run, lint)),
        f"## AI disclosure\n\n{AI_DISCLOSURE}",
    ]
    return "\n\n".join(sections) + "\n"


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def save_run(slug: str, run: dict[str, Any]) -> dict[str, Any]:
    """Write one finished run to samples/<slug>/ so outputs are never copied by hand.

    slug: 3-80 chars of a-z, 0-9 and '-' (e.g. "future-of-data-hackathon"); becomes the folder name.
    run: {"source": {"url", "title"}, "brief": {..., "facts": [{"fact", "source_quote"}]},
    "drafts": [one per round], "reviews": [one per round], "final": {"verdict", "linkedin_text",
    "instagram_caption", "instagram_hashtags": [str], "visual_note", "flags": [str]}}.
    verdict is PASS, SHIP_WITH_FLAGS or BLOCKED. Final gate: linkedin_text, and instagram_caption
    with the hashtags, are linted; if either has hard failures the verdict must be BLOCKED, otherwise
    nothing is saved and an error lists the failures.
    Writes brief.json, draft-rN.json, review-rN.json and final.md (with the AI disclosure), replacing
    any earlier run saved under the same slug. Returns {"saved": [paths], "verdict"}.
    On failure returns {"error", "hint"}.
    """
    if not isinstance(slug, str) or not SLUG_RE.match(slug):
        return error(f"Invalid slug '{slug}'.", "Use 3-80 characters of lowercase letters, digits and '-', e.g. the post's URL slug.")
    invalid = _validate(run)
    if invalid:
        return invalid

    final = run["final"]
    lint = _final_lint(final)
    for platform, result in lint.items():
        if "error" in result:
            return error(f"Could not lint the final {platform} copy: {result['error']}", result["hint"])
    hard_failures = [{"platform": p, **f} for p, result in lint.items() for f in result["hard_failures"]]
    if hard_failures and final["verdict"] != "BLOCKED":
        return error(
            f"Verdict {final['verdict']} but the final copy has {len(hard_failures)} hard lint failure(s); nothing was saved.",
            "Fix the copy and re-run lint_draft, or save with verdict BLOCKED.",
            hard_failures=hard_failures,
        )

    out_dir = samples_dir() / slug
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        for pattern in ROUND_FILE_GLOBS:  # drop rounds left over from an earlier run under this slug
            for stale in out_dir.glob(pattern):
                stale.unlink()
        files: list[tuple[Path, Any]] = [(out_dir / "brief.json", run["brief"])]
        files += [(out_dir / f"draft-r{i}.json", d) for i, d in enumerate(run["drafts"], start=1)]
        files += [(out_dir / f"review-r{i}.json", r) for i, r in enumerate(run["reviews"], start=1)]
        for path, data in files:
            _write_json(path, data)
        final_md = out_dir / "final.md"
        final_md.write_text(render_final_md(run, lint, date.today()), encoding="utf-8")
    except OSError as exc:
        return error(f"Could not write {out_dir}: {exc}", "Check the samples directory exists and is writable.")

    return {"saved": [str(path) for path, _ in files] + [str(final_md)], "verdict": final["verdict"]}
