"""
Quick end-to-end smoke test for the Glean RAG chatbot.

Usage (from the repo root with the venv active):
    python scripts/test_pipeline.py

Tests Search → Chat in sequence and prints results to stdout.
"""

import os
import sys
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import httpx

from glean_chatbot.chat import chat
from glean_chatbot.config import get_config
from glean_chatbot.search import _extract_snippet_text

INSTANCE = os.environ["GLEAN_INSTANCE"]
USER_TOKEN = os.environ["GLEAN_USER_TOKEN"]
CHAT_TOKEN = os.environ.get("GLEAN_CHAT_TOKEN") or USER_TOKEN
ACT_AS = os.environ.get("GLEAN_ACT_AS", "")
DATASOURCE = os.environ.get("GLEAN_DATASOURCE", "interviewds")
BASE_URL = os.environ.get("GLEAN_BASE_URL", f"https://{INSTANCE}-be.glean.com")

SEARCH_HEADERS = {
    "Authorization": f"Bearer {USER_TOKEN}",
    "Content-Type": "application/json",
}
if ACT_AS:
    SEARCH_HEADERS["X-Glean-ActAs"] = ACT_AS

TEST_QUESTION = "What is the PTO policy?"


def test_search() -> list[dict]:
    print(f"\n{'='*60}")
    print(f"SEARCH: {TEST_QUESTION!r}")
    print("="*60)

    payload = {
        "query": TEST_QUESTION,
        "pageSize": 5,
        "requestOptions": {"datasourceFilter": DATASOURCE},
    }
    r = httpx.post(f"{BASE_URL}/rest/api/v1/search", headers=SEARCH_HEADERS, json=payload, timeout=15)
    r.raise_for_status()
    data = r.json()

    results = data.get("results", [])
    print(f"Results: {len(results)}")
    for i, result in enumerate(results, 1):
        print(f"\n  [{i}] {result.get('title', '(no title)')}")
        print(f"      URL: {result.get('url', '')}")
        snippets = result.get("snippets", [])
        if snippets:
            s = snippets[0]
            text = s if isinstance(s, str) else s.get("text", str(s))
            print(f"      Snippet: {text[:120]}…")
    return results


def test_chat(results: list[dict]) -> None:
    print(f"\n{'='*60}")
    print("CHAT (grounded answer via Glean SDK)")
    print("="*60)

    from glean_chatbot.models import SearchResult, SearchResultSnippet, SearchResultMetadata
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

    print("Streaming response (may take 30–60s)...")
    cfg = get_config()
    response = chat(TEST_QUESTION, search_results, cfg=cfg)

    print(f"\nAnswer:\n{response.answer}")
    if response.sources:
        print(f"\nSources: {[s.title for s in response.sources]}")


if __name__ == "__main__":
    print(f"Instance     : {INSTANCE}")
    print(f"Datasource   : {DATASOURCE}")
    print(f"Act-as       : {ACT_AS or '(not set)'}")
    print(f"Search token : {USER_TOKEN[:8]}…")
    print(f"Chat token   : {CHAT_TOKEN[:8]}…")

    results = test_search()
    if results:
        test_chat(results)
    else:
        print("\nNo search results — skipping chat test.")
        print("Check that documents are indexed and GLEAN_DATASOURCE is correct.")
