"""Offline tests for the brand-cache builder. Run from the project root: python -m unittest discover tests -v"""

import json
import tempfile
import unittest
from pathlib import Path

from mcp_server.build_brand_cache import NOTE, extract_article, update_cache_file

PAGE = """
<html><body>
<div class="wip" role="status">This is a work in progress, media will be added soon.</div>
<div class="search-hud"><span class="search-hud-label">Search</span></div>
<aside class="rail"><nav>Sidebar link</nav></aside>
<main id="main"><div class="guide-pane">
  <header class="hc"><div class="hc-top">Voice &amp; Tone HUB-voice.md §8</div>
    <h1 class="hc-title">Wording &amp; mechanics.</h1></header>
  <nav class="bc"><ol><li>Brand Hub</li><li>/</li></ol></nav>
  <button class="sa"><span class="sa-feedback">Copied</span></button>
  <section class="gs"><header><span class="eyebrow">Section 2</span><div>Punctuation.</div></header>
    <p><strong>Em dashes: none.</strong> The long dash is the clearest AI tell.</p>
    <p>Say <em>this</em>, not that.</p></section>
  <section class="gs"><span>Keep reading</span><a href="/x">More on voice →</a></section>
</div></main>
</body></html>
"""


class ExtractArticleTests(unittest.TestCase):
    def test_keeps_article_text_and_drops_chrome(self):
        self.assertEqual(
            extract_article(PAGE),
            "Wording & mechanics.\nSection 2\nPunctuation.\n"
            "Em dashes: none. The long dash is the clearest AI tell.\nSay this, not that.",
        )

    def test_page_without_main_gives_empty_text(self):
        self.assertEqual(extract_article('<html><body><div id="app"></div></body></html>'), "")


class UpdateCacheFileTests(unittest.TestCase):
    def write(self, data):
        path = Path(tempfile.mkdtemp()) / "rule.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_adds_fields_and_keeps_structured_ones(self):
        path = self.write({"category": "mechanics", "rules": ["a"]})
        update_cache_file(path, "page text", "2026-10-16T00:00:00+00:00")
        update_cache_file(path, "newer text", "2026-10-17T00:00:00+00:00")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {
            "category": "mechanics", "rules": ["a"], "verbatim": "newer text",
            "fetched_at": "2026-10-17T00:00:00+00:00", "note": NOTE,
        })

    def test_existing_note_is_kept(self):
        path = self.write({"category": "logo-usage", "note": "Our own note."})
        update_cache_file(path, "page text", "2026-10-16T00:00:00+00:00")
        update_cache_file(path, "page text", "2026-10-16T00:00:00+00:00")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["note"], "Our own note.")
        self.assertEqual(data["verbatim_note"], NOTE)


if __name__ == "__main__":
    unittest.main()
