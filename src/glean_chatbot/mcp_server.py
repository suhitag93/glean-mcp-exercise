"""
MCP server exposing the Glean RAG chatbot as a single tool.

Run with:
    python -m glean_chatbot.mcp_server

Or via the installed entry-point:
    glean-mcp

The server communicates over stdio, which is the standard transport for
MCP clients like Cursor, Claude Desktop, and the MCP CLI inspector.
"""

from __future__ import annotations

import json
import sys
from typing import Annotated

from mcp.server.fastmcp import FastMCP

from .chat import chat
from .config import get_config
from .models import ChatbotResult, CitationSource
from .search import search

mcp = FastMCP(
    name="glean-rag-chatbot",
    instructions=(
        "Use this server to ask questions about the Acme Corp internal knowledge base. "
        "The chatbot retrieves relevant documents from Glean and generates a grounded answer "
        "with source citations. Provide a clear, specific question for best results."
    ),
)


@mcp.tool(
    name="ask_glean",
    description=(
        "Ask a natural-language question about the Acme Corp knowledge base. "
        "The tool searches Glean for relevant documents, then uses Glean Chat to "
        "generate a grounded answer with source citations. "
        "Returns both the answer and the list of sources used."
    ),
)
def ask_glean(
    question: Annotated[str, "The natural-language question to answer"],
    num_results: Annotated[
        int,
        "Number of search results to retrieve and use as context (1–10, default 5)",
    ] = 5,
    datasource_filter: Annotated[
        str | None,
        "Optional: restrict search to a specific Glean datasource (e.g. 'glean-mcp-exercise')",
    ] = None,
    chat_session_id: Annotated[
        str | None,
        "Optional: Glean chat session ID to continue a multi-turn conversation",
    ] = None,
) -> str:
    """
    RAG pipeline: Search → Chat → Return answer + sources.

    Workflow:
    1. Call Glean Search API with the question to find relevant documents.
    2. Pass those documents as grounding context to the Glean Chat API.
    3. Return the generated answer along with source metadata.
    """
    cfg = get_config()

    # 1. Retrieve relevant documents via Glean Search
    results = search(
        question,
        cfg=cfg,
        page_size=max(1, min(num_results, 10)),
        datasource_filter=datasource_filter,
    )

    # 2. Generate a grounded answer via Glean Chat
    chat_response = chat(
        question=question,
        search_results=results,
        cfg=cfg,
        chat_session_id=chat_session_id,
    )

    # 3. Build the final result
    # Merge Chat API citations with Search result metadata for richer output
    sources = _merge_sources(chat_response.sources, results)
    result = ChatbotResult(
        answer=chat_response.answer,
        sources=sources,
        search_result_count=len(results),
    )

    return _format_output(result)


def _merge_sources(
    chat_sources: list[CitationSource],
    search_results,
) -> list[CitationSource]:
    """
    Combine citation sources from the Chat API with metadata from search results.

    The Chat API may return minimal citation info; the search results have richer
    metadata (title, URL, datasource). We use search results as the primary source
    of truth and supplement with any additional citations from the Chat API.
    """
    merged: list[CitationSource] = []
    seen_ids: set[str] = set()

    # First, include search-result-derived sources (have the richest metadata)
    for r in search_results:
        doc_id = (r.metadata and r.metadata.document_id) or (r.document and r.document.get("id")) or ""
        url = r.url or ""
        key = doc_id or url
        if key and key not in seen_ids:
            seen_ids.add(key)
            snippet = ""
            if r.snippets:
                snippet = r.snippets[0].text if r.snippets[0].text else ""
            merged.append(
                CitationSource(
                    document_id=doc_id or None,
                    title=r.title,
                    url=url or None,
                    datasource=(r.metadata and r.metadata.datasource) or None,
                    snippet=snippet or None,
                )
            )

    # Then append any Chat API citations not already included
    for s in chat_sources:
        key = s.document_id or s.url or ""
        if key and key not in seen_ids:
            seen_ids.add(key)
            merged.append(s)

    return merged


def _format_output(result: ChatbotResult) -> str:
    """Render the chatbot result as a human-readable Markdown string."""
    lines: list[str] = [
        "## Answer",
        "",
        result.answer,
        "",
    ]

    if result.sources:
        lines.append("## Sources")
        lines.append("")
        for i, source in enumerate(result.sources, start=1):
            title = source.title or "Untitled"
            url = source.url or ""
            datasource = source.datasource or ""
            snippet = source.snippet or ""

            source_line = f"{i}. **{title}**"
            if url:
                source_line = f"{i}. [{title}]({url})"
            if datasource:
                source_line += f" *(datasource: {datasource})*"
            lines.append(source_line)

            if snippet:
                lines.append(f"   > {snippet[:200]}")
        lines.append("")

    lines.append(f"*Retrieved {result.search_result_count} document(s) from Glean search.*")

    return "\n".join(lines)


def main() -> None:
    """Start the MCP server on stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
