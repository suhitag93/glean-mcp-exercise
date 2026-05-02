"""
Glean Chat API client.

Combines search results (retrieved context) with the user's question
and calls the Glean Chat API to produce a grounded, cited answer.
"""

from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import Config
from .models import ChatResponse, CitationSource, SearchResult


def chat(
    question: str,
    search_results: list[SearchResult],
    *,
    cfg: Config,
    chat_session_id: str | None = None,
    save_chat: bool = False,
) -> ChatResponse:
    """
    Send a question to the Glean Chat API with search results as grounding context.

    The Glean Chat API natively supports RAG: we provide source documents and it
    generates a cited answer referencing only those sources.

    Args:
        question: The user's natural-language question.
        search_results: Results from the Glean Search API to ground the answer.
        cfg: Config instance.
        chat_session_id: Optional session ID to continue a multi-turn conversation.
        save_chat: Whether to persist the chat session in Glean (default False).

    Returns:
        ChatResponse with the answer text and source citations.
    """
    payload = _build_chat_payload(
        question=question,
        search_results=search_results,
        chat_session_id=chat_session_id,
        save_chat=save_chat,
    )
    return _post_chat(payload, cfg=cfg)


def _build_chat_payload(
    *,
    question: str,
    search_results: list[SearchResult],
    chat_session_id: str | None,
    save_chat: bool,
) -> dict:
    """Construct the Chat API request body."""
    # Build the message with context injected before the question.
    # We inline the retrieved snippets so the model can cite them.
    context_block = _build_context_block(search_results)
    user_message = f"{context_block}\n\n---\nQuestion: {question}"

    messages = [
        {
            "role": "USER",
            "fragments": [{"text": user_message}],
        }
    ]

    payload: dict = {
        "messages": messages,
        "saveChat": save_chat,
        "stream": False,
    }

    if chat_session_id:
        payload["chatSessionId"] = chat_session_id

    # Pass source document IDs so Glean can generate proper citations
    source_doc_ids = _extract_doc_ids(search_results)
    if source_doc_ids:
        payload["sourceDocumentIds"] = source_doc_ids

    return payload


def _build_context_block(results: list[SearchResult]) -> str:
    """Format retrieved documents into a context block for the prompt."""
    if not results:
        return "No relevant documents were retrieved."

    lines = [
        "Use ONLY the following retrieved knowledge-base articles to answer the question.",
        "Cite the source by its [number] when you use information from it.",
        "",
    ]
    for i, r in enumerate(results, start=1):
        title = r.title or "Untitled"
        url = r.url or ""
        snippets = [s.text for s in (r.snippets or []) if s.text]
        snippet_text = " … ".join(snippets[:3]) if snippets else "(no preview)"
        lines.append(f"[{i}] {title}")
        if url:
            lines.append(f"    URL: {url}")
        lines.append(f"    Content: {snippet_text}")
        lines.append("")

    return "\n".join(lines)


def _extract_doc_ids(results: list[SearchResult]) -> list[str]:
    doc_ids: list[str] = []
    for r in results:
        if r.metadata and r.metadata.document_id:
            doc_ids.append(r.metadata.document_id)
        elif r.document:
            doc_id = r.document.get("id", "")
            if doc_id:
                doc_ids.append(doc_id)
    return doc_ids


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
def _post_chat(payload: dict, *, cfg: Config) -> ChatResponse:
    headers = {
        "Authorization": f"Bearer {cfg.user_token}",
        "Content-Type": "application/json",
    }
    if cfg.act_as_email:
        headers["X-Glean-ActAs"] = cfg.act_as_email
    url = f"{cfg.base_url}/rest/api/v1/chat"

    with httpx.Client(timeout=60) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()

    data = response.json()
    import json, os
    if os.getenv("GLEAN_DEBUG"):
        print("RAW CHAT RESPONSE:", json.dumps(data, indent=2)[:3000])
    return _parse_chat_response(data)


def _parse_chat_response(data: dict) -> ChatResponse:
    """Parse the Glean Chat API response into a ChatResponse model."""
    # The Chat API wraps the response message under different keys depending on version.
    # We handle both the legacy and current response shapes.
    answer_text = ""
    sources: list[CitationSource] = []

    # Current API shape: { "messages": [...], "chatSessionId": "..." }
    messages = data.get("messages", [])
    for msg in messages:
        if msg.get("role", "").upper() in ("ASSISTANT", "GLEAN"):
            fragments = msg.get("fragments", [])
            for fragment in fragments:
                if fragment.get("type") == "TEXT" or "text" in fragment:
                    answer_text += fragment.get("text", "")
                elif fragment.get("type") == "CITATION":
                    citation = fragment.get("citation", {})
                    doc = citation.get("document", {})
                    sources.append(
                        CitationSource(
                            document_id=doc.get("id"),
                            title=doc.get("title") or citation.get("sourceTitle"),
                            url=doc.get("url") or citation.get("sourceUrl"),
                            datasource=doc.get("datasource"),
                            snippet=citation.get("snippet"),
                        )
                    )

    # Fallback: older API shape with a top-level "answer" key
    if not answer_text and "answer" in data:
        answer_data = data["answer"]
        if isinstance(answer_data, str):
            answer_text = answer_data
        elif isinstance(answer_data, dict):
            answer_text = answer_data.get("text", "")

    # Extract cited sources from top-level "citations" if present
    if not sources:
        for citation in data.get("citations", []):
            doc = citation.get("document", {})
            sources.append(
                CitationSource(
                    document_id=doc.get("id") or citation.get("documentId"),
                    title=doc.get("title") or citation.get("title"),
                    url=doc.get("url") or citation.get("url"),
                    datasource=doc.get("datasource"),
                    snippet=citation.get("snippet"),
                )
            )

    # De-duplicate sources by URL
    seen_urls: set[str] = set()
    deduped: list[CitationSource] = []
    for s in sources:
        key = s.url or s.document_id or s.title or ""
        if key and key not in seen_urls:
            seen_urls.add(key)
            deduped.append(s)

    return ChatResponse(
        answer=answer_text.strip() or "I could not generate an answer from the available sources.",
        sources=deduped,
        chat_session_id=data.get("chatSessionId"),
    )
