"""
Glean Chat API client using the official Glean Python SDK.

Uses create_stream() per the official developer docs — the non-streaming
endpoint times out on the support-lab sandbox instance.
"""

from __future__ import annotations

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
    if cfg.act_as_email:
        glean_kwargs["act_as"] = cfg.act_as_email

    answer_chunks: list[str] = []
    with Glean(**glean_kwargs) as glean:
        response_stream = glean.client.chat.create_stream(**kwargs)
        for chunk in response_stream:
            if chunk:
                answer_chunks.append(chunk)

    answer = "".join(answer_chunks).strip()
    return ChatResponse(
        answer=answer or "I could not generate an answer from the available sources.",
        sources=[],
        chat_session_id=None,
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
