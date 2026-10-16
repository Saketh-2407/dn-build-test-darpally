"""Run from the project root: python -m unittest discover tests -v"""

import copy
import json
import unittest
from pathlib import Path

from mcp_server.tools.validate_handoff import MAX_ERRORS, VALID_KINDS, validate_handoff

ROOT = Path(__file__).resolve().parent.parent
# A real brief from a finished run.
BRIEF = json.loads((ROOT / "samples" / "your-hospital-bill-is-wrong-ai-can-prove-it" / "brief.json").read_text(encoding="utf-8"))

DRAFT = {
    "source_url": "https://disruptionnow.com/blog/your-hospital-bill-is-wrong-ai-can-prove-it/",
    "round": 0,
    "linkedin": {"text": "What was inside a $195,000 hospital bill?", "opener_type": "Investigator", "fact_ids": ["F2", "F4"]},
    "instagram": {"caption": "AI flagged $162,000 in likely Medicare violations.", "hashtags": ["#MedicalBills"], "fact_ids": ["F4"]},
    "claims_map": [
        {"platform": "linkedin", "snippet": "What was inside a $195,000 hospital bill?", "fact_id": "F2"},
        {"platform": "instagram", "snippet": "AI flagged $162,000 in likely Medicare violations.", "fact_id": "F4"},
        {"platform": "linkedin", "snippet": "Bundling rules say which services must be billed as one charge.", "fact_id": "DEF"},
    ],
    "definitions": [{"term": "bundling rules", "sentence": "Bundling rules say which services must be billed as one charge."}],
    "visual_note": "Real photo of a bill next to a laptop.",
}

HARD = {"id": "V1", "severity": "hard", "platform": "linkedin", "line": "x", "rule": "em_dash", "fix": "Remove it."}
JUDGMENT = {"id": "V2", "severity": "judgment", "platform": "instagram", "line": "y", "rule": "the-gate", "fix": "Cut it."}
REVIEW = {
    "round": 0,
    "verdict": "PASS",
    "violations": [],
    "sentence_audit": [{"platform": "linkedin", "sentence": "What was inside a $195,000 hospital bill?"}],
}


def paths(result):
    return [e["path"] for e in result["errors"]]


class SchemaTests(unittest.TestCase):
    def test_valid_brief(self):
        self.assertEqual(validate_handoff("brief", BRIEF), {"valid": True, "errors": []})

    def test_invalid_brief(self):
        brief = copy.deepcopy(BRIEF)
        brief["facts"] = brief["facts"][:2]
        brief["facts"][1]["id"] = "fact-2"
        brief["timeframe"]["status"] = "soon"
        del brief["core_point"]
        result = validate_handoff("brief", brief)
        self.assertFalse(result["valid"])
        self.assertEqual(sorted(paths(result)), ["$", "$.facts", "$.facts[1].id", "$.timeframe.status"])

    def test_valid_draft(self):
        self.assertEqual(validate_handoff("draft", DRAFT, BRIEF), {"valid": True, "errors": []})

    def test_invalid_draft(self):
        draft = copy.deepcopy(DRAFT)
        draft["round"] = 3
        draft["instagram"]["hashtags"] = [42]
        draft["claims_map"][0]["platform"] = "tiktok"
        del draft["definitions"]
        result = validate_handoff("draft", draft)
        self.assertFalse(result["valid"])
        # $.claims_map[2] is the DEF claim, which now has no definitions entry to match.
        self.assertEqual(
            sorted(paths(result)),
            ["$", "$.claims_map[0].platform", "$.claims_map[2]", "$.instagram.hashtags[0]", "$.round"],
        )

    def test_valid_review(self):
        self.assertEqual(validate_handoff("review", REVIEW), {"valid": True, "errors": []})

    def test_invalid_review(self):
        review = {"round": 0, "verdict": "MAYBE", "violations": [{"id": "V1", "severity": "minor"}], "sentence_audit": []}
        result = validate_handoff("review", review)
        self.assertFalse(result["valid"])
        self.assertIn("$.verdict", paths(result))
        self.assertIn("$.violations[0].severity", paths(result))
        self.assertIn("$.sentence_audit", paths(result))
        self.assertIn("$.violations[0]", paths(result))  # missing platform, line, rule, fix

    def test_errors_capped(self):
        draft = {"claims_map": [{"platform": "x"} for _ in range(30)]}
        result = validate_handoff("draft", draft)
        self.assertFalse(result["valid"])
        self.assertEqual(len(result["errors"]), MAX_ERRORS)

    def test_unknown_kind(self):
        result = validate_handoff("caption", {})
        self.assertIn("error", result)
        self.assertIn("hint", result)
        self.assertEqual(result["valid_kinds"], VALID_KINDS)


class BriefCheckTests(unittest.TestCase):
    def test_missing_quotes_must_be_zero(self):
        brief = copy.deepcopy(BRIEF)
        brief["quote_check"]["missing"] = 2
        self.assertEqual(paths(validate_handoff("brief", brief)), ["$.quote_check.missing"])

    def test_fact_ids_unique(self):
        brief = copy.deepcopy(BRIEF)
        brief["facts"][3]["id"] = "F1"
        result = validate_handoff("brief", brief)
        self.assertEqual(paths(result), ["$.facts[3].id"])
        self.assertIn("Duplicate fact id 'F1'", result["errors"][0]["message"])


class DraftCheckTests(unittest.TestCase):
    def test_unknown_fact_ids_rejected(self):
        draft = copy.deepcopy(DRAFT)
        draft["linkedin"]["fact_ids"].append("F99")
        draft["instagram"]["fact_ids"] = ["F42"]
        draft["claims_map"][0]["fact_id"] = "F77"
        result = validate_handoff("draft", draft, BRIEF)
        self.assertEqual(paths(result), ["$.linkedin.fact_ids[2]", "$.instagram.fact_ids[0]", "$.claims_map[0].fact_id"])

    def test_fact_ids_unchecked_without_brief(self):
        draft = copy.deepcopy(DRAFT)
        draft["linkedin"]["fact_ids"].append("F99")
        self.assertTrue(validate_handoff("draft", draft)["valid"])

    def test_def_claim_needs_definition(self):
        draft = copy.deepcopy(DRAFT)
        draft["definitions"] = []
        result = validate_handoff("draft", draft, BRIEF)
        self.assertEqual(paths(result), ["$.claims_map[2]"])

    def test_def_snippet_may_be_part_of_definition(self):
        draft = copy.deepcopy(DRAFT)
        draft["claims_map"][2]["snippet"] = "which services must be billed as one charge"
        self.assertTrue(validate_handoff("draft", draft, BRIEF)["valid"])


class ReviewCheckTests(unittest.TestCase):
    def check(self, verdict, violations, round_no=0):
        review = dict(REVIEW, verdict=verdict, violations=violations, round=round_no)
        return validate_handoff("review", review)

    def test_pass_requires_no_violations(self):
        self.assertEqual(paths(self.check("PASS", [JUDGMENT])), ["$.verdict"])

    def test_revise_not_allowed_in_round_2(self):
        self.assertTrue(self.check("REVISE", [JUDGMENT], 1)["valid"])
        self.assertEqual(paths(self.check("REVISE", [JUDGMENT], 2)), ["$.verdict"])

    def test_blocked_requires_hard_violation(self):
        self.assertTrue(self.check("BLOCKED", [HARD, JUDGMENT], 2)["valid"])
        self.assertEqual(paths(self.check("BLOCKED", [JUDGMENT], 2)), ["$.verdict"])

    def test_ship_with_flags_requires_judgment_only(self):
        self.assertTrue(self.check("SHIP_WITH_FLAGS", [JUDGMENT], 2)["valid"])
        self.assertEqual(paths(self.check("SHIP_WITH_FLAGS", [], 2)), ["$.verdict"])
        self.assertEqual(paths(self.check("SHIP_WITH_FLAGS", [HARD], 2)), ["$.verdict"])


if __name__ == "__main__":
    unittest.main()
