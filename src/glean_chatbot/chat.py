"""
Glean Chat API client.

Combines search results (retrieved context) with the user's question
and calls the Glean Chat API to produce a grounded, cited answer.
"""

from __future__ import annotations

import json
import os

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

    Args:
        question: The user's natural-language question.
        search_results: Results from the Glean Search API to ground the answer.
        cfg: Config instance.
        chat_session_id: Optional session ID to continue a multi-turn conversation.
        save_chat: Whether to persist the chat session in Glean.

    Returns:
        ChatResponse with the answer text and source citations.
    """
    context = _build_context_block(search_results)
    message_text = f"{context}\n\n---\nQuestion: {question}"

    payload: dict = {
        "messages": [
            {"fragments": [{"text": message_text}]},
        ],
        "saveChat": save_chat,
        "stream": False,
    }
    if chat_session_id:
        payload["chatSessionId"] = chat_session_id

    return _post_chat(payload, cfg=cfg)


def _build_context_block(results: list[SearchResult]) -> str:
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


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
def _post_chat(payload: dict, *, cfg: Config) -> ChatResponse:
    headers = {
        "Authorization": f"Bearer {cfg.chat_token}",
        "Content-Type": "application/json",
    }
    if cfg.act_as_email:
        headers["X-Glean-ActAs"] = cfg.act_as_email
    url = f"{cfg.base_url}/rest/api/v1/chat"

    with httpx.Client(timeout=60) as client:
        response = client.post(url, headers=headers, json=payload)
        if not response.is_success:
            print(f"  Chat error ({response.status_code}): {response.text}")
        response.raise_for_status()

    data = response.json()
    if os.getenv("GLEAN_DEBUG"):
        print("RAW CHAT RESPONSE:", json.dumps(data, indent=2)[:3000])
    return _parse_chat_response(data)


def _parse_chat_response(data: dict) -> ChatResponse:
    """
    Parse the Glean Chat API response.

    Per the official docs, the answer is in the LAST message's fragments.
    Each fragment has a 'text' key with the answer content.
    """
    answer = ""
    sources: list[CitationSource] = []

    messages = data.get("messages", [])
    if messages:
        # Take the last message — that's the assistant's reply per Glean docs
        last_message = messages[-1]
        fragments = last_message.get("fragments", [])
        for fragment in fragments:
            if isinstance(fragment, str):
                answer += fragment
            elif isinstance(fragment, dict):
                text = fragment.get("text", "")
                if text:
                    answer += text
                # Extract any structured citations
                citation = fragment.get("citation")
                if citation and isinstance(citation, dict):
                    doc = citation.get("document", {})
                    sources.append(CitationSource(
                        document_id=doc.get("id") or citation.get("documentId"),
                        title=doc.get("title") or citation.get("sourceTitle"),
                        url=doc.get("url") or citation.get("sourceUrl"),
                        datasource=doc.get("datasource"),
                        snippet=citation.get("snippet"),
                    ))

    # De-duplicate sources
    seen: set[str] = set()
    deduped: list[CitationSource] = []
    for s in sources:
        key = s.url or s.document_id or s.title or ""
        if key and key not in seen:
            seen.add(key)
            deduped.append(s)

    return ChatResponse(
        answer=answer.strip() or "I could not generate an answer from the available sources.",
        sources=deduped,
        chat_session_id=data.get("chatSessionId"),
    )
