# Troubleshooting Log – End-to-End RAG Pipeline

A chronological record of every issue encountered and resolved while getting the Glean RAG chatbot working from scratch.

---

## 1. Project Setup
**What:** Built the full RAG chatbot from scratch — `indexer.py`, `search.py`, `chat.py`, `mcp_server.py`, 8 sample knowledge-base documents, README, DESIGN.md. Exposed the pipeline as a single `ask_glean` MCP tool over stdio.

---

## 2. Indexing API – Host Not in Allowlist
**Error:** `HTTP 403 – Host not in allowlist`
**Cause:** The Glean indexing token was restricted to specific IPs; the cloud environment's IP wasn't whitelisted.
**Fix:** Ran `glean-index` locally from the user's MacBook instead of the cloud environment.

---

## 3. Python Version Incompatible
**Error:** `Package 'glean-rag-chatbot' requires a different Python: 3.9.6 not in '>=3.11'`
**Cause:** Local machine had Python 3.9.6; the `mcp` package requires 3.10+.
**Fix:** `brew install python@3.12`. Updated `pyproject.toml` to `requires-python = ">=3.10"`. Added `from __future__ import annotations` to `config.py` for 3.10 compatibility.

---

## 4. pip Externally Managed Environment
**Error:** `error: externally-managed-environment`
**Cause:** Homebrew Python 3.12 blocks system-wide `pip install` per PEP 668.
**Fix:** Created a virtual environment: `python3.12 -m venv .venv && source .venv/bin/activate`

---

## 5. Datasource Registration Rejected (400 / 403)
**Error:** `HTTP 400 Bad Request` on `POST /api/index/v1/adddatasource`
**Cause:** The `interviewds` datasource is pre-configured in the Glean sandbox admin console. The indexing token does not have permission to create or modify datasources.
**Fix:** Updated `register_datasource()` to skip gracefully on HTTP 400/403/409 and proceed directly to indexing.

---

## 6. Document URL Regex Mismatch
**Error:** `HTTP 400 – View URL https://wiki.acme-corp.example.com/docs/api_rate_limits does not match the URL Regex pattern https://internal\.example\.com/policies/.*`
**Cause:** The pre-configured datasource enforces a URL pattern. Our fabricated document URLs used a different domain.
**Fix:** Updated the document URL template in `indexer.py` to `https://internal.example.com/policies/{doc_id}`.

---

## ✅ Documents Indexed Successfully

---

## 7. Search API – Missing X-Glean-ActAs Header
**Error:** `HTTP 400 – Required header missing: X-Glean-ActAs`
**Cause:** The Client API token is of type **Global**, which requires every request to specify the user identity it is acting on behalf of.
**Fix:** Added `GLEAN_ACT_AS` environment variable. Injected `X-Glean-ActAs: <email>` header into all Search and Chat API requests.

---

## 8. Invalid Identity
**Error:** `HTTP 400 – Invalid identity`
**Cause:** `suhita.g93@gmail.com` is not a registered user in the `support-lab` Glean instance.
**Fix:** Used the sandbox login email (`alex@glean-sandbox.com`) for `GLEAN_ACT_AS`.

---

## 9. Snippet Parsing Error
**Error:** `AttributeError: 'str' object has no attribute 'get'`
**Cause:** Assumed snippets were returned as `{"snippet": {"text": "..."}}`. The actual Glean response shape is `{"snippet": "text"}` — a plain string value, not a nested dict.
**Fix:** Extracted a `_extract_snippet_text()` helper that defensively handles all three observed shapes: plain string, `{"snippet": "str"}`, `{"snippet": {"text": "..."}}`, and `{"text": "..."}`.

---

## 10. Chat API – ReadTimeout (stream: false)
**Error:** `httpx.ReadTimeout: The read operation timed out`
**Cause:** The Glean Chat API on the `support-lab` sandbox does not support non-streaming responses. Setting `stream: false` causes the server to hang indefinitely.
**Fix:** Switched to the official Glean Python SDK (`glean-api-client`) and used `glean.client.chat.create()`.

---

## 11. Separate Search vs Chat Tokens
**Observation:** The Search API token and Client API token are separate credentials with different scopes.
**Resolution:** Added a dedicated `GLEAN_CHAT_TOKEN` environment variable. The Client token (scope: Chat + Search, type: Global) is used for Chat; the Search-specific token is used for Search API calls.

---

## 12. SDK – Unexpected act_as Parameter
**Error:** `TypeError: Glean.__init__() got an unexpected keyword argument 'act_as'`
**Cause:** The Glean Python SDK does not expose an `act_as` constructor parameter.
**Fix:** Injected the `X-Glean-ActAs` header by passing a pre-configured `httpx.Client` to the SDK constructor: `Glean(client=httpx.Client(headers={"X-Glean-ActAs": email}, timeout=httpx.Timeout(120.0)))`.

---

## 13. SDK – create_stream() GleanError
**Error:** `GleanError: Unexpected response received` on `glean.client.chat.create_stream()`
**Cause:** The sandbox returns a **complete JSON response**, not a chunked stream. `create_stream()` expects Server-Sent Events and rejects the non-streaming response.
**Fix:** Switched from `create_stream()` to `create()` and added a dedicated `_parse_response()` function.

---

## 14. MessageType Enum Comparison
**Error:** Parser returned `"I could not generate an answer from the available sources."` despite a successful API call.
**Cause:** `message_type` is a Python enum (`MessageType.CONTENT`). Comparing `str(msg_type).upper() == "CONTENT"` evaluated to `"MESSAGETYPE.CONTENT" == "CONTENT"` — always false.
**Fix:** Used `getattr(msg_type, "value", str(msg_type)).upper()` to extract the raw string value from the enum before comparing.

---

## ✅ Full Pipeline Working

Search returns 5 relevant documents → Chat generates a grounded, cited answer from the `messageType == "CONTENT"` message fragments → Streamlit UI and MCP tool both functional.

---

## 15. Multi-Turn – chat_session_id Unexpected Keyword Argument
**Error:** `TypeError: chat() got an unexpected keyword argument 'chat_session_id'`
**Cause:** The `glean-api-client` SDK uses `chat_id` as the parameter name, not `chat_session_id`.
**Fix:** Changed `kwargs["chat_session_id"]` to `kwargs["chat_id"]` in `chat.py`.

---

## 16. Streamlit UI – Interactive Chat Interface
**What:** Built `scripts/chat_ui.py` — a Streamlit web app wrapping the RAG pipeline with a sidebar (num_results slider, datasource filter, sources toggle, clear button) and multi-turn chat history backed by `st.session_state`.

---

## 17. Streamlit UI – Datasource Switching Clears Conversation
**What:** Switching datasources mid-conversation would carry over `chat_id` context from the previous datasource.
**Fix:** Added `active_datasource` to session state. On each render, if the datasource field changed, `messages` and `chat_session_id` are cleared automatically before the next question is processed.

---

## 18. Streamlit UI – One-Click Indexer
**What:** Added an **"Index this datasource"** button to the sidebar that runs `register_datasource()` + `build_documents()` + `_index_documents()` inline with progress feedback — so documents can be indexed into any datasource without leaving the UI.

---

## 19. Indexing – URL Regex Mismatch Across Datasources
**Error:** `HTTP 400 – View URL … does not match the URL Regex pattern … for the datasource`
**Cause:** Each sandbox datasource was registered by a different user with a different `urlRegex`. Hardcoding `https://internal.example.com/policies/` only works for `interviewds`.
**Fix 1:** Made the document URL prefix configurable — added `url_prefix` param to `build_documents()` and a **Document URL prefix** text input to the Streamlit sidebar.
**Fix 2:** Added auto-detection: when a URL mismatch 400 is returned, the error body contains the exact regex. The UI parses it with `re.search(r"URL Regex pattern (.+?) for the datasource", msg)`, strips metacharacters (`re.sub(r"/?\.?\*$", "")` then `.replace("\\.", ".")`), updates the in-memory config, and shows a yellow warning prompting the user to retry.

---

## 20. Indexing – Object Type Mismatch Across Datasources
**Error:** `HTTP 400 – Object definitions not found for object types: KnowledgeArticle`
**Cause:** `interviewds` uses object type `KnowledgeArticle`; `interviewds2`–`interviewds6` use `Article`. The indexer had `KnowledgeArticle` hardcoded.
**Fix:** Made the object type configurable — added `object_type` param to `build_documents()` and an **Object type** text input to the Streamlit sidebar. Added a `DATASOURCE_CONFIGS` lookup table in the UI that auto-populates both the URL prefix and object type for known datasources.

---

## 21. Test Script – Hardcoded Follow-Up and Interactive Loop
**What:** Extended `scripts/test_pipeline.py` to:
- Run a hardcoded follow-up question (`"Are there multiple companies PTO policies here?"`) immediately after the initial smoke test, threading the `chat_id` for multi-turn continuity
- Drop into an interactive prompt loop so any question can be asked without restarting the script; type `quit` to exit

---

## ✅ Full Feature Set Complete

End-to-end RAG pipeline → Streamlit UI with runtime datasource switching and one-click indexer → MCP tool → multi-turn conversation → auto URL prefix detection → configurable object types per datasource.
