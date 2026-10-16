"""Run from the project root: python -m unittest discover tests -v"""

import unittest

from mcp_server.tools.lint_draft import lint_draft


class LintDraftTests(unittest.TestCase):
    def test_em_dash_is_hard_failure(self):
        result = lint_draft("We train your team — then we leave.")
        self.assertFalse(result["passed"])
        self.assertEqual([f["rule"] for f in result["hard_failures"]], ["em_dash"])

    def test_em_dash_substitutes_are_hard_failures(self):
        for text, match in [("We train your team – then we leave.", "–"), ("We train your team -- then we leave.", "--")]:
            with self.subTest(text=text):
                result = lint_draft(text)
                self.assertFalse(result["passed"])
                self.assertEqual([(f["rule"], f["match"]) for f in result["hard_failures"]], [("em_dash_substitute", match)])

    def test_range_en_dash_and_single_hyphen_pass(self):
        for text in ["Teams of 10–20 people built it.", "A two-day, real-world build.", "Read: https://example.com/a--b"]:
            with self.subTest(text=text):
                self.assertTrue(lint_draft(text)["passed"])

    def test_jargon_word_is_hard_failure(self):
        result = lint_draft("We deliver AI Solutions for your business.")
        self.assertFalse(result["passed"])
        self.assertEqual(result["hard_failures"][0]["rule"], "jargon_avoid_list")
        self.assertEqual(result["hard_failures"][0]["match"], "Solutions")
        self.assertIn("deliver AI Solutions for", result["hard_failures"][0]["context"])

    def test_listed_word_forms_fail(self):
        for word, rule in [("unlocked", "hype_verbs"), ("leveraging", "jargon_avoid_list"), ("transformative", "hype_verbs")]:
            with self.subTest(word=word):
                result = lint_draft(f"This is {word} work.")
                self.assertFalse(result["passed"])
                self.assertEqual([(f["rule"], f["match"]) for f in result["hard_failures"]], [(rule, word)])

    def test_unlisted_word_forms_pass(self):
        for text in ["We trained a transformer model.", "Transformers read the whole sentence at once.", "We ran a robustness test."]:
            with self.subTest(text=text):
                self.assertTrue(lint_draft(text)["passed"])

    def test_coach_not_consultant_is_allowlisted(self):
        result = lint_draft("We are a coach, not consultant. You keep the tool.")
        self.assertTrue(result["passed"])
        self.assertEqual(result["soft_flags"], [])

    def test_bare_consultant_is_soft_flag(self):
        result = lint_draft("Hire a consultant if you want slides.")
        self.assertTrue(result["passed"])
        self.assertEqual([f["rule"] for f in result["soft_flags"]], ["consultant_word"])

    def test_needs_is_soft_flag_not_failure(self):
        result = lint_draft("Your team needs one working AI tool.")
        self.assertTrue(result["passed"])
        self.assertEqual([f["match"] for f in result["soft_flags"]], ["needs"])

    def test_clean_string_passes(self):
        result = lint_draft("AI is a sharp junior employee with no common sense. Give it your direction.")
        self.assertTrue(result["passed"])
        self.assertEqual(result["hard_failures"], [])
        self.assertEqual(result["soft_flags"], [])

    def test_unknown_platform_returns_recoverable_error(self):
        result = lint_draft("Hello.", platform="tiktok")
        self.assertIn("error", result)
        self.assertEqual(result["valid_platforms"], ["linkedin", "instagram"])


if __name__ == "__main__":
    unittest.main()
