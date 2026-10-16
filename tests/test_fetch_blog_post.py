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

# No FAQ or Sources heading, so the bio card is not back matter: it must still stay out of the body.
BYLINE_PAGE = """
<html><head><meta property="article:published_time" content="2025-08-30T09:00:00Z"></head>
<body><article>
  <header><h1>Post Title</h1>
    <div><div><img alt="Rob Richardson" src="r.webp"><span>Rob Richardson</span></div>
      <time datetime="2025-08-30">August 29, 2025</time></div></header>
  <div>
    <p>Body paragraph about the hackathon.</p>
    <div class="bg-card"><img alt="Rob Richardson" src="r.webp"><div>
      <p>Rob Richardson</p><p>Founder &amp; CEO, Disruption Now</p>
      <p>Rob founded and convenes <a href="https://midwestcon.live/">MidwestCon</a>, the conference the hackathon runs under.</p>
    </div></div>
  </div>
</article></body></html>
"""


class ExtractArticleTests(unittest.TestCase):
    def setUp(self):
        self.title, self.text, self.sources, self.byline = extract_article(PAGE)

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


class BylineTests(unittest.TestCase):
    def test_byline_extracted(self):
        _, _, _, byline = extract_article(BYLINE_PAGE)
        self.assertEqual(byline, {
            "author": "Rob Richardson",
            "published": "2025-08-30",
            "bio": "Founder & CEO, Disruption Now\n"
                   "Rob founded and convenes MidwestCon, the conference the hackathon runs under.",
        })

    def test_visible_byline_used_without_meta_tags(self):
        page = BYLINE_PAGE.replace('<meta property="article:published_time" content="2025-08-30T09:00:00Z">', "")
        page = page.replace(' datetime="2025-08-30"', "")
        _, _, _, byline = extract_article(page)
        self.assertEqual((byline["author"], byline["published"]), ("Rob Richardson", "2025-08-29"))

    def test_missing_byline_gives_nulls(self):
        _, _, _, byline = extract_article("<article><p>Just a body.</p></article>")
        self.assertEqual(byline, {"author": None, "published": None, "bio": None})

    def test_bio_not_in_text(self):
        _, text, _, _ = extract_article(BYLINE_PAGE)
        self.assertEqual(text, "Body paragraph about the hackathon.")
        self.assertNotIn("convenes", text)


if __name__ == "__main__":
    unittest.main()
