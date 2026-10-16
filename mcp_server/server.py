"""dn-repurposer MCP server (stdio transport).

Run from the project root: python -m mcp_server.server
"""

from mcp.server.mcpserver import MCPServer

from mcp_server.tools import fetch_blog_post, get_brand_rule, lint_draft, list_blog_posts

server = MCPServer(
    name="dn-repurposer",
    instructions=(
        "Tools for turning a Disruption Now blog post into on-brand LinkedIn and Instagram copy. "
        "Find posts with list_blog_posts, read one with fetch_blog_post, load doctrine with "
        "get_brand_rule, and check only our generated drafts with lint_draft."
    ),
)

for tool in (list_blog_posts, fetch_blog_post, get_brand_rule, lint_draft):
    server.tool()(tool)


if __name__ == "__main__":
    server.run(transport="stdio")
