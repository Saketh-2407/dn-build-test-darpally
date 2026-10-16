# DN Repurposer

Turns one Disruption Now blog post into a LinkedIn post and an Instagram 
caption that pass DN's published brand doctrine.

## Run it
- `/repurpose-post <post URL or topic word>` runs the whole pipeline. The SOP is 
  `.claude/skills/repurpose-post/SKILL.md`.
- One post per conversation. Start a new conversation for the next post.
- First-time setup: `python bootstrap.py` (Windows: `py bootstrap.py`).

## How it is built
- MCP server `dn-repurposer` (`mcp_server/`): list_blog_posts, fetch_blog_post, 
  get_brand_rule, lint_draft, verify_quotes, validate_handoff, save_run.
- Subagents (`.claude/agents/`): dn-analyst -> dn-writer -> dn-reviewer. Each 
  has only the tools its job needs. The Writer cannot fetch the post.
- Handoffs are JSON, checked against `contracts/*.schema.json`.
- Doctrine (`mcp_server/cache/brand-rules/`): DN's brand hub pages, verbatim, 
  plus a structured index. Refresh with `python bootstrap.py --refresh`.
- Outputs go to `samples/<slug>/`, written only by save_run.

## Rules for the main session
- You orchestrate. Never write, edit, or fix social copy yourself. Only the 
  Writer writes and only the Reviewer judges.
- Never read a blog post in the main session. The Analyst does.
- Every fact in the copy comes from the source post, through the Analyst's 
  verified ledger. No outside research.
- lint_draft checks only copy we generate, never the source post.
- Never hand-edit files in `mcp_server/cache/`. Use the build scripts.

## What lives where
- Always in context: this file and the skill.
- Fetched on demand, one at a time: blog posts (fetch_blog_post) and doctrine 
  categories (get_brand_rule).
- Never in context: other runs' samples and the full blog archive.
