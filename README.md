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
                    │  Glean Chat     │  POST /rest/api/v1/chat
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
1. **Index** (one-time or via Streamlit UI): reads 8 Markdown documents from `data/documents/`, registers the datasource, and POSTs them to the Glean Indexing API. The indexer auto-detects the correct `viewURL` prefix from Glean's error response if there is a URL regex mismatch.
2. **Search**: on each question, `search.py` queries the Glean Search API for the top-N most relevant documents, filtered to the active datasource.
3. **Chat**: `chat.py` injects retrieved snippets as grounding context and calls the Glean Chat API to generate a cited answer.
4. **MCP**: `mcp_server.py` wraps this pipeline as a single `ask_glean` tool callable from any MCP client.

---

## Prerequisites

- Python 3.11+
- A Glean sandbox instance with:
  - An **Indexing API token** (Admin → Setup → APIs & Connectors → API Tokens → type: Indexing)
  - A **User/Client API token** (Admin → Setup → APIs & Connectors → API Tokens → type: User)

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
GLEAN_INSTANCE=your-instance        # subdomain, e.g. "acme" from acme.glean.com
GLEAN_INDEXING_TOKEN=glean_idx_...  # Indexing API token
GLEAN_USER_TOKEN=glean_...          # User/Client API token
GLEAN_DATASOURCE=interviewds        # Default datasource (switchable at runtime)
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
- **Datasource selector**: switch between `interviewds`, `interviewds2`, `interviewds4`, `interviewds5`, `interviewds6` — takes effect on the next question, no reload needed
- **Index Documents button**: indexes the 8 sample documents into the currently selected datasource. The indexer auto-detects the correct URL prefix from Glean's error response if the datasource was registered with a different `urlRegex`

**Chat:**
- Ask any natural-language question
- Responses include a grounded answer and numbered source citations
- Multi-turn conversation is supported via `chat_id` threading

### Datasource Switching

Each datasource in the shared sandbox was registered by a different user with its own `urlRegex`. The app handles this automatically:

1. You select a datasource and click **Index Documents**
2. If the document `viewURL` doesn't match the datasource's registered regex, Glean returns a 400 error with the exact regex in the message
3. The indexer parses this error, extracts the correct URL prefix, and prompts you to retry
4. A yellow warning in the UI shows the corrected prefix that was detected

This means you can switch to any datasource and index successfully without knowing its URL schema upfront.

---

## Indexing via CLI

You can also index documents from the command line:

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
        "GLEAN_DATASOURCE": "interviewds"
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
        "GLEAN_DATASOURCE": "interviewds"
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
├── DESIGN.md                   # Architecture and design decisions
├── TROUBLESHOOTING.md          # Full debugging log
├── scripts/
│   ├── chat_ui.py              # Streamlit web UI
│   └── test_pipeline.py        # End-to-end pipeline test script
├── src/
│   └── glean_chatbot/
│       ├── __init__.py
│       ├── config.py           # Environment-based configuration
│       ├── models.py           # Pydantic models for API payloads
│       ├── indexer.py          # Glean Indexing API client + CLI
│       ├── search.py           # Glean Search API client
│       ├── chat.py             # Glean Chat API client
│       └── mcp_server.py       # MCP server (ask_glean tool)
└── data/
    └── documents/              # Sample internal knowledge-base articles
        ├── hr_pto_policy.md
        ├── engineering_onboarding.md
        ├── security_policy.md
        ├── incident_response_runbook.md
        ├── benefits_guide.md
        ├── api_rate_limits.md
        ├── product_roadmap_2025.md
        └── remote_work_policy.md
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GLEAN_INSTANCE` | Yes | Glean instance subdomain (e.g. `support-lab`) |
| `GLEAN_INDEXING_TOKEN` | Yes | Token for the Indexing API |
| `GLEAN_USER_TOKEN` | Yes | Token for Search and Chat APIs |
| `GLEAN_DATASOURCE` | No | Default datasource (default: `interviewds`). Overridable at runtime via the Streamlit UI or as a parameter to `ask_glean`. |
| `GLEAN_BASE_URL` | No | Override the backend URL (default: `https://{instance}-be.glean.com`) |

---

## Known Limitations & Assumptions

- **Shared sandbox datasources**: The sandbox datasources (`interviewds` through `interviewds6`) are shared across multiple users. Each was registered with a different `urlRegex`, and documents from other users are visible in search results. In production, each team would have an isolated datasource with its own ACL.
- **`allowAnonymousAccess: true`**: Documents are indexed with open permissions for prototype simplicity. Production deployments would use per-user or per-group ACLs tied to identity providers.
- **No streaming**: The Glean Chat API in this sandbox returns a complete JSON response rather than a chunked stream. The client uses `create()` (non-streaming) accordingly.
- **`chat_id` and datasource switching**: Switching datasources mid-conversation carries over the `chat_id` from the previous session. The prior chat context may reference documents from the old datasource. A production implementation would clear `chat_id` on datasource change.
- **IP allowlisting**: The Indexing API requires requests to originate from allowlisted IPs. The indexer must be run locally or from a server with a static IP that has been allowlisted. Cloud execution environments (e.g. Claude Code, GitHub Actions) will be rejected unless their egress IP is allowlisted or routed through a Cloud NAT with a static IP.
