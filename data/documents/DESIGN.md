# Design Note – Glean RAG Chatbot + MCP Tool

## 1. How the Three Glean APIs Are Used

### Glean Indexing API

**Endpoint:** `POST /api/index/v1/indexdocuments`  
**Auth:** Bearer token (Indexing API token)

The Indexing API is used once (or on demand via the Streamlit UI) to ingest a corpus of 8 Markdown documents that simulate a real enterprise knowledge base — HR policies, engineering runbooks, security guidelines, and product plans.

Before indexing, `adddatasource` is called to register the datasource. In the sandbox this call returns 400/403 (datasources are pre-configured by admins), so the error is caught and skipped gracefully — indexing proceeds directly. Each document is mapped to the `GleanDocument` schema with fields: `id` (stable slug from filename), `title` (from the first H1 heading), `body` (full Markdown text), `summary` (first non-heading paragraph), `viewURL` (canonical URL matching the datasource's registered regex), and `objectType` (configurable; `KnowledgeArticle` for `interviewds`, `Article` for `interviewds2`–`interviewds6`).

Documents are batched (up to 50 per request) to stay within the API's payload limits. The `updatedAt` timestamp is set to the current time on each run, which allows re-indexing to update documents in-place.

**The viewURL problem**: In a production deployment, every document already has a canonical URL — a Confluence page, a Notion document, an internal wiki entry. The `viewURL` field is simply that URL. In this prototype, the documents are local Markdown files with no hosting, so a URL must be fabricated.

The first attempt used a placeholder domain (`https://wiki.acme-corp.example.com/docs/{doc_id}`). This immediately failed with HTTP 400: Glean enforces a `urlRegex` per datasource, and every document's `viewURL` must match it. The datasource had been registered by a Glean admin with a specific URL pattern — one our fabricated URLs did not match.

The initial fix was straightforward: read the regex from the error message and update the URL template to match it. But when the scope expanded to support multiple datasources, a new problem emerged: each datasource in the sandbox was registered by a different user with a different `urlRegex`. There is no API to query what a datasource's regex is — the only way to discover it is to attempt indexing and read the 400 error body.

This led to the current design: the `viewURL` prefix is a configurable parameter (`url_prefix`) passed into `build_documents()`. The Streamlit UI exposes it as an editable field and auto-populates it from a known config table for recognized datasources. When indexing fails with a URL mismatch, the UI parses the regex from the error body using `re.search(r"URL Regex pattern (.+?) for the datasource", msg)`, strips regex metacharacters to produce a usable base URL, updates the in-memory config, and prompts the user to retry. The correct URL namespace is discovered from the API itself rather than requiring prior knowledge of each datasource's configuration.

### Glean Search API

**Endpoint:** `POST /rest/api/v1/search`  
**Auth:** Bearer token (`GLEAN_USER_TOKEN`); Global tokens also require `X-Glean-ActAs: <email>` header

On every call to `ask_glean` or a Streamlit chat message, the user's question is sent verbatim to the Search API with retry logic (3 attempts, exponential backoff via `tenacity`). Glean's search engine returns the top-N documents ranked by relevance — leveraging its native semantic and keyword hybrid search over the indexed corpus.

Key request parameters used:
- `pageSize`: configured by the caller (default 5, max 10)
- `datasourceFilter`: optional — narrows results to the active datasource

The response is parsed into `SearchResult` objects that carry the document title, URL, datasource, document ID, and the most relevant text snippets. Snippet parsing handles all three shapes observed in the API response: plain string, `{"snippet": "str"}`, and `{"snippet": {"text": "..."}}`.

### Glean Chat API

**SDK:** `glean-api-client` (`glean.api_client.Glean`) — `glean.client.chat.create()`  
**Auth:** Bearer token (`GLEAN_CHAT_TOKEN`, falls back to `GLEAN_USER_TOKEN`); Global tokens require `X-Glean-ActAs` injected via a custom `httpx.Client` passed to the SDK constructor

The Chat API is the answer-generation layer. The retrieved search results are formatted into a numbered context block and prepended to the user message:

```
Use ONLY the following retrieved knowledge-base articles …

[1] Paid Time Off (PTO) Policy
    URL: https://internal.example.com/policies/hr_pto_policy
    Content: <snippet>

[2] Employee Benefits Guide
    …

---
Question: How many PTO days do employees get after 3 years?
```

The SDK response is parsed to find the message where `messageType == "CONTENT"` (a `MessageType` enum; compared via `.value` to avoid the `"MessageType.CONTENT" != "CONTENT"` pitfall). The text fragments from that message are concatenated into the final answer.

Multi-turn conversation is supported by passing `chat_id` to the SDK on subsequent calls. The Streamlit UI and test script thread this automatically; the MCP tool requires the caller to pass `chat_session_id` explicitly.

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

---

## 4. Development Approach and Product Decisions

### CLI Pipeline as Triage Layer

Throughout development, `scripts/test_pipeline.py` served as the primary triage tool for isolating whether errors originated in the code, the API, or the UI layer. When the Streamlit UI surfaced an error it was not always clear whether the problem was a UI bug, a bad API call, or a misconfiguration — and UI errors often obscured the real cause.

A specific example: selecting `interviewds2` in the Streamlit UI showed an error suggesting the datasource was not indexed and required admin privileges. Running the same question through `test_pipeline.py` with `GLEAN_DATASOURCE=interviewds2` returned results immediately — proving the datasource was indexed and fully accessible. The UI error was a red herring. The CLI triage revealed the real issue: `interviewds2` uses object type `Article` rather than `KnowledgeArticle`, which the indexer had hardcoded. That finding drove the decision to make `object_type` a configurable parameter and add it as an editable field in the sidebar.

This pattern — reproduce in the CLI pipeline first, fix the root cause, then verify in the UI — was applied consistently throughout development and is why `test_pipeline.py` exists as a standalone script rather than being embedded in the UI code.

### Datasource Flexibility as a Product Decision

The brief called for a single datasource. Rather than hardcoding `interviewds` as a constant, the datasource was treated as a runtime parameter from the start — configurable via environment variable, overridable in the Streamlit UI, and passable as a parameter to the MCP tool.

This was a deliberate product decision: in a real enterprise deployment, different teams would use different datasources. Locking the tool to a single datasource at the code level would make it a demo, not a tool. Treating it as a runtime parameter required solving problems that a hardcoded approach would have hidden — specifically, that each datasource in the sandbox has its own `urlRegex` and `objectType`. Solving those led to the URL regex auto-detection from error responses and the configurable object type field.

The result is a UI where a user can switch datasources, index documents into any of them, and query across them — without touching code or restarting the app.

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

### Design alternatives considered

- **Direct `sourceDocumentIds` chat (no search step).** Glean's Chat API can accept document IDs directly without a prior search. This would simplify the flow but requires knowing which documents are relevant upfront — which is exactly the problem the Search API solves.
- **Streaming responses via `create_stream()`.** Streaming would improve perceived latency for long answers. It was attempted first but `create_stream()` raises a `GleanError` on this sandbox because the server returns complete JSON rather than SSE. `create()` is the correct choice for this environment; switching to streaming on a production instance that supports SSE would be straightforward.
