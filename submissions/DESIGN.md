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
| Raw HTTP with `stream: false` caused indefinite `ReadTimeout` — sandbox does not support non-streaming over raw HTTP | Switched to the official `glean-api-client` SDK |
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

The MCP server exposes a single tool — `ask_glean` — rather than separate `search_glean` and `chat_glean` tools. The MCP client (Cursor, Claude Desktop) does not need to know how the pipeline works internally or how to coordinate two tools in sequence. It asks a question and gets an answer. Keeping the interface at the level of intent rather than implementation makes the tool more useful to an AI agent and more robust to future pipeline changes.

### `datasource_filter` as a Call-Time Parameter

The datasource is exposed as an optional parameter on the tool rather than fixed at the environment variable level. This means the same running MCP server instance can search across different datasources depending on what the question requires — the calling agent can specify `datasource_filter="interviewds2"` on one turn and `datasource_filter="interviewds"` on the next without restarting the server or changing configuration.

This mirrors the same principle applied in the Streamlit UI: datasource as a runtime choice, not a deploy-time constant. In a real enterprise deployment, an agent could route questions to the correct datasource based on the topic — HR questions to the HR datasource, engineering questions to the engineering datasource — using the same tool.

### `chat_session_id` and Stateless Design

The MCP tool is intentionally stateless. It does not persist `chat_session_id` between calls. The caller is responsible for threading it explicitly if multi-turn continuity is needed. This is a deliberate trade-off: a stateless tool is simpler, more predictable, and composable — any agent or client can call it without worrying about hidden session state. The Streamlit UI, by contrast, manages `chat_id` automatically because it owns the session lifecycle.

### stdio Transport

The MCP server runs over stdio rather than HTTP. This is the standard transport for IDE-integrated MCP tools (Cursor, Claude Desktop). It means no port configuration, no network exposure, and the process lifecycle is managed entirely by the MCP client — it starts the process when needed and terminates it when done.

### Citation Merging

The Chat API returns citations in its response, but they often carry minimal metadata. The search results returned earlier in the pipeline have richer metadata — title, URL, datasource, snippet. `_merge_sources()` uses search results as the primary source of truth for citations and supplements with any additional Chat API citations not already covered. The result is that every source shown to the user has a title, URL, and a snippet excerpt — regardless of what the Chat API chose to cite.

### Markdown Output

The tool returns a formatted Markdown string with `## Answer` and `## Sources` sections rather than a structured JSON object. This renders directly in Cursor's agent chat and Claude Desktop without any client-side rendering logic. The trade-off is that it is harder to parse programmatically, but for the intended use case — a human reading answers in an IDE — readability takes priority.

### Indexing is Deliberately Excluded from the MCP Tool

The MCP tool is scoped to search and retrieval only. Indexing is kept as a separate operation — via the `glean-index` CLI or the Streamlit UI — for two reasons:

- **IP allowlisting.** The Indexing API only accepts requests from pre-approved IPs. The MCP server runs as a subprocess of whatever client invokes it (Cursor, Claude Desktop), which could be on any machine or network. That environment cannot be guaranteed to be allowlisted.
- **Intent mismatch.** Indexing is a privileged setup operation — a human decision about when the corpus needs to change. The MCP tool's job is to answer questions against whatever is already in Glean, not to manage the corpus.

In production, indexing would be triggered by a pipeline — a webhook on document update, a scheduled sync job, or a CI step — not by an IDE tool. The MCP tool is correctly scoped as query-time only.

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
