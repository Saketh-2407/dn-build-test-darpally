"""Tool: check a brief, draft or review against its contract before it moves to the next agent."""

from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from ._common import PROJECT_ROOT, error, load_json

CONTRACTS_DIR = PROJECT_ROOT / "contracts"
VALID_KINDS = ["brief", "draft", "review"]
MAX_ERRORS = 20
_validators: dict[str, Draft202012Validator] = {}


def _validator(kind: str) -> Draft202012Validator:
    if kind not in _validators:
        schema = load_json(CONTRACTS_DIR / f"{kind}.schema.json")
        Draft202012Validator.check_schema(schema)
        _validators[kind] = Draft202012Validator(schema)
    return _validators[kind]


def _path(parts: Any) -> str:
    """JSON path like $.facts[2].id from a sequence of keys and indexes."""
    path = "$"
    for part in parts:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path


def _items(value: Any) -> list[tuple[int, dict[str, Any]]]:
    return [(i, item) for i, item in enumerate(value) if isinstance(item, dict)] if isinstance(value, list) else []


def _brief_checks(brief: dict[str, Any]) -> list[dict[str, str]]:
    errors = []
    quote_check = brief.get("quote_check")
    missing = quote_check.get("missing") if isinstance(quote_check, dict) else None
    if isinstance(missing, int) and missing != 0:
        errors.append({"path": "$.quote_check.missing", "message": f"{missing} source quote(s) were not found in the post; it must be 0."})
    seen: dict[str, int] = {}
    for i, fact in _items(brief.get("facts")):
        fact_id = fact.get("id")
        if not isinstance(fact_id, str):
            continue
        if fact_id in seen:
            errors.append({"path": f"$.facts[{i}].id", "message": f"Duplicate fact id '{fact_id}' (first used at $.facts[{seen[fact_id]}].id)."})
        else:
            seen[fact_id] = i
    return errors


def _draft_checks(draft: dict[str, Any], brief: dict[str, Any] | None) -> list[dict[str, str]]:
    errors = []
    claims = _items(draft.get("claims_map"))
    defined = [d["sentence"].strip() for _, d in _items(draft.get("definitions")) if isinstance(d.get("sentence"), str)]
    for i, claim in claims:
        snippet = claim.get("snippet")
        snippet = snippet.strip() if isinstance(snippet, str) else ""
        # A snippet may quote the whole definition sentence or part of it.
        if claim.get("fact_id") == "DEF" and not (snippet and any(snippet in s or s in snippet for s in defined)):
            errors.append({
                "path": f"$.claims_map[{i}]",
                "message": "Mapped to DEF but its snippet matches no definitions[].sentence; list it in definitions.",
            })
    if brief is None:
        return errors
    known = {fact.get("id") for _, fact in _items(brief.get("facts"))}
    cited = []
    for platform in ("linkedin", "instagram"):
        section = draft.get(platform)
        fact_ids = section.get("fact_ids") if isinstance(section, dict) else None
        if isinstance(fact_ids, list):
            cited += [(f"$.{platform}.fact_ids[{i}]", fact_id) for i, fact_id in enumerate(fact_ids)]
    cited += [(f"$.claims_map[{i}].fact_id", claim.get("fact_id")) for i, claim in claims]
    for path, fact_id in cited:
        if fact_id != "DEF" and fact_id not in known:
            errors.append({"path": path, "message": f"Fact id '{fact_id}' is not in the brief's facts."})
    return errors


def _review_checks(review: dict[str, Any]) -> list[dict[str, str]]:
    verdict, round_no = review.get("verdict"), review.get("round")
    violations = review.get("violations")
    if not isinstance(violations, list):
        return []
    hard = [v for v in violations if isinstance(v, dict) and v.get("severity") == "hard"]
    if verdict == "PASS" and violations:
        return [{"path": "$.verdict", "message": f"PASS requires no violations, but {len(violations)} are open."}]
    if verdict == "REVISE" and round_no == 2:
        return [{"path": "$.verdict", "message": "REVISE is not allowed in round 2; use BLOCKED (hard violations) or SHIP_WITH_FLAGS (judgment only)."}]
    if verdict == "BLOCKED" and not hard:
        return [{"path": "$.verdict", "message": "BLOCKED requires at least one hard violation."}]
    if verdict == "SHIP_WITH_FLAGS" and (not violations or hard):
        reason = "it has hard violations" if hard else "there are no violations"
        return [{"path": "$.verdict", "message": f"SHIP_WITH_FLAGS requires judgment violations only, but {reason}."}]
    return []


def validate_handoff(kind: str, data: dict[str, Any], brief: dict[str, Any] | None = None) -> dict[str, Any]:
    """Check one pipeline handoff against its contract in contracts/<kind>.schema.json.

    kind: "brief" (from dn-analyst), "draft" (from dn-writer) or "review" (from dn-reviewer).
    data: the handoff JSON exactly as the subagent returned it.
    brief: for a draft, the brief it was written from, so its fact ids can be checked.
    Beyond the schema: a brief needs quote_check.missing == 0 and unique fact ids; a draft's fact ids
    must exist in the brief (except "DEF"), and every "DEF" claim needs a definitions entry; a review's
    verdict must fit its violations (PASS: none; BLOCKED: at least one hard; SHIP_WITH_FLAGS: judgment
    only; no REVISE in round 2).
    Returns {"valid": bool, "errors": [{"path", "message"}]} with at most 20 errors; path is a JSON path
    such as $.facts[2].id. An unknown kind returns {"error", "hint", "valid_kinds"}.
    """
    if kind not in VALID_KINDS:
        return error(f"Unknown kind '{kind}'.", "Use one of valid_kinds.", valid_kinds=VALID_KINDS)
    try:
        validator = _validator(kind)
    except (OSError, ValueError, SchemaError) as exc:
        return error(f"Could not load contracts/{kind}.schema.json: {exc}", "Restore the contracts/ folder from git.")

    errors = [
        {"path": _path(e.absolute_path), "message": e.message}
        for e in sorted(validator.iter_errors(data), key=lambda e: [str(p) for p in e.absolute_path])
    ]
    if isinstance(data, dict):
        if kind == "brief":
            errors += _brief_checks(data)
        elif kind == "draft":
            errors += _draft_checks(data, brief if isinstance(brief, dict) else None)
        else:
            errors += _review_checks(data)
    return {"valid": not errors, "errors": errors[:MAX_ERRORS]}
