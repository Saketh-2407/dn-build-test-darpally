"""Uses a fixed index (real titles and URLs) so a cache refresh never breaks it.
Run from the project root: python -m unittest discover tests -v"""

import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcp_server.tools.list_blog_posts import list_blog_posts

# The tools package re-exports the function under the module's name, so fetch the module itself.
module = importlib.import_module("mcp_server.tools.list_blog_posts")

HACKATHON_2025 = {
    "title": "Future of Data Hackathon 2025 — Build AI for Cincinnati Nonprofits",
    "url": "https://disruptionnow.com/blog/back-bigger-future-of-data-hackathon-2025",
}
POSTS = [
    {
        "title": "The Efficiency Paradox Plaguing Nonprofits",
        "url": "https://disruptionnow.com/blog/the-efficiency-paradox-plaguing-nonprofits",
    },
    {
        "title": "No Team? No Problem. Join the Future of Data Hackathon Solo",
        "url": "https://disruptionnow.com/blog/no-team-no-problem-join-the-hackathon",
    },
    HACKATHON_2025,
    {
        "title": "Your Hospital Bill Is Wrong. AI Can Prove It.",
        "url": "https://disruptionnow.com/blog/your-hospital-bill-is-wrong-ai-can-prove-it",
    },
]


class ListBlogPostsTests(unittest.TestCase):
    def setUp(self):
        self.use_index(POSTS)

    def use_index(self, posts):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        index_path = Path(tmp.name) / "blog-index.json"
        index_path.write_text(json.dumps({"count": len(posts), "posts": posts}), encoding="utf-8")
        patcher = mock.patch.object(module, "BLOG_INDEX_PATH", index_path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_words_match_in_any_order(self):
        for topic in ["hackathon nonprofits", "Nonprofits HACKATHON"]:
            with self.subTest(topic=topic):
                result = list_blog_posts(topic)
                self.assertEqual(result["posts"], [HACKATHON_2025])
                self.assertEqual(result["total_matches"], 1)

    def test_no_match_returns_sample_titles(self):
        result = list_blog_posts("healthcare")
        self.assertEqual(result["posts"], [])
        self.assertEqual(result["total_matches"], 0)
        self.assertEqual(result["sample_titles"], [p["title"] for p in POSTS])

    def test_slug_only_word_matches(self):
        # "bigger" is only in the slug back-bigger-future-of-data-hackathon-2025, never in a title.
        self.assertEqual(list_blog_posts("bigger")["posts"], [HACKATHON_2025])

    def test_more_title_hits_rank_first(self):
        slug_only = {"title": "Back and Bigger", "url": "https://disruptionnow.com/blog/back-bigger-data-hackathon"}
        in_title = {"title": "The Data Hackathon Is Back", "url": "https://disruptionnow.com/blog/data-hackathon-returns"}
        self.use_index([slug_only, in_title])
        # Both match "hackathon back"; only in_title has "hackathon" in its title, so it outranks index order.
        self.assertEqual(list_blog_posts("hackathon back")["posts"], [in_title, slug_only])
        # A tie keeps index order.
        self.assertEqual(list_blog_posts("back")["posts"], [slug_only, in_title])

    def test_no_topic_lists_everything(self):
        result = list_blog_posts()
        self.assertEqual(result["posts"], POSTS)
        self.assertNotIn("sample_titles", result)


if __name__ == "__main__":
    unittest.main()
