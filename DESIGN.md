# Design Note – Glean RAG Chatbot + MCP Tool

## 1. How the Three Glean APIs Are Used

### Glean Indexing API

**Endpoint:** `POST /api/index/v1/indexdocuments`  
**Auth:** Bearer token (Indexing API token)

The Indexing API is used once (or on demand) to ingest a corpus of 8 Markdown documents that simulate a real enterprise knowledge base — HR policies, engineering runbooks, security guidelines, and product plans.

Before indexing, `adddatasource` is called to register a custom datasource named `glean-mcp-exercise`. Each document is mapped to the `GleanDocument` schema with fields: `id` (stable slug from filename), `title` (from the first H1 heading), `body` (full Markdown text), `summary` (first non-heading paragraph), `viewURL` (canonical wiki URL), and `objectType: KnowledgeArticle`.

Documents are batched (up to 50 per request) to stay within the API's payload limits. The `updatedAt` timestamp is set to the current time on each run, which allows re-indexing to update documents in-place.

### Glean Search API

**Endpoint:** `POST /rest/api/v1/search`  
**Auth:** Bearer token (User/Client API token)

On every call to the `ask_glean` MCP tool, the user's question is sent verbatim to the Search API. Glean's search engine returns the top-N documents ranked by relevance — leveraging its native semantic and keyword hybrid search over the indexed corpus.

Key request parameters used:
- `pageSize`: configured by the caller (default 5, max 10)
- `datasourceFilter`: optional — narrows results to the custom datasource

The response is parsed into `SearchResult` objects that carry the document title, URL, datasource, document ID, and the most relevant text snippets.

### Glean Chat API

**Endpoint:** `POST /rest/api/v1/chat`  
**Auth:** Bearer token (User/Client API token)

The Chat API is the answer-generation layer. The retrieved search results are formatted into a numbered context block and prepended to the user message:

```
Use ONLY the following retrieved knowledge-base articles …

[1] Paid Time Off (PTO) Policy
    URL: https://wiki.acme-corp.example.com/docs/hr_pto_policy
    Content: <snippet>

[2] Employee Benefits Guide
    …

---
Question: How many PTO days do employees get after 3 years?
```

The `sourceDocumentIds` field is also populated with the retrieved document IDs, giving Glean the opportunity to emit structured `CITATION` fragments in its response. The Chat API's response is parsed to extract the answer text and citation metadata, which are returned to the caller.

---

## 2. RAG Flow

```
question
   │
   ▼  Glean Search API
top-N search results (title, URL, snippets, doc IDs)
   │
   ▼  context injection
user message = numbered source block + "Question: …"
   │
   ▼  Glean Chat API
answer text + citation fragments
   │
   ▼  post-processing
merge Chat citations with Search metadata → ranked source list
   │
   ▼  MCP response
Markdown: ## Answer … ## Sources …
```

The key design choice is to let Glean do both the retrieval (Search API) and the generation (Chat API). This means the RAG pipeline has no external LLM dependency — Glean's Chat API already incorporates an LLM internally. The application layer is a thin orchestration layer that stitches the two APIs together.

---

## 3. Key Tradeoffs and Limitations

### What works well

- **Single vendor, consistent quality.** Because both retrieval and generation are handled by Glean, the relevance signals from the Search index directly inform the generation model. There is no embedding mismatch that can arise when using an external vector store with a different LLM.
- **Zero vector infrastructure.** A traditional RAG stack requires a vector database, an embedding model, a chunking strategy, and reconciliation with source updates. Glean's Indexing API absorbs all of that.
- **Citation provenance.** Glean's Chat API emits structured `CITATION` fragments that link each claim to a specific source document, which is surfaced in the MCP response.
- **Live corpus updates.** Re-running `glean-index` re-indexes all documents without needing to rebuild an external vector store.

### Limitations and tradeoffs

| Concern | Detail |
|---|---|
| **No chunking control** | Glean's indexer handles chunking internally. For documents with very long sections, the snippets returned in search results may be truncated. A custom RAG stack would allow fine-grained chunking strategies. |
| **Context window packing** | The context block is constructed from the search snippets, not the full document text. This means the Chat model may not have access to all relevant information from a document. The tradeoff is that full-document injection would quickly exceed the Chat API's context limits. |
| **Search latency** | Every question incurs two round trips (Search + Chat). For latency-sensitive use cases, caching common queries or pre-computing answers for FAQ-style questions would help. |
| **Cold start** | There is a delay between calling the Indexing API and documents becoming searchable (typically 1–5 minutes). The indexer prints a reminder about this. |
| **Single datasource** | The current implementation targets one datasource. Extending to multiple datasources would require merging and re-ranking results across sources, or relying on Glean's native cross-source search. |
| **No conversation memory** | Multi-turn conversation is supported via `chatSessionId`, but the MCP tool does not automatically persist the session ID between calls. Callers must pass it explicitly. A stateful session store (e.g., Redis) would be needed for fully automatic multi-turn support. |
| **Auth model** | The indexing and user tokens are kept separate (as required by Glean), but both are passed through environment variables. In a production deployment, these should be fetched from a secrets manager (e.g., AWS Secrets Manager, HashiCorp Vault) rather than `.env` files. |

### Design alternatives considered

- **External LLM (OpenAI/Anthropic) + Glean Search as retriever only.** This would allow richer prompt engineering and streaming responses, but adds a second API dependency and loses Glean's native citation framework.
- **Direct `sourceDocumentIds` chat (no search step).** Glean's Chat API can accept document IDs directly without a prior search. This would simplify the flow but requires knowing which documents are relevant upfront, which is the problem search solves.
- **Streaming responses.** The Chat API supports `stream: true`, which would improve perceived latency for long answers. The current implementation uses non-streaming for simplicity; adding streaming via server-sent events (SSE) is a straightforward extension.
