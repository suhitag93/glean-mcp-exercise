# Glean RAG Chatbot + MCP Tool

A RAG-based enterprise chatbot that uses the **Glean Indexing API**, **Glean Search API**, and **Glean Chat API** to answer employee questions from a curated internal knowledge base — exposed as a single MCP tool for use in Cursor, Claude Desktop, and other MCP-compatible clients, and as an interactive **Streamlit web app**.

---

## Architecture Overview

```
User Question
     │
     ├─────────────────────────────────────┐
     ▼                                     ▼
┌─────────────────────────────┐   ┌─────────────────────────────┐
│       Streamlit UI          │   │         MCP Tool            │
│    (scripts/chat_ui.py)     │   │  (glean_chatbot/mcp_server) │
└─────────────┬───────────────┘   └─────────────┬───────────────┘
              │                                 │
              └──────────────┬──────────────────┘
                             │
                    ┌────────▼────────┐
                    │  Glean Search   │  POST /rest/api/v1/search
                    │   (search.py)   │  → top-N relevant documents
                    └────────┬────────┘
                             │  retrieved docs (titles, URLs, snippets)
                    ┌────────▼────────┐
                    │  Glean Chat     │  glean.client.chat.create()
                    │   (chat.py)     │  → grounded answer + citations
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │    Response     │  answer + cited sources
                    └─────────────────┘

Separate step (run once or via UI):
┌─────────────────────────────┐
│  Glean Indexing API         │  POST /api/index/v1/indexdocuments
│  (indexer.py)               │  → 8 sample internal knowledge-base docs
└─────────────────────────────┘
```

**Data flow:**
1. **Index** (one-time or via Streamlit UI): reads 8 Markdown documents from `data/documents/`, registers the datasource, and POSTs them to the Glean Indexing API. The indexer auto-detects the correct `viewURL` prefix from Glean's 400 error response if there is a URL regex mismatch.
2. **Search**: on each question, `search.py` queries the Glean Search API for the top-N most relevant documents, filtered to the active datasource.
3. **Chat**: `chat.py` injects retrieved snippets as a numbered grounding context block and calls the Glean Chat API (via the official `glean-api-client` SDK) to generate a cited answer.
4. **MCP**: `mcp_server.py` wraps this pipeline as a single `ask_glean` tool callable from any MCP client.

---

## Prerequisites

- Python 3.10+
- A Glean sandbox instance with:
  - An **Indexing API token** (Admin → Setup → APIs & Connectors → API Tokens → type: Indexing)
  - A **User/Client API token** (Admin → Setup → APIs & Connectors → API Tokens → type: User or Global)

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/suhitag93/glean-mcp-exercise.git
cd glean-mcp-exercise
pip install -e .
```

Or with `uv`:

```bash
uv sync
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```dotenv
GLEAN_INSTANCE=your-instance          # subdomain, e.g. "acme" from acme.glean.com
GLEAN_INDEXING_TOKEN=glean_idx_...    # Indexing API token
GLEAN_USER_TOKEN=glean_...            # Search API token
GLEAN_CHAT_TOKEN=glean_...            # Chat/Client API token (falls back to GLEAN_USER_TOKEN)
GLEAN_DATASOURCE=interviewds          # Datasource to search (switchable at runtime)
GLEAN_ACT_AS=you@yourcompany.com      # Required when using a Global token type
```

---

## Running the Streamlit App

The Streamlit app is the primary interface for this prototype. It provides:
- A **chat interface** for asking questions and receiving grounded answers with citations
- A **datasource selector** in the sidebar to switch between available datasources at runtime
- A **one-click indexer** to push documents into the selected datasource directly from the UI

```bash
streamlit run scripts/chat_ui.py
```

Then open `http://localhost:8501` in your browser.

### Streamlit Features

**Sidebar:**
- **Search results to use**: slider controlling how many search results are injected as context (1–10, default 5)
- **Datasource filter**: switch datasources at runtime — conversation history clears automatically on change
- **Document URL prefix**: the base URL prepended to document slugs for indexing; auto-populated from the known datasource config table and auto-corrected on URL regex mismatch errors
- **Object type**: the Glean object type used when indexing (e.g. `KnowledgeArticle` for `interviewds`, `Article` for `interviewds2`–`interviewds6`); auto-populated from the known config table
- **Index this datasource**: indexes the 8 sample documents into the currently selected datasource. On URL regex mismatch the correct prefix is extracted from Glean's error message and shown as a warning — click again to retry with the corrected prefix
- **Show sources**: toggle source citations on/off in chat responses
- **Clear conversation**: resets chat history and `chat_id`

**Chat:**
- Ask any natural-language question
- Responses include a grounded answer with numbered source citations
- Multi-turn conversation is maintained automatically via `chat_id` threading

### Datasource Switching

Each datasource in the shared sandbox was registered with its own `urlRegex`. The app handles indexing into any datasource without knowing its URL schema upfront:

1. Select a datasource and click **Index this datasource**
2. If the document `viewURL` doesn't match the datasource's regex, Glean returns a 400 with the exact regex in the error body
3. The UI parses the error, strips regex metacharacters to derive the correct URL prefix, and shows a yellow warning
4. Click **Index this datasource** again — it retries with the corrected prefix

---

## Indexing via CLI

```bash
glean-index
```

Output:
```
Glean instance : support-lab
Datasource     : interviewds
Documents dir  : /path/to/data/documents

Step 1/3 – Registering datasource …
  Datasource 'interviewds' registered → HTTP 200

Step 2/3 – Loading documents from disk …
  Loaded 8 documents
    • [api_rate_limits] Api Rate Limits
    • [benefits_guide] Employee Benefits Guide
    ...

Step 3/3 – Sending documents to Glean Indexing API …
  Indexed batch 1 (8 documents) → HTTP 200

Done. Documents have been submitted for indexing.
Note: It may take a few minutes for documents to appear in search results.
```

---

## End-to-End Test Script

```bash
python scripts/test_pipeline.py
```

Runs two hardcoded questions (`"What is the PTO policy?"` and `"Are there multiple companies PTO policies here?"`) as a smoke test, then drops into an interactive prompt for further questions. Session ID is threaded through all turns for multi-turn continuity. Type `quit` to exit.

---

## Using the MCP Tool in Cursor

Add this to your Cursor MCP configuration (`~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "glean-rag-chatbot": {
      "command": "glean-mcp",
      "env": {
        "GLEAN_INSTANCE": "your-instance",
        "GLEAN_INDEXING_TOKEN": "glean_idx_...",
        "GLEAN_USER_TOKEN": "glean_...",
        "GLEAN_CHAT_TOKEN": "glean_...",
        "GLEAN_DATASOURCE": "interviewds",
        "GLEAN_ACT_AS": "you@yourcompany.com"
      }
    }
  }
}
```

Then in Cursor chat:

```
Use ask_glean to answer: "How many PTO days do employees get after 3 years?"
```

### Tool Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `question` | string | Yes | — | Natural-language question |
| `num_results` | int | No | 5 | Search results to use as context (1–10) |
| `datasource_filter` | string | No | env var | Restrict search to a specific datasource |
| `chat_session_id` | string | No | None | Session ID for multi-turn conversation continuity |

### Example Response

```markdown
## Answer

Based on the PTO policy, employees who have been with the company for 2–5 years
accrue **20 days of PTO per year** (1.67 days/month). [1]

## Sources

1. [Paid Time Off (PTO) Policy](https://internal.example.com/policies/hr_pto_policy)
   *(datasource: interviewds)*
   > Employees may roll over up to 10 days of unused PTO …

*Retrieved 5 document(s) from Glean search.*
```

---

## Using the MCP Tool in Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "glean-rag-chatbot": {
      "command": "glean-mcp",
      "env": {
        "GLEAN_INSTANCE": "your-instance",
        "GLEAN_INDEXING_TOKEN": "glean_idx_...",
        "GLEAN_USER_TOKEN": "glean_...",
        "GLEAN_CHAT_TOKEN": "glean_...",
        "GLEAN_DATASOURCE": "interviewds",
        "GLEAN_ACT_AS": "you@yourcompany.com"
      }
    }
  }
}
```

---

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/
```

---

## Project Structure

```
glean-mcp-exercise/
├── pyproject.toml              # Package definition and dependencies
├── .env.example                # Environment variable template
├── README.md                   # This file
├── scripts/
│   ├── chat_ui.py              # Streamlit web UI
│   └── test_pipeline.py        # End-to-end smoke test + interactive loop
├── src/
│   └── glean_chatbot/
│       ├── __init__.py
│       ├── config.py           # Environment-based configuration
│       ├── models.py           # Pydantic models for API payloads
│       ├── indexer.py          # Glean Indexing API client + CLI entry point
│       ├── search.py           # Glean Search API client
│       ├── chat.py             # Glean Chat API client (via glean-api-client SDK)
│       └── mcp_server.py       # FastMCP server exposing ask_glean tool
└── data/
    └── documents/              # Markdown files indexed into Glean
        ├── hr_pto_policy.md
        ├── engineering_onboarding.md
        ├── security_policy.md
        ├── incident_response_runbook.md
        ├── benefits_guide.md
        ├── api_rate_limits.md
        ├── product_roadmap_2025.md
        ├── remote_work_policy.md
        ├── DESIGN.md           # Architecture and design decisions
        └── TROUBLESHOOTING.md  # Full debugging log
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GLEAN_INSTANCE` | Yes | — | Glean instance subdomain (e.g. `support-lab`) |
| `GLEAN_INDEXING_TOKEN` | Yes | — | Bearer token for the Indexing API |
| `GLEAN_USER_TOKEN` | Yes | — | Bearer token for the Search API |
| `GLEAN_CHAT_TOKEN` | No | `GLEAN_USER_TOKEN` | Bearer token for the Chat API; falls back to `GLEAN_USER_TOKEN` if not set |
| `GLEAN_DATASOURCE` | No | `glean-mcp-exercise` | Default datasource for search and indexing; overridable at runtime via the Streamlit UI or as a parameter to `ask_glean` |
| `GLEAN_ACT_AS` | No | — | Email address to impersonate; required when using a Global token type (`X-Glean-ActAs` header) |
| `GLEAN_BASE_URL` | No | `https://{instance}-be.glean.com` | Override the Glean backend base URL |
| `GLEAN_DEBUG` | No | — | Set to any non-empty value to print the raw Chat API SDK response to stdout |

---

## Known Limitations & Assumptions

- **Shared sandbox datasources**: The sandbox datasources (`interviewds` through `interviewds6`) are shared across multiple users. Each was registered with a different `urlRegex`, and documents from other users are visible in search results. In production, each team would have an isolated datasource with its own ACL.
- **`allowAnonymousAccess: true`**: Documents are indexed with open permissions for prototype simplicity. Production deployments would use per-user or per-group ACLs tied to identity providers.
- **No streaming**: The Glean Chat API in this sandbox returns a complete JSON response rather than a chunked stream. The SDK's `create_stream()` raises a `GleanError` on this sandbox; `create()` is used instead.
- **`chat_id` and datasource switching**: The Streamlit UI clears `chat_id` automatically when the datasource changes. The MCP tool requires the caller to manage `chat_session_id` explicitly across turns.
- **IP allowlisting**: The Indexing API requires requests to originate from allowlisted IPs. The indexer must be run locally or from a server with a static IP that has been allowlisted. Cloud execution environments will be rejected unless their egress IP is allowlisted.
