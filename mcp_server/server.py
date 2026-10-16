"""dn-repurposer MCP server (stdio transport).

Run from the project root: python -m mcp_server.server
"""

from mcp.server.mcpserver import MCPServer

from mcp_server.tools import (
    fetch_blog_post,
    get_brand_rule,
    lint_draft,
    list_blog_posts,
    save_run,
    validate_handoff,
    verify_quotes,
)

server = MCPServer(
    name="dn-repurposer",
    instructions=(
        "Tools for turning a Disruption Now blog post into on-brand LinkedIn and Instagram copy. "
        "Find posts with list_blog_posts, read one with fetch_blog_post, load doctrine with "
        "get_brand_rule, check only our generated drafts with lint_draft, prove every fact is quoted "
        "word-for-word from the post with verify_quotes, check every brief, draft and review against its "
        "contract with validate_handoff, and write the finished run with save_run."
    ),
)

for tool in (list_blog_posts, fetch_blog_post, get_brand_rule, lint_draft, verify_quotes, validate_handoff, save_run):
    server.tool()(tool)


if __name__ == "__main__":
    server.run(transport="stdio")
