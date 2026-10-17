# Context system

How this repo decides what each agent knows, when it knows it, and why.

## The rule

Every agent gets exactly what its job needs, and nothing else.

Extra context is not free. It costs tokens, slows the run and gives a model more to drift on. In this system it would also let the wrong agent see the wrong thing: a Writer that can read the post can invent from it.

## What lives where

| Layer                 | What it holds                                                      | When it is in context                                   |
| --------------------- | ------------------------------------------------------------------ | ------------------------------------------------------- |
| `CLAUDE.md`           | Purpose, how to run, rules for the orchestrator, this map in short | Main session only. Kept under 50 lines.                 |
| `SKILL.md`            | The SOP: steps, the revision loop, stop conditions                 | Main session, while `/repurpose-post` runs              |
| `.claude/agents/*.md` | One agent's job, inputs, rules and output contract                 | That agent only, as its system prompt                   |
| Blog post             | Clean article text from `fetch_blog_post`                          | The Analyst only, fetched on demand                     |
| Doctrine              | One category per `get_brand_rule` call                             | Fetched on demand, only the categories each agent needs |
| Lint rules            | Banned words, em dash rules                                        | Never. `lint_draft` applies them in code.               |
| Contracts             | `contracts/*.schema.json`                                          | Never. `validate_handoff` applies them in code.         |
| Past runs             | `samples/`                                                         | Never                                                   |

Doctrine each agent loads:

- **Analyst:** the-gate and voice-principles, to choose an opener and read the post the way DN would.
- **Writer:** voice-principles, the-gate, mechanics, say-this-not-that and anti-slop-catalog.
- **Reviewer:** the Writer's five, plus where-the-brand-speaks, so it protects DN's earned phrases instead of flagging them as slop.

## How agents avoid drowning in their own history

- **Fresh context per agent.** A subagent starts with its system prompt and the handoff, nothing more. `omitClaudeMd: true` keeps even `CLAUDE.md` out.
- **The orchestrator never reads the post.** It passes JSON between agents unchanged, so its own context holds handoffs, not article text.
- **Revisions do not replay the past.** The Writer gets the brief, its latest draft and the latest review. Earlier rounds stay on disk.
- **One post per conversation.** The next post starts a new conversation, so run three never carries run one.
- **Disk is the memory.** Everything worth keeping goes to `samples/<slug>/` through `save_run`, not into a conversation.

## Handoff contracts

Three JSON shapes, defined in `contracts/` and checked by `validate_handoff` after every step.

- **brief** (Analyst to Writer): the facts ledger (id, fact, verbatim source_quote, attribution, because, priority), plus the core point, opener, cautions, timeframe and first_party.
- **draft** (Writer to Reviewer): the LinkedIn text, the Instagram caption and hashtags, a claims_map that ties every factual sentence to a fact id, and any definitions.
- **review** (Reviewer to Writer, or to `save_run`): the verdict, violations with severity and exact fixes, and a sentence-by-sentence audit.

Rules a schema cannot express are checked in code. A draft can only cite fact ids that exist in its brief. A PASS cannot carry violations. Round 2 cannot return REVISE. An invalid handoff goes back to the same agent once; if it is still invalid, the run stops. The orchestrator never repairs a handoff itself.

## Tool boundaries

- **Least privilege.** Each agent's tool list is in its frontmatter. The Writer has `get_brand_rule` and `lint_draft` only, so "never read the source" is enforced by permissions, not by asking nicely. The Reviewer can prove a quote with `verify_quotes` without loading the whole post.
- **Code for literal rules, judgment for the rest.** Em dashes, banned words and cliches are checked by `lint_draft` every time. Model judgment is reserved for rules that need it: the Gate's four questions, contrast framing, carrying the because.
- **Recoverable failures.** Tools return `{"error", "hint"}` instead of raising, so an agent can retry with a fix.
- **The linter only touches our copy.** DN's own posts use em dashes. Linting the source would be noise.

## Why the doctrine is cached word for word

The Reviewer's verdict is only as good as the doctrine it reads. Each file in `mcp_server/cache/brand-rules/` holds the exact page text from DN's brand hub (`verbatim`) plus a structured index the agents can scan. If the two ever differ, the Writer and Reviewer are told the verbatim text wins. `python bootstrap.py --refresh` fetches it again.

## Decisions, and what they cost

- **The Writer is blind to the source.** It cannot invent a fact. The cost: the Analyst has to be thorough, because anything it leaves out is gone.
- **The Reviewer sees the ledger, not the post.** It checks "clearer than the source" against each fact's verbatim quote, without re-reading the whole article.
- **No outside research.** DN's own rules make the post the source of truth. The cost: no trend context.
- **Two revisions, then an honest verdict.** SHIP_WITH_FLAGS when only judgment calls remain, BLOCKED when a hard rule still fails. Never a PASS that is not one.
- **One explicit exception to source-only.** A plain-language definition of an insider term, because DN's Plain principle requires it. It is tagged, checked and listed in `final.md` for a human.

## What breaks at 500 posts

- The index builder reads one page of the blog. It would need pagination.
- Topic search matches keywords in titles and URLs. It would need ranking or meaning-based search.
- Nothing else grows with the archive. Each run touches one post.

## Folder layout

```
.claude/
  agents/            dn-analyst.md, dn-writer.md, dn-reviewer.md
  skills/repurpose-post/SKILL.md
  settings.json      pre-approves the seven dn-repurposer tools
contracts/           brief, draft and review JSON schemas
mcp_server/
  server.py          registers the tools (stdio)
  tools/             one module per tool
  cache/             blog index, verbatim doctrine, lint rules
  build_index.py, build_brand_cache.py, check_archive.py
reports/             archive-check.md (every post fetched and checked)
samples/             one folder per run: brief, drafts, reviews, final.md
tests/               63 unit tests
bootstrap.py         one-command setup and self-check
CLAUDE.md            orchestrator context
```
