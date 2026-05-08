# Design Note – Glean RAG Chatbot + MCP Tool

## 1. How the Three Glean APIs Are Used

### Glean Indexing API

**Action:** Ingest Markdown documents into a Glean datasource by mapping each file to the `GleanDocument` schema — `id` (filename slug), `title` (first H1), `body` (full Markdown), `viewURL`, and `objectType`.

| Challenge | Resolution |
|---|---|
| `adddatasource` returned 400/403 — sandbox datasources are pre-configured by admins; indexing token has no create permission | Skip registration gracefully on 400/403/409 and proceed directly to indexing |
| `viewURL` must match the datasource's registered `urlRegex` — placeholder URLs failed; each datasource had a different regex with no API to query it upfront | On URL mismatch, parse the correct regex from Glean's 400 error body, strip metacharacters to derive a base URL, update config in-memory, prompt retry |
| Each datasource enforces a different `objectType` (`KnowledgeArticle` vs `Article`) — only discoverable through a failed indexing attempt | Made `url_prefix` and `object_type` configurable on `build_documents()`; added `DATASOURCE_CONFIGS` table to auto-populate known values per datasource |

---

### Glean Search API

**Action:** Send the user's query verbatim to the Search API and return top-N documents ranked by Glean's hybrid semantic + keyword search, filtered to the active datasource.

| Challenge | Resolution |
|---|---|
| Global token requires `X-Glean-ActAs: <email>` on every request — missing header returned HTTP 400 | Added `GLEAN_ACT_AS` env var; injected `X-Glean-ActAs` header on all Search requests |
| Email must be a registered Glean user — personal Gmail rejected with "Invalid identity" | Used sandbox login email (`alex@glean-sandbox.com`) for `GLEAN_ACT_AS` |
| Snippets returned in three different shapes — assuming one shape caused `AttributeError` | Wrote `_extract_snippet_text()` to handle all three: plain string, `{"snippet": "str"}`, `{"snippet": {"text": "..."}}`, and `{"text": "..."}` |

---

### Glean Chat API

**Action:** Format retrieved search results as a numbered context block, send to Chat API to generate a grounded answer. Multi-turn conversation maintained via `chat_id`.

| Challenge | Resolution |
|---|---|
| `create_stream()` raised `GleanError` — sandbox returns complete JSON, not SSE | Used `create()` instead of `create_stream()` |
| SDK has no built-in `act_as` parameter — no direct way to inject `X-Glean-ActAs` | Passed a pre-configured `httpx.Client` with the header to the SDK constructor |
| `messageType` is a Python enum — `str(MessageType.CONTENT)` evaluates to `"MessageType.CONTENT"` not `"CONTENT"`, causing parser to always miss the answer | Parsed via `getattr(msg_type, "value", str(msg_type)).upper()` to extract the raw string |
| SDK uses `chat_id` not `chat_session_id` — caused `TypeError` on multi-turn calls | Fixed parameter name to `chat_id` in `chat.py` |

---

## 2. RAG Flow

```
question
   │
   ▼  Glean Search API  (POST /rest/api/v1/search)
top-N search results (title, URL, snippets, doc IDs)
   │
   ▼  context injection
user message = numbered source block + "Question: …"
   │
   ▼  Glean Chat API  (glean.client.chat.create())
answer text from messageType == "CONTENT" fragments
   │
   ▼  post-processing
merge Chat answer with Search metadata → ranked source list
   │
   ▼  response
Streamlit: answer + sources expander
MCP: Markdown "## Answer … ## Sources …"
```

The key design choice is to let Glean handle both retrieval (Search API) and generation (Chat API). The application layer is thin orchestration — it stitches the two APIs together and formats the context block. There is no external LLM dependency and no vector database to manage.

---

## 3. MCP Tool Design

### Single Tool, Full Pipeline

`ask_glean` exposes the full Search → Chat pipeline as one tool rather than separate `search_glean` and `chat_glean` tools. The calling agent asks a question and gets an answer — it does not need to know how the pipeline works or coordinate two tools in sequence. This keeps the interface at the level of intent, making it more useful to an AI agent and more resilient to future pipeline changes.

### `datasource_filter` as a Call-Time Parameter

Datasource is an optional parameter rather than a fixed env var, so the same running server can search across different datasources without restarting. The calling agent can pass `datasource_filter="interviewds2"` on one turn and `datasource_filter="interviewds"` on the next, defaulting to the `GLEAN_DATASOURCE` env var when omitted. In production, an agent could route HR questions to one datasource and engineering questions to another using the same tool.

### `chat_session_id` and Stateless Design

The MCP tool is intentionally stateless — it does not persist `chat_session_id` between calls. The caller threads it explicitly when multi-turn continuity is needed, keeping the tool simple, predictable, and composable across any client. The Streamlit UI manages `chat_id` automatically because it owns the session lifecycle; the MCP tool does not.

### stdio Transport

The server runs over stdio rather than HTTP, which is the standard transport for IDE-integrated MCP tools like Cursor and Claude Desktop. This means no port configuration, no network exposure, and the process lifecycle is managed entirely by the MCP client. It starts on demand and terminates when the client exits.

### Citation Merging

The Chat API returns citations with minimal metadata; search results carry richer data — title, URL, datasource, snippet. `_merge_sources()` uses search results as the primary source of truth and supplements with any Chat API citations not already covered. Every source shown to the user has a title, URL, and snippet regardless of what the Chat API chose to cite.

### Markdown Output

The tool returns a formatted Markdown string with `## Answer` and `## Sources` sections rather than structured JSON. This renders directly in Cursor and Claude Desktop without any client-side parsing logic. Readability in an IDE takes priority over programmatic parseability for this use case.

### Indexing Excluded from MCP Tool

Indexing is kept separate — via `glean-index` CLI or the Streamlit UI — because the Indexing API only accepts requests from allowlisted IPs, and the MCP server runs as a subprocess of whatever client invokes it, on any machine or network. Indexing is also a privileged setup operation — a human decision about when the corpus changes — not a query-time concern. In production it would be triggered by a webhook, scheduled sync, or CI step.

---

## 4. Development Approach and Product Decisions

**CLI pipeline as triage layer.** `scripts/test_pipeline.py` was the primary tool for isolating whether errors came from the code, the API, or the UI. A specific example: the Streamlit UI showed an error for `interviewds2` suggesting the datasource required admin privileges. Running the same question through `test_pipeline.py` returned results immediately — proving the datasource was accessible. The real issue was that `interviewds2` uses object type `Article` not `KnowledgeArticle`, which was hardcoded. That finding drove making `object_type` a configurable parameter.

**Datasource flexibility as a product decision.** The brief called for a single datasource. Rather than hardcoding `interviewds`, datasource was treated as a runtime parameter from the start — configurable via env var, overridable in the Streamlit UI, and passable to the MCP tool. This required solving problems a hardcoded approach would have hidden: each datasource has its own `urlRegex` and `objectType`, discoverable only through failed indexing attempts. The result is a UI where users can switch datasources, index into any of them, and query across them without touching code.

**Unit tests as pre-flight check.** 38 tests across `test_search.py`, `test_mcp_server.py`, and `test_indexer.py` cover all pure logic without network calls or credentials. The intended workflow before any demo: `pytest tests/` first to verify local logic, then start the app to verify live integration. A failure in `pytest` points to broken code; a failure in the app points to an API or environment issue. Writing the tests also surfaced a real bug — `_extract_snippet_text()` silently returned empty string for snippets shaped as `{"text": "..."}`, fixed with a one-line guard change.

---

## 5. Key Tradeoffs and Limitations

### What works well

- **Live corpus updates.** Setting `updatedAt` to the current time on every indexing run means documents are updated in-place rather than duplicated. Re-running `glean-index` or clicking **Index this datasource** in the UI is sufficient to reflect any document changes.
- **Multi-turn conversation.** The Glean Chat API maintains session context via `chat_id`. Rather than exposing this as a manual concern, the Streamlit UI and test script thread it automatically across turns — the caller only needs to manage it explicitly when using the MCP tool.
- **Runtime datasource switching.** Datasource is treated as a runtime parameter rather than a deploy-time constant. The Streamlit UI lets users switch datasources mid-session; conversation history clears automatically on switch to avoid context bleed from the previous datasource.
- **URL regex auto-detection.** Rather than requiring manual configuration of per-datasource URL patterns, the indexer extracts the correct pattern directly from Glean's 400 error response and retries — making the indexer work against any pre-configured datasource without prior knowledge of its URL schema.

### Limitations and tradeoffs

| Concern | Detail |
|---|---|
| **Indexing requires an allowlisted IP** | The Indexing API rejects requests from non-allowlisted IPs with HTTP 403. This means `glean-index` and the Streamlit indexer button must be run from a local machine or a server with a static IP that has been allowlisted — cloud execution environments won't work out of the box. |
| **Datasource creation requires admin access** | The indexing token cannot create or modify datasources. `adddatasource` returns 400/403 in the sandbox because datasources are pre-configured by a Glean admin. The code skips registration gracefully and proceeds to indexing, but this means the indexer only works against datasources that already exist. |
| **Datasource configuration is opaque** | Each datasource enforces its own `urlRegex` and `objectType`, but these aren't exposed via a public API. The only way to discover them is to attempt indexing and read the error message. The URL regex auto-detection and configurable object type fields exist specifically to work around this. |
| **Non-streaming Chat API on this sandbox** | The `support-lab` sandbox returns a complete JSON response from the Chat API rather than a chunked SSE stream. `create_stream()` raises a `GleanError` because it expects SSE. `create()` is used instead, which requires parsing the response to find the `messageType == "CONTENT"` message — including working around a Python enum comparison pitfall where `str(MessageType.CONTENT)` evaluates to `"MessageType.CONTENT"`, not `"CONTENT"`. |
| **Global token requires `X-Glean-ActAs` on every request** | The Client API token issued for this sandbox is of type Global, meaning every request must specify a user identity via `X-Glean-ActAs`. The Search API accepts this as a plain header; the Chat SDK has no built-in parameter for it, requiring injection via a custom `httpx.Client` passed to the SDK constructor. |
| **Separate tokens for Search and Chat** | Glean issues separate tokens for the Indexing API, Search API, and Chat/Client API with different scopes. All three must be managed and kept in sync. In production these should come from a secrets manager rather than `.env` files. |
| **`chat_id` is not managed automatically in the MCP tool** | The Streamlit UI and test script thread `chat_id` automatically across turns. The MCP tool does not — the caller must pass `chat_session_id` explicitly on each request. Reusing a session ID after switching datasources will bleed context from the previous datasource into subsequent answers. |
| **Cold start after indexing** | There is a delay of 1–5 minutes between calling the Indexing API and documents becoming searchable. This is a Glean platform behavior with no client-side workaround. |
| **No re-ranking** | Search results are passed to the Chat API in the order Glean returns them. There is no re-ranking step. In a custom RAG stack you would typically apply a re-ranker (e.g. a cross-encoder model) to re-score retrieved documents by relevance to the query before injecting them into the context. The trade-off here is trusting Glean's internal ranking — which combines semantic, keyword, and behavioral signals tuned for enterprise content — rather than adding a second ranking layer on top. Adding a re-ranker would increase latency and infrastructure complexity; the assumption is that Glean's ranking is accurate enough that re-ranking yields marginal gain for this use case. |
| **Markdown-only document ingestion** | The indexer reads only `.md` files from `data/documents/`. The Glean Indexing API itself is format-agnostic — it accepts any text content with a `mimeType`. The constraint is on the client side. PDFs were evaluated as an extension: text-based PDFs can be parsed with `pypdf`, but image-based or scanned PDFs require OCR (`pytesseract` + Tesseract system dependency), which adds significant setup overhead. For this prototype, Markdown is sufficient — documents exported from Google Docs, Notion, or Confluence can be saved as `.md` without loss of indexable content. |

### Design alternatives considered

- **Direct `sourceDocumentIds` chat (no search step).** Glean's Chat API can accept document IDs directly without a prior search. This would simplify the flow but requires knowing which documents are relevant upfront — which is exactly the problem the Search API solves.
- **Streaming responses via `create_stream()`.** Streaming would improve perceived latency for long answers. It was attempted first but `create_stream()` raises a `GleanError` on this sandbox because the server returns complete JSON rather than SSE. `create()` is the correct choice for this environment; switching to streaming on a production instance that supports SSE would be straightforward.
