"""Offline tests for article extraction. Run from the project root: python -m unittest discover tests -v"""

import unittest

from mcp_server.tools.fetch_blog_post import _index_title, extract_article

PAGE = """
<html><body><article>
  <header><h1>Big Claim<br/><span>Smaller Point</span></h1>
    <p class="sr-only">screen reader summary</p><p>The hook paragraph.</p></header>
  <div>
    <aside class="key-takeaways"><h2>Key Takeaways</h2><ul><li>Summary bullet</li></ul></aside>
    <p>Body paragraph with <strong>bold</strong> text.</p>
    <section><h2>Frequently Asked Questions</h2><p>FAQ answer</p></section>
    <section><h2>Sources</h2><ul>
      <li>Outlet, 2026. "<a href="https://example.com/a">Headline A</a>" note.</li>
      <li>Report with no link.</li>
    </ul></section>
    <div>Rob Richardson Founder bio</div>
    <div>Book a Consultation</div>
    <div>Published today Share</div>
  </div>
</article></body></html>
"""


class ExtractArticleTests(unittest.TestCase):
    def setUp(self):
        self.title, self.text, self.sources = extract_article(PAGE)

    def test_h1_line_breaks_join_with_period(self):
        self.assertEqual(self.title, "Big Claim. Smaller Point")

    def test_text_keeps_lede_and_body_only(self):
        self.assertEqual(self.text, "The hook paragraph.\nBody paragraph with bold text.")

    def test_sources_returned_separately(self):
        self.assertEqual(self.sources, [
            {"text": 'Outlet, 2026. "Headline A" note.', "href": "https://example.com/a"},
            {"text": "Report with no link.", "href": ""},
        ])

    def test_no_sources_section_gives_empty_list(self):
        self.assertEqual(extract_article("<article><p>Just a body.</p></article>")[2], [])

    def test_index_title_lookup_ignores_trailing_slash(self):
        self.assertEqual(
            _index_title("https://disruptionnow.com/blog/you-don-t-have-a-model-problem/"),
            "You Don’t Have a Model Problem — You Have a Workflow Problem",
        )


if __name__ == "__main__":
    unittest.main()
