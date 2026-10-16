---
name: repurpose-post
description: Turn a Disruption Now blog post into a LinkedIn post and an Instagram caption that pass DN's published brand doctrine, using the dn-repurposer MCP tools and three subagents (Analyst, Writer, Reviewer). Use when asked to repurpose a DN blog post, given a disruptionnow.com/blog URL, or asked for DN social content on a topic.
argument-hint: "[post URL, topic word, or nothing]"
allowed-tools: mcp__dn-repurposer__list_blog_posts mcp__dn-repurposer__validate_handoff mcp__dn-repurposer__save_run
---

# Repurpose a DN blog post (SOP)

This skill turns one Disruption Now blog post into one LinkedIn post and one 
Instagram caption that pass DN's brand doctrine, and saves the run to samples/.

You are the orchestrator. You never write or edit the social copy yourself, and 
you never read the blog post yourself. The three subagents do the work. You pass 
their JSON between them exactly as received, never summarized or edited.

Input: $ARGUMENTS (a post URL, a topic word, or nothing).

## Step 0: Preflight
Confirm the dn-repurposer MCP tools are available. If they are not, stop and 
tell the user to open /mcp and approve or reconnect "dn-repurposer".

## Step 1: Pick the post
- A disruptionnow.com/blog URL was given: use it.
- A topic word was given: call list_blog_posts(topic) and pick the most relevant 
  post. If nothing matches, show the sample titles it returns and ask the user 
  to choose.
- Nothing was given: call list_blog_posts() and ask the user to choose.
Make the slug from the URL's last path segment: lowercase, any character outside 
a-z, 0-9, and "-" replaced with "-", cut to 80 characters.

## Checking a handoff
Every brief, draft and review goes through validate_handoff before it moves on:
- If it returns valid: true, continue.
- If it returns valid: false, send the JSON back to the same subagent once, with 
  the errors, and ask for the corrected JSON only. Check the corrected JSON 
  again.
- If it is still invalid, stop and report the errors to the user.
Never fix a handoff yourself.

## Step 2: Analyst
Delegate to the dn-analyst subagent with the post URL and today's date in YYYY-MM-DD form.
It returns the brief JSON. If it returned an error, stop and report it to the 
user. Otherwise call validate_handoff("brief", brief). This also catches 
quote_check.missing not being 0 and fewer than 3 facts.

## Step 3: Writer, first draft
Delegate to the dn-writer subagent with the full brief JSON and round 0.
Call validate_handoff("draft", draft, brief).

## Step 4: Reviewer
Delegate to the dn-reviewer subagent with the full brief JSON, the full draft 
JSON, and the round number.
Call validate_handoff("review", review).

## Step 5: Revision loop (at most 2 revisions)
If the verdict is REVISE, delegate to dn-writer with the brief, the latest draft, 
and the Reviewer's JSON (round + 1). Call validate_handoff("draft", draft, 
brief), then go back to Step 4.
The loop ends on PASS, SHIP_WITH_FLAGS, or BLOCKED. The Reviewer will not return 
REVISE for round 2.

## Step 6: Save
Call save_run(slug, run) with:
- source: {url, title} from the brief
- brief: the brief JSON
- drafts: every draft JSON, in order
- reviews: every review JSON, in order
- final: {verdict, linkedin_text, instagram_caption, instagram_hashtags, 
  visual_note, flags, definitions}, taken from the last draft and the last 
  review. flags is the list of still-open violations (rule and line) for 
  SHIP_WITH_FLAGS or BLOCKED, and empty for PASS. definitions is the last 
  draft's "definitions" list ([] when it has none).
If save_run refuses, do not change the copy to get around it. Set the verdict to 
BLOCKED, save again, and tell the user the linter caught something the Reviewer 
missed.

## Step 7: Report
Tell the user: the post title, the verdict, how many review rounds ran, any open 
flags, the saved file paths, and the final LinkedIn and Instagram text.

## Rules
- Every fact in the copy comes from the source post, through the Analyst's 
  verified ledger. No outside research.
- Handoffs are contracts: every brief, draft and review is checked against 
  contracts/*.schema.json with validate_handoff before it moves on.
- The linter only checks copy we generate, never the source post.
- Run one post per conversation, so context stays small. Start a new 
  conversation for the next post.
- Never ask the user how to frame a time-bound post (an event, a deadline, a 
  registration). The brief's timeframe decides: a past event becomes evergreen 
  copy with no expired call to action. Only ask the user to choose a post when 
  none was given.
