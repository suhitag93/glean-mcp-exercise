"""
Glean Search API client.

Sends a natural-language query to the Glean Search API and returns
structured SearchResult objects that are then passed to the Chat API.
"""

from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import Config
from .models import SearchResponse, SearchResult, SearchResultMetadata, SearchResultSnippet


def search(
    query: str,
    *,
    cfg: Config,
    page_size: int = 5,
    datasource_filter: str | None = None,
) -> list[SearchResult]:
    """
    Query Glean Search API and return the top results.

    Args:
        query: Natural-language search query.
        cfg: Config instance.
        page_size: Maximum number of results to return (1–20).
        datasource_filter: Optional datasource name to restrict results.

    Returns:
        List of SearchResult objects, ordered by relevance.
    """
    page_size = max(1, min(page_size, 20))

    payload: dict = {
        "query": query,
        "pageSize": page_size,
        "requestOptions": {
            "facetFilters": [],
        },
    }

    if datasource_filter:
        payload["requestOptions"]["datasourceFilter"] = datasource_filter

    results = _post_search(payload, cfg=cfg)
    return results


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
def _post_search(payload: dict, *, cfg: Config) -> list[SearchResult]:
    headers = {
        "Authorization": f"Bearer {cfg.user_token}",
        "Content-Type": "application/json",
    }
    url = f"{cfg.base_url}/rest/api/v1/search"

    with httpx.Client(timeout=30) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()

    data = response.json()
    return _parse_search_response(data)


def _parse_search_response(data: dict) -> list[SearchResult]:
    """Parse the raw Glean Search API response into SearchResult models."""
    raw_results = data.get("results", [])
    parsed: list[SearchResult] = []

    for item in raw_results:
        # Extract snippets
        snippets: list[SearchResultSnippet] = []
        for s in item.get("snippets", []):
            text = s.get("snippet", {}).get("text", "") or s.get("text", "")
            if text:
                snippets.append(SearchResultSnippet(text=text))

        # Extract metadata from the nested document structure
        doc = item.get("document", {})
        metadata_raw = doc.get("metadata", {})
        container = metadata_raw.get("container", "")
        datasource = doc.get("datasource", "") or metadata_raw.get("datasource", "")

        metadata = SearchResultMetadata(
            datasource=datasource,
            object_type=doc.get("objectType", ""),
            document_id=doc.get("id", ""),
            update_time=metadata_raw.get("updateTime", ""),
        )

        parsed.append(
            SearchResult(
                title=item.get("title", doc.get("title", "")),
                url=item.get("url", doc.get("url", "")),
                snippets=snippets,
                document=doc,
                metadata=metadata,
            )
        )

    return parsed


def format_results_for_context(results: list[SearchResult]) -> str:
    """
    Format search results as a context block to include in the Chat API prompt.

    Each result is rendered as a numbered section with title, URL, and snippet.
    """
    if not results:
        return "No relevant documents found."

    parts: list[str] = []
    for i, result in enumerate(results, start=1):
        title = result.title or "Untitled"
        url = result.url or ""
        snippet_texts = [s.text for s in (result.snippets or []) if s.text]
        snippet = " … ".join(snippet_texts[:2]) if snippet_texts else ""

        section = f"[{i}] {title}"
        if url:
            section += f"\n    URL: {url}"
        if snippet:
            section += f"\n    {snippet}"
        parts.append(section)

    return "\n\n".join(parts)
