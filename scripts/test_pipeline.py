"""
Quick end-to-end smoke test for the Glean RAG chatbot.

Usage (from the repo root with the venv active):
    python scripts/test_pipeline.py

Tests Search → Chat in sequence and prints results to stdout.
"""

import json
import os
import sys
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import httpx

INSTANCE = os.environ["GLEAN_INSTANCE"]
USER_TOKEN = os.environ["GLEAN_USER_TOKEN"]
ACT_AS = os.environ.get("GLEAN_ACT_AS", "")
DATASOURCE = os.environ.get("GLEAN_DATASOURCE", "interviewds")
BASE_URL = os.environ.get("GLEAN_BASE_URL", f"https://{INSTANCE}-be.glean.com")

HEADERS = {
    "Authorization": f"Bearer {USER_TOKEN}",
    "Content-Type": "application/json",
}
if ACT_AS:
    HEADERS["X-Glean-ActAs"] = ACT_AS

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
    r = httpx.post(f"{BASE_URL}/rest/api/v1/search", headers=HEADERS, json=payload, timeout=15)
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
    print("CHAT (grounded answer)")
    print("="*60)

    # Build context from search results
    context_lines = [
        "Use ONLY the following documents to answer the question. Cite sources by [number].",
        "",
    ]
    for i, r in enumerate(results, 1):
        snippets = r.get("snippets", [])
        snippet = ""
        if snippets:
            s = snippets[0]
            snippet = s if isinstance(s, str) else s.get("text", str(s))
        context_lines.append(f"[{i}] {r.get('title', '')}\n    URL: {r.get('url', '')}\n    {snippet[:300]}")
    context = "\n\n".join(context_lines)

    payload = {
        "messages": [
            {"role": "USER", "fragments": [{"text": f"{context}\n\n---\nQuestion: {TEST_QUESTION}"}]}
        ],
        "saveChat": False,
        "stream": False,
    }

    r = httpx.post(f"{BASE_URL}/rest/api/v1/chat", headers=HEADERS, json=payload, timeout=60)
    if not r.is_success:
        print(f"Chat error: {r.text}")
        r.raise_for_status()

    data = r.json()

    # Extract answer text
    answer = ""
    for msg in data.get("messages", []):
        if msg.get("role", "").upper() in ("ASSISTANT", "GLEAN"):
            for fragment in msg.get("fragments", []):
                if isinstance(fragment, dict):
                    answer += fragment.get("text", "")
                elif isinstance(fragment, str):
                    answer += fragment

    if not answer:
        answer = data.get("answer", "(no answer returned)")

    print(f"\nAnswer:\n{answer.strip()}")
    print(f"\nRaw chat session ID: {data.get('chatSessionId', 'n/a')}")


if __name__ == "__main__":
    print(f"Instance  : {INSTANCE}")
    print(f"Datasource: {DATASOURCE}")
    print(f"Act-as    : {ACT_AS or '(not set)'}")

    results = test_search()
    if results:
        test_chat(results)
    else:
        print("\nNo search results — skipping chat test.")
        print("Check that documents are indexed and GLEAN_DATASOURCE is correct.")
