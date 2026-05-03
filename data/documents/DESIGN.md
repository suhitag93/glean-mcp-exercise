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
| **No chunking control** | Glean's indexer handles chunking internally. For documents with very long sections, the snippets returned in search results may be truncated. A custom RAG stack would allow fine-grained chunking strategies. |
| **Context window packing** | The context block is constructed from search snippets, not full document text. The Chat model may not have access to all relevant information from a document. Full-document injection would quickly exceed context limits. |
| **Search latency** | Every question incurs two round trips (Search + Chat). For latency-sensitive use cases, caching common queries or pre-computing answers for FAQ-style questions would help. |
| **Cold start** | There is a delay between calling the Indexing API and documents becoming searchable (typically 1–5 minutes). The indexer prints a reminder about this. |
| **Datasource object types** | Each sandbox datasource was registered with a different object type (`KnowledgeArticle` vs `Article`). The indexer exposes `object_type` as a configurable parameter; the Streamlit UI auto-populates it from a known config table. |
| **`chat_id` across datasource switches** | In the MCP tool, the caller manages `chat_session_id` explicitly. If a caller reuses a session ID after switching datasources, prior context from the old datasource may bleed into the answer. |
| **Auth model** | The indexing and user/chat tokens are kept separate (as required by Glean) and passed via environment variables. In production these should be fetched from a secrets manager rather than `.env` files. |
| **Global token `X-Glean-ActAs` requirement** | Global token types require every request to specify an impersonated user email via the `X-Glean-ActAs` header. The Search API accepts it as a header directly; the Chat SDK does not expose an `act_as` parameter, so it is injected by passing a pre-configured `httpx.Client` to the SDK constructor. |

### Design alternatives considered

- **External LLM (OpenAI/Anthropic) + Glean Search as retriever only.** This would allow richer prompt engineering and streaming responses, but adds a second API dependency and loses Glean's native citation framework.
- **Direct `sourceDocumentIds` chat (no search step).** Glean's Chat API can accept document IDs directly without a prior search. This would simplify the flow but requires knowing which documents are relevant upfront, which is the problem search solves.
- **Streaming responses via `create_stream()`.** The Chat API supports streaming via Server-Sent Events. However, the `support-lab` sandbox returns a complete JSON response rather than an SSE stream — `create_stream()` raises a `GleanError: Unexpected response received` because it expects chunked SSE. `create()` is used instead. Adding streaming support for a production instance that does return SSE would be a straightforward extension.
