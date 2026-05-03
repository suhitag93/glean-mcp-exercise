# Design Note – Glean RAG Chatbot + MCP Tool

## 1. How the Three Glean APIs Are Used

### Glean Indexing API

**Endpoint:** `POST /api/index/v1/indexdocuments`  
**Auth:** Bearer token (Indexing API token)

The Indexing API is used once (or on demand via the Streamlit UI) to ingest a corpus of 8 Markdown documents that simulate a real enterprise knowledge base — HR policies, engineering runbooks, security guidelines, and product plans.

Before indexing, `adddatasource` is called to register the datasource. In the sandbox this call returns 400/403 (datasources are pre-configured by admins), so the error is caught and skipped gracefully — indexing proceeds directly. Each document is mapped to the `GleanDocument` schema with fields: `id` (stable slug from filename), `title` (from the first H1 heading), `body` (full Markdown text), `summary` (first non-heading paragraph), `viewURL` (canonical URL matching the datasource's registered regex), and `objectType` (configurable; `KnowledgeArticle` for `interviewds`, `Article` for `interviewds2`–`interviewds6`).

Documents are batched (up to 50 per request) to stay within the API's payload limits. The `updatedAt` timestamp is set to the current time on each run, which allows re-indexing to update documents in-place.

**URL regex auto-detection**: Each datasource is registered with a `urlRegex` that all document `viewURL`s must match. Rather than hardcoding URLs per datasource, the indexer lets the first failed request reveal the correct regex: Glean's 400 error body contains the exact pattern (e.g. `https://internal\.example\.com/policies/.*`). The Streamlit UI parses this, strips regex metacharacters to derive a base URL prefix, updates the in-memory config, and prompts the user to retry — without requiring any manual configuration lookup.

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

## 3. Key Tradeoffs and Limitations

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

### Design alternatives considered

- **Direct `sourceDocumentIds` chat (no search step).** Glean's Chat API can accept document IDs directly without a prior search. This would simplify the flow but requires knowing which documents are relevant upfront — which is exactly the problem the Search API solves.
- **Streaming responses via `create_stream()`.** Streaming would improve perceived latency for long answers. It was attempted first but `create_stream()` raises a `GleanError` on this sandbox because the server returns complete JSON rather than SSE. `create()` is the correct choice for this environment; switching to streaming on a production instance that supports SSE would be straightforward.
