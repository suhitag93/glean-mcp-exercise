"""
Glean Chat API client using the official Glean Python SDK.

Uses create() (non-streaming) — the sandbox returns a complete JSON
response. The answer is in the message where messageType == "CONTENT".
"""

from __future__ import annotations

import httpx
from glean.api_client import Glean, models

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

    Streams the response via the official Glean SDK and collects all chunks
    into a single answer string.

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

    kwargs: dict = dict(
        messages=[
            {
                "fragments": [
                    models.ChatMessageFragment(text=message_text),
                ],
            }
        ],
    )
    if chat_session_id:
        kwargs["chat_session_id"] = chat_session_id

    glean_kwargs: dict = dict(
        api_token=cfg.chat_token,
        server_url=cfg.base_url,
    )
    # The SDK has no built-in act_as param — inject the header via a custom client
    if cfg.act_as_email:
        glean_kwargs["client"] = httpx.Client(
            headers={"X-Glean-ActAs": cfg.act_as_email},
            timeout=httpx.Timeout(120.0),
        )
    glean_kwargs["timeout_ms"] = 120_000

    with Glean(**glean_kwargs) as glean:
        response = glean.client.chat.create(**kwargs)

    return _parse_response(response)


def _parse_response(response) -> ChatResponse:
    """
    Extract the answer from the SDK response.

    The sandbox returns a full JSON response where the final answer is in
    the message with messageType == "CONTENT".
    """
    answer = ""
    sources: list[CitationSource] = []
    chat_id: str | None = None

    if hasattr(response, "chat_id"):
        chat_id = response.chat_id

    messages = getattr(response, "messages", None) or []
    for msg in messages:
        msg_type = getattr(msg, "message_type", None) or getattr(msg, "messageType", None)
        if str(msg_type).upper() == "CONTENT":
            for fragment in getattr(msg, "fragments", None) or []:
                text = getattr(fragment, "text", None)
                if text:
                    answer += text

    return ChatResponse(
        answer=answer.strip() or "I could not generate an answer from the available sources.",
        sources=sources,
        chat_session_id=chat_id,
    )


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
