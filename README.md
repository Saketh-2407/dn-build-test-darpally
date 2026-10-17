# dn-build-test-darpally

A system that turns a Disruption Now blog post into a LinkedIn post and an Instagram caption that pass DN's own published brand doctrine.

Built with Claude Code: an MCP server, a skill, three subagents with checked handoffs, and a deliberate context system.

## Setup (6 steps)

You need Python 3.10 or newer, Git, an internet connection, and Claude Code signed in with a paid Claude plan (the VS Code extension or the `claude` CLI).

1. Clone the repo:
   `git clone https://github.com/Saketh-2407/dn-build-test-darpally.git` then `cd dn-build-test-darpally`
2. Run setup: `python bootstrap.py` (Windows: `py bootstrap.py`).
   It creates `.venv`, installs the pinned dependencies, writes `.mcp.json` for your OS, runs the test suite, starts the MCP server and lists its tools. If any step fails, it says what to do and exits non-zero.
3. Open the folder in Claude Code.
4. Approve the `dn-repurposer` MCP server when prompted. Type `/mcp` and check it shows as connected.
5. Run a post through the system:
   `/repurpose-post https://disruptionnow.com/blog/your-hospital-bill-is-wrong-ai-can-prove-it`
   You can also pass a topic word (`/repurpose-post hackathon`) or nothing, to pick from a list.
6. Read the result in `samples/<post-slug>/final.md`.

A run takes a few minutes. Three subagents work in sequence, and the Reviewer can send a draft back up to twice. Start a new conversation for each post.

## How it works

```
/repurpose-post <url or topic>
   |
   v
skill (orchestrator)            list_blog_posts
   |
   v
dn-analyst                      fetch_blog_post, verify_quotes, get_brand_rule
   |  brief: a facts ledger; every fact carries a verbatim source quote, proven by verify_quotes
   v  validate_handoff("brief")
dn-writer                       get_brand_rule, lint_draft   (no tool to read the post)
   |  draft: LinkedIn + Instagram; every factual sentence mapped to a fact id
   v  validate_handoff("draft")
dn-reviewer                     lint_draft, verify_quotes, get_brand_rule
   |  review: PASS | REVISE with exact fixes | SHIP_WITH_FLAGS | BLOCKED
   v  validate_handoff("review")      REVISE goes back to the Writer, at most twice
save_run                        final lint gate, writes samples/<slug>/
```

| The brief asks for | Where it is                                                      |
| ------------------ | ---------------------------------------------------------------- |
| An MCP server      | `mcp_server/` (Python, stdio, 7 tools)                           |
| A skill            | `.claude/skills/repurpose-post/SKILL.md`                         |
| Subagents          | `.claude/agents/dn-analyst.md`, `dn-writer.md`, `dn-reviewer.md` |
| A context system   | `CLAUDE.md`, `CONTEXT.md`, `contracts/`                          |

### MCP tools

| Tool               | Its one job                                                                                            |
| ------------------ | ------------------------------------------------------------------------------------------------------ |
| `list_blog_posts`  | Search the cached index of DN posts by topic words in the title or URL.                                |
| `fetch_blog_post`  | Fetch one post live and return its clean body text, cited sources and byline.                          |
| `get_brand_rule`   | Return one doctrine category: DN's exact page text plus a structured index.                            |
| `lint_draft`       | Run literal brand checks (em dashes, banned words, cliches) on copy we generate. Never on source text. |
| `verify_quotes`    | Prove each quote appears word for word in the post body.                                               |
| `validate_handoff` | Check a brief, draft or review against its JSON contract.                                              |
| `save_run`         | Write a finished run to `samples/`. Refuses to save a PASS that fails the linter.                      |

Every tool returns structured data. Failures return `{"error", "hint"}`, so an agent can correct itself instead of crashing.

### Why three agents

- **Analyst** reads the post and builds the facts ledger. Each fact carries a verbatim quote, and `verify_quotes` proves the quote is in the post.
- **Writer** never sees the post and has no tool that can fetch it. It can only use proven facts, so it cannot invent one.
- **Reviewer** runs three checks: the linter for rules that are always literal, a fact check that every number and claim traces to a proven quote, and a line-by-line review against the Gate for rules that need judgment. It never rewrites. It returns exact fixes.

The handoff is the point. The Analyst's ledger is the only material the Writer can draw on, and the Writer's claims map is what the Reviewer audits.

## Sample outputs

Three posts, chosen to stress different paths through the system. All three were produced by the final version of the pipeline.

| Post                                                                                        | What it tests                                                                                           | Review rounds | Verdict                                        |
| ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ------------- | ---------------------------------------------- |
| [Future of Data Hackathon](samples/40-student-slots-real-world-impact/final.md)             | DN's own event, so the copy says "we". A past event, so past tense and no expired call to action.       | 2             | PASS                                           |
| [You Don't Have a Model Problem](samples/you-don-t-have-a-model-problem/final.md)           | An enterprise topic, a title with an em dash, and numbers from cited third parties (MIT, The Next Web). | 3             | PASS                                           |
| [Your Hospital Bill Is Wrong](samples/your-hospital-bill-is-wrong-ai-can-prove-it/final.md) | A consumer topic, dollar figures with hedges, and an insider term that needs a plain definition.        | 2             | PASS, with 1 definition for a human to confirm |

Each `final.md` has the LinkedIn post, the Instagram caption, a visual note, the facts used with their source quotes, a review summary and an AI disclosure. Each folder also keeps every brief, draft and review, so any line can be traced back to the post.

## What is live, what is cached, and what is mine

- **Live:** every blog post is fetched from disruptionnow.com at run time.
- **Cached:** the list of posts (`mcp_server/cache/blog-index.json`) and DN's doctrine (`mcp_server/cache/brand-rules/`, seven brand hub pages stored word for word). Rebuild both with `python bootstrap.py --refresh`. The brief says the blog has about 55 posts; the live archive had 67 when I built the index.
- **My conventions, not DN doctrine:** the brand hub has no channel rules, so post length, hook length, paragraph shape and hashtag counts are mine. `dn-writer.md` labels them that way.
- **No outside research, by design.** DN's doctrine says never end up vaguer than the source and always carry the because, so every fact comes from the post. The one exception is a plain-language definition of an insider term, because the doctrine also says "no insider word without a plain explanation next to it". The Writer tags it, the Reviewer checks it, and `final.md` lists it for a human to confirm.
- **AI disclosure:** DN's rule is radical AI transparency. Every `final.md` carries a disclosure line. I kept it out of the caption itself, because a human approves the copy before it is published.

## Verification

- **63 unit tests.** `bootstrap.py` runs them. To run them yourself, use the project's virtual environment: `.venv/bin/python -m unittest discover tests` (Windows: `.venv\Scripts\python -m unittest discover tests`).
- **Every post in the archive.** `python -m mcp_server.check_archive` fetched all 67 posts: 67 OK, 418 to 1,568 words each, every one with an author, date, bio and sources, and no leftover share bars, FAQs or bios in the text. Report: `reports/archive-check.md`.
- **Two operating systems.** `bootstrap.py` was run end to end on Windows and on a clean Linux clone. macOS uses the same setup path as Linux.
- **Doctrine fidelity.** The cached doctrine was compared line by line with the brand hub pages.

## Known limitations

- **Judgment is model-based.** The linter, the fact check and the contracts are deterministic. The Gate review is not, so two runs on the same post can word things differently.
- **Topic search matches words, not meaning.** "hospital" finds the hospital-bill post; "healthcare" finds nothing and shows sample titles instead.
- **The index is a snapshot.** A newer post still works by URL, but topic search will not find it until `--refresh`.
- **Thin posts stop.** A post with fewer than 3 usable facts ends with a clear message instead of thin copy.
- **Numbers are verified against the post, not DN's records.** The doctrine says to verify a number against the authoritative document. The Reviewer can only check it against the source post, and the system says so.

## What I would build next

- A batch mode that repurposes the newest posts each week into a content calendar.
- A paginated index builder and meaning-based topic search, for an archive of 500 or more posts.
- An evaluation set of deliberately flawed drafts, to measure how often the Reviewer catches each rule.
- A scheduled `--refresh` that flags any change to DN's doctrine pages.
- Image briefs that follow DN's photography and logo rules.

## Time

About 6 hours of hands-on time across two sessions. The brief says to stop at three hours, so here is where the rest went.

The core pipeline (MCP server, three agents and the skill) worked end to end in the first session. I spent the remaining time auditing the samples against DN's doctrine myself and fixing what the audits found:

- The copy described DN's own hackathon in the third person, because the fetcher stripped the author bio that says the event runs under MidwestCon.
- Past-tense copy turned a pre-event promise into a claim about who attended.
- The Reviewer listed "optional polish" and still passed the draft.
- Setup only worked on Windows.
- The handoff contracts were described in prompts but not enforced in code.

Each fix is its own commit, so the history shows what changed and why.
