"""
End-to-end smoke test and interactive CLI for the Glean RAG chatbot.

Usage (from the repo root with the venv active):
    python scripts/test_pipeline.py

Runs the initial question and a hardcoded follow-up, then drops into
an interactive loop for further questions. Type 'quit' to exit.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import find_dotenv, dotenv_values

_dotenv_path = (
    find_dotenv(raise_error_if_not_found=False, usecwd=False)
    or find_dotenv(raise_error_if_not_found=False, usecwd=True)
)
for _k, _v in dotenv_values(_dotenv_path).items():
    if _v is not None:
        os.environ.setdefault(_k, _v)

import httpx

from glean_chatbot.chat import chat
from glean_chatbot.config import get_config
from glean_chatbot.models import SearchResult, SearchResultSnippet
from glean_chatbot.search import _extract_snippet_text

INSTANCE   = os.environ["GLEAN_INSTANCE"]
USER_TOKEN = os.environ["GLEAN_USER_TOKEN"]
CHAT_TOKEN = os.environ.get("GLEAN_CHAT_TOKEN") or USER_TOKEN
ACT_AS     = os.environ.get("GLEAN_ACT_AS", "")
DATASOURCE = os.environ.get("GLEAN_DATASOURCE", "interviewds")
BASE_URL   = os.environ.get("GLEAN_BASE_URL", f"https://{INSTANCE}-be.glean.com")

SEARCH_HEADERS = {"Authorization": f"Bearer {USER_TOKEN}", "Content-Type": "application/json"}
if ACT_AS:
    SEARCH_HEADERS["X-Glean-ActAs"] = ACT_AS

TEST_QUESTION = "What is the PTO policy?"
FOLLOWUP      = "Are there multiple companies PTO policies here?"


def do_search(question: str) -> list[dict]:
    payload = {
        "query": question,
        "pageSize": 5,
        "requestOptions": {"datasourceFilter": DATASOURCE},
    }
    r = httpx.post(f"{BASE_URL}/rest/api/v1/search", headers=SEARCH_HEADERS, json=payload, timeout=15)
    r.raise_for_status()
    results = r.json().get("results", [])
    print(f"  [{len(results)} results]", end="  ")
    for res in results[:3]:
        print(f"\n    • {res.get('title', '?')} — {res.get('url', '')}")
    return results


def do_chat(question: str, results: list[dict], cfg, session_id: str | None) -> tuple[str, str | None]:
    search_results = [
        SearchResult(
            title=r.get("title", ""),
            url=r.get("url", ""),
            snippets=[
                SearchResultSnippet(text=_extract_snippet_text(s))
                for s in r.get("snippets", [])
                if _extract_snippet_text(s)
            ],
        )
        for r in results
    ]
    response = chat(question, search_results, cfg=cfg, chat_session_id=session_id)
    return response.answer, response.chat_session_id


def ask(question: str, cfg, session_id: str | None = None) -> str | None:
    print(f"\n{'='*60}")
    print(f"Q: {question}")
    print("="*60)

    print("Searching…", end="", flush=True)
    try:
        results = do_search(question)
    except Exception as e:
        print(f"\nSearch failed: {e}")
        return session_id

    print("\nGenerating answer (may take 30–60s)…", flush=True)
    try:
        answer, new_session_id = do_chat(question, results, cfg, session_id)
    except Exception as e:
        print(f"Chat failed: {e}")
        return session_id

    print(f"\nAnswer:\n{answer}")
    return new_session_id


if __name__ == "__main__":
    print(f"Instance     : {INSTANCE}")
    print(f"Datasource   : {DATASOURCE}")
    print(f"Act-as       : {ACT_AS or '(not set)'}")
    print(f"Search token : {USER_TOKEN[:8]}…")
    print(f"Chat token   : {CHAT_TOKEN[:8]}…")

    cfg = get_config()
    session_id: str | None = None

    # --- Hardcoded smoke test ---
    session_id = ask(TEST_QUESTION, cfg, session_id)
    session_id = ask(FOLLOWUP, cfg, session_id)

    # --- Interactive loop ---
    print(f"\n{'='*60}")
    print("Interactive mode — type your question, or 'quit' to exit.")
    print("="*60)
    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break
        session_id = ask(user_input, cfg, session_id)
