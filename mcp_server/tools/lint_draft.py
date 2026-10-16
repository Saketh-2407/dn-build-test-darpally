"""Tool: mechanical brand lint for copy WE generate (never for source blog text)."""

import re
from typing import Any

from ._common import LINT_RULES_PATH, error, load_json

VALID_PLATFORMS = ["linkedin", "instagram"]
CONTEXT_CHARS = 40


def _term_pattern(term: str) -> re.Pattern[str]:
    """Whole-word match for single words, phrase match (flexible whitespace) for multi-word entries."""
    body = r"\s+".join(re.escape(word) for word in term.split())
    return re.compile(rf"(?<!\w){body}(?!\w)", re.IGNORECASE)


def _context(text: str, start: int, end: int) -> str:
    left, right = max(0, start - CONTEXT_CHARS), min(len(text), end + CONTEXT_CHARS)
    snippet = re.sub(r"\s+", " ", text[left:right]).strip()
    return f"{'...' if left else ''}{snippet}{'...' if right < len(text) else ''}"


def _term_lists(section: dict[str, Any]) -> dict[str, list[str]]:
    """Rule lists in a lint section; scalar 'note_*' / 'em_dash_char' entries are skipped."""
    return {name: value for name, value in section.items() if isinstance(value, list)}


def _find(text: str, rule: str, terms: list[str], allowed: list[tuple[int, int]]) -> list[dict[str, str]]:
    found = []
    for term in terms:
        for m in _term_pattern(term).finditer(text):
            if any(a_start <= m.start() and m.end() <= a_end for a_start, a_end in allowed):
                continue
            found.append({"rule": rule, "match": m.group(0), "context": _context(text, m.start(), m.end())})
    return found


def lint_draft(text: str, platform: str = "linkedin") -> dict[str, Any]:
    """Run literal brand checks on a draft LinkedIn or Instagram post that WE generated.

    Only for our own generated copy. Never run it on source blog text: the blog legitimately
    contains em dashes and other patterns, and linting it would produce meaningless failures.

    hard_failures (any one fails the draft): em dashes and banned jargon, hype verbs, significance
    adjectives, vibe phrases, cliches and throat-clearing openers. soft_flags (warnings for a human or
    AI reviewer to judge in context): filler intensifiers, 'consultant', and the corporate noun 'needs'.
    Matches inside earned brand phrases (e.g. 'coach, not consultant') are never flagged.
    Returns {"passed", "platform", "char_count", "hard_failures", "soft_flags"}; each finding is
    {"rule", "match", "context"} where context is the surrounding snippet.
    """
    if not isinstance(text, str) or not text.strip():
        return error("Draft text is empty.", "Pass the full draft post text to lint.")
    platform = (platform or "").strip().lower()
    if platform not in VALID_PLATFORMS:
        return error(f"Unknown platform '{platform}'.", "Use one of valid_platforms.", valid_platforms=VALID_PLATFORMS)
    try:
        rules = load_json(LINT_RULES_PATH)
    except (FileNotFoundError, ValueError) as exc:
        return error(f"Could not load lint rules: {exc}", "Restore mcp_server/cache/lint-rules.json.")

    allowed = [
        (m.start(), m.end())
        for phrase in rules.get("allowlist_earned_phrases", [])
        for m in _term_pattern(phrase).finditer(text)
    ]

    hard_fail = rules.get("hard_fail", {})
    hard_failures = []
    em_dash = hard_fail.get("em_dash_char")
    if em_dash:
        hard_failures += [
            {"rule": "em_dash", "match": em_dash, "context": _context(text, m.start(), m.end())}
            for m in re.finditer(re.escape(em_dash), text)
        ]
    for rule, terms in _term_lists(hard_fail).items():
        hard_failures += _find(text, rule, terms, allowed)

    soft_flags = []
    for rule, terms in _term_lists(rules.get("soft_flag", {})).items():
        soft_flags += _find(text, rule, terms, allowed)

    return {
        "passed": not hard_failures,
        "platform": platform,
        "char_count": len(text),
        "hard_failures": hard_failures,
        "soft_flags": soft_flags,
    }
