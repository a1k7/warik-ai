from pydantic import BaseModel, Field
from app.tools.base import BaseTool, ToolContext, ToolResult
from ddgs import DDGS

class WebSearchInput(BaseModel):
    query: str = Field(..., description="The search query")

class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the internet for real-time information, news, movie release dates, or general facts. Returns snippets and URLs."
    capability = "research"
    input_schema = WebSearchInput
    requires_confirmation = False
    is_mutating = False

    def execute(self, ctx: ToolContext, params: WebSearchInput) -> ToolResult:
        try:
            results = DDGS().text(params.query, max_results=5)
            if not results:
                return ToolResult(success=True, message="No search results found.", data={"results": []})

            formatted_results = []
            for r in results:
                formatted_results.append({
                    "title": r.get("title"),
                    "snippet": r.get("body"),
                    "url": r.get("href")
                })

            return ToolResult(
                success=True,
                message=f"Found {len(results)} results for '{params.query}'.",
                data={"type": "web_search", "results": formatted_results}
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Web search failed: {str(e)}")
