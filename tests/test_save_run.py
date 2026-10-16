"""Writes into a temp directory via DN_SAMPLES_DIR. Run from the project root: python -m unittest discover tests -v"""

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcp_server.tools._common import SAMPLES_DIR_ENV
from mcp_server.tools.save_run import AI_DISCLOSURE, DEFINITIONS_HEADING, save_run

RUN = {
    "source": {"url": "https://disruptionnow.com/blog/stub-post-for-tests", "title": "Stub Post"},
    "brief": {
        "angle": "Solo builders are welcome.",
        "facts": [{"fact": "There are 40 student slots.", "source_quote": "Forty student slots are open to teams and solo builders."}],
    },
    "drafts": [{"linkedin_text": "First try."}, {"linkedin_text": "Second try."}],
    "reviews": [{"verdict": "REVISE", "summary": "Tighten the hook."}, {"verdict": "PASS", "summary": "Ready."}],
    "final": {
        "verdict": "PASS",
        "linkedin_text": "AI is a sharp junior employee with no common sense. Give it your direction.",
        "instagram_caption": "Forty student slots. Come solo or bring a team.",
        "instagram_hashtags": ["#Cincinnati", "Hackathon"],
        "visual_note": "Photo of students at laptops, DN logo bottom right.",
        "flags": [],
    },
}


def run_with(**final_changes):
    run = copy.deepcopy(RUN)
    run["final"].update(final_changes)
    return run


class SaveRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        patcher = mock.patch.dict(os.environ, {SAMPLES_DIR_ENV: self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def assertNothingWritten(self):
        self.assertEqual(list(self.root.iterdir()), [])

    def test_bad_slug_rejected(self):
        for slug in ["../escape", "ab", "Has-Caps", "a/b/c", "x" * 81]:
            with self.subTest(slug=slug):
                result = save_run(slug, copy.deepcopy(RUN))
                self.assertIn("error", result)
                self.assertIn("hint", result)
        self.assertNothingWritten()

    def test_pass_with_em_dash_refused(self):
        result = save_run("em-dash-run", run_with(linkedin_text="We train your team — then we leave."))
        self.assertIn("error", result)
        self.assertEqual([(f["platform"], f["rule"]) for f in result["hard_failures"]], [("linkedin", "em_dash")])
        self.assertNothingWritten()

    def test_ship_with_flags_with_jargon_refused(self):
        result = save_run("jargon-run", run_with(verdict="SHIP_WITH_FLAGS", instagram_caption="Real solutions for nonprofits."))
        self.assertIn("error", result)
        self.assertEqual([(f["platform"], f["match"]) for f in result["hard_failures"]], [("instagram", "solutions")])
        self.assertNothingWritten()

    def test_blocked_with_jargon_saved(self):
        result = save_run("jargon-run", run_with(verdict="BLOCKED", instagram_caption="Real solutions for nonprofits."))
        self.assertEqual(result["verdict"], "BLOCKED")
        final_md = (self.root / "jargon-run" / "final.md").read_text(encoding="utf-8")
        self.assertIn("**Verdict:** BLOCKED", final_md)
        self.assertIn('Lint hard failure (instagram): jargon_avoid_list "solutions"', final_md)

    def test_clean_pass_writes_every_file(self):
        result = save_run("clean-run", copy.deepcopy(RUN))
        out = self.root / "clean-run"
        expected = ["brief.json", "draft-r0.json", "draft-r1.json", "review-r0.json", "review-r1.json", "final.md"]
        self.assertEqual(result, {"saved": [str(out / name) for name in expected], "verdict": "PASS"})
        self.assertEqual(sorted(p.name for p in out.iterdir()), sorted(expected))
        self.assertEqual(json.loads((out / "brief.json").read_text(encoding="utf-8")), RUN["brief"])
        self.assertEqual(json.loads((out / "review-r1.json").read_text(encoding="utf-8")), RUN["reviews"][1])

        final_md = (out / "final.md").read_text(encoding="utf-8")
        for expected_text in [
            "# Stub Post",
            "Source: https://disruptionnow.com/blog/stub-post-for-tests",
            "**Verdict:** PASS",
            "## LinkedIn post\n\n" + RUN["final"]["linkedin_text"],
            "## Instagram caption\n\nForty student slots. Come solo or bring a team.\n\n#Cincinnati #Hackathon",
            "## Visual note",
            '1. There are 40 student slots.\n   > "Forty student slots are open to teams and solo builders."',
            "- Rounds: 2",
            "- Round 0: REVISE - Tighten the hook.",
            "- Round 1: PASS - Ready.",
            f"## AI disclosure\n\n{AI_DISCLOSURE}",
        ]:
            with self.subTest(expected_text=expected_text[:30]):
                self.assertIn(expected_text, final_md)
        self.assertNotIn(DEFINITIONS_HEADING, final_md)
        # The stub drafts record no fact ids, so every brief fact is listed under one heading.
        self.assertIn("## Facts in the brief\n\n1. There are 40 student slots.", final_md)
        self.assertNotIn("## Facts used", final_md)

    def test_facts_used_split_from_unused(self):
        run = copy.deepcopy(RUN)
        run["brief"]["facts"] = [
            {"id": "F1", "fact": "Forty slots.", "source_quote": "Forty student slots are open."},
            {"id": "F2", "fact": "Solo builders welcome.", "source_quote": "Solo builders are welcome."},
            {"id": "F3", "fact": "Teams of four.", "source_quote": "Teams of up to four."},
            {"id": "F4", "fact": "Held in Cincinnati.", "source_quote": "It is held in Cincinnati."},
        ]
        run["drafts"] = [
            {"linkedin": {"fact_ids": ["F4"]}},  # an earlier round's ids do not count
            {
                "linkedin": {"fact_ids": ["F1"]},
                "instagram": {"fact_ids": ["F1"]},
                "claims_map": [{"fact_id": "F3"}, {"fact_id": "DEF"}],
            },
        ]
        save_run("facts-run", run)
        final_md = (self.root / "facts-run" / "final.md").read_text(encoding="utf-8")
        self.assertIn(
            '## Facts used\n\nF1. Forty slots.\n   > "Forty student slots are open."\n'
            'F3. Teams of four.\n   > "Teams of up to four."\n\n'
            "## Other verified facts in the brief (not used)\n\n"
            'F2. Solo builders welcome.\n   > "Solo builders are welcome."\n'
            'F4. Held in Cincinnati.\n   > "It is held in Cincinnati."\n',
            final_md,
        )
        self.assertNotIn("## Facts in the brief", final_md)

    def test_every_fact_used_says_so(self):
        run = copy.deepcopy(RUN)
        run["brief"]["facts"] = [{"id": "F1", "fact": "Forty slots.", "source_quote": "Forty student slots are open."}]
        run["drafts"] = [{"claims_map": [{"fact_id": "F1"}]}]
        save_run("all-used", run)
        final_md = (self.root / "all-used" / "final.md").read_text(encoding="utf-8")
        self.assertIn("## Other verified facts in the brief (not used)\n\n_None. The copy uses every fact._", final_md)

    def test_definitions_listed_for_human_check(self):
        definition = {"term": "bundling rules", "sentence": "Bundling rules say which services must be billed as one charge."}
        result = save_run("definitions-run", run_with(definitions=[definition]))
        self.assertEqual(result["verdict"], "PASS")
        final_md = (self.root / "definitions-run" / "final.md").read_text(encoding="utf-8")
        self.assertIn(
            f"## {DEFINITIONS_HEADING}\n\n- **bundling rules:** Bundling rules say which services must be billed as one charge.",
            final_md,
        )

    def test_malformed_definition_refused(self):
        for bad in [["bundling rules"], [{"term": "bundling rules"}], "not a list"]:
            with self.subTest(definitions=bad):
                result = save_run("bad-definitions", run_with(definitions=bad))
                self.assertIn("error", result)
        self.assertNothingWritten()

    def test_files_named_by_own_round(self):
        run = copy.deepcopy(RUN)
        run["drafts"] = [{"round": 1, "linkedin_text": "Revision."}]
        run["reviews"] = [{"round": 1, "verdict": "PASS", "summary": "Ready."}]
        result = save_run("round-run", run)
        out = self.root / "round-run"
        expected = ["brief.json", "draft-r1.json", "review-r1.json", "final.md"]
        self.assertEqual(result["saved"], [str(out / name) for name in expected])
        self.assertIn("- Round 1: PASS - Ready.", (out / "final.md").read_text(encoding="utf-8"))

    def test_rerun_clears_stale_round_files(self):
        save_run("rerun", copy.deepcopy(RUN))
        run = copy.deepcopy(RUN)
        run["drafts"], run["reviews"] = run["drafts"][:1], run["reviews"][:1]
        save_run("rerun", run)
        names = sorted(p.name for p in (self.root / "rerun").iterdir())
        self.assertEqual(names, ["brief.json", "draft-r0.json", "final.md", "review-r0.json"])


if __name__ == "__main__":
    unittest.main()
