"""Offline: the stub post is seeded into the shared post cache, so no request is made.
Run from the project root: python -m unittest discover tests -v"""

import unittest

from mcp_server.tools import _common
from mcp_server.tools.verify_quotes import verify_quotes

URL = "https://disruptionnow.com/blog/stub-post-for-tests"
BODY = (
    "The hackathon runs for one weekend.\n"
    "Rob said “AI is a sharp junior employee” — and he meant it.\n"
    "Forty student slots are open to teams and solo builders."
)


class VerifyQuotesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _common._post_cache.clear()
        _common.cache_post(URL, {"title": "Stub", "url": URL, "text": BODY, "word_count": len(BODY.split()), "sources": []})

    def tearDown(self):
        _common._post_cache.clear()

    async def test_exact_match_is_found(self):
        result = await verify_quotes(URL, ["The hackathon runs for one weekend."])
        self.assertEqual(result, {"url": URL, "checked": 1, "found": ["The hackathon runs for one weekend."], "missing": []})

    async def test_match_needs_curly_quote_and_em_dash_normalization(self):
        quote = 'rob said "AI is a sharp junior employee" - and he   meant it.'
        result = await verify_quotes(URL, [quote])
        self.assertEqual(result["found"], [quote])
        self.assertEqual(result["missing"], [])

    async def test_missing_quote_returns_closest_match(self):
        result = await verify_quotes(URL, ["The hackathon runs for one weekend.", "Fifty student slots are open to teams."])
        self.assertEqual(result["checked"], 2)
        self.assertEqual(result["found"], ["The hackathon runs for one weekend."])
        self.assertEqual(len(result["missing"]), 1)
        self.assertEqual(result["missing"][0]["quote"], "Fifty student slots are open to teams.")
        self.assertEqual(result["missing"][0]["closest_match"], "Forty student slots are open to teams and solo builders.")

    async def test_empty_list_is_recoverable_error(self):
        result = await verify_quotes(URL, [])
        self.assertIn("error", result)
        self.assertIn("hint", result)

    async def test_non_blog_url_is_recoverable_error(self):
        result = await verify_quotes("https://example.com/post", ["anything"])
        self.assertIn("error", result)
        self.assertIn("hint", result)


if __name__ == "__main__":
    unittest.main()
