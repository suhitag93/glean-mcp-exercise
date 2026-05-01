# Glean RAG Chatbot + MCP Tool

A RAG-based enterprise chatbot that uses the **Glean Indexing API**, **Glean Search API**, and **Glean Chat API** to answer questions about a curated knowledge base — exposed as a single MCP tool for use in Cursor, Claude Desktop, and other MCP-compatible clients.

---

## Architecture Overview

```
User Question
     │
     ▼
┌─────────────────────────────┐
│         MCP Tool            │  ← ask_glean(question, ...)
│  (glean_chatbot/mcp_server) │
└─────────────┬───────────────┘
              │
     ┌────────▼────────┐
     │  Glean Search   │  POST /rest/api/v1/search
     │  API  (search.py│  → top-N relevant documents
     └────────┬────────┘
              │  retrieved docs (titles, URLs, snippets)
     ┌────────▼────────┐
     │  Glean Chat     │  POST /rest/api/v1/chat
     │  API  (chat.py) │  → grounded answer + citations
     └────────┬────────┘
              │
     ┌────────▼────────┐
     │  MCP Response   │  Markdown: answer + source list
     └─────────────────┘

Separate step (run once):
┌─────────────────────────────┐
│  Glean Indexing API         │  POST /api/index/v1/indexdocuments
│  (indexer.py)               │  → 8 sample knowledge-base docs
└─────────────────────────────┘
```

**Data flow:**
1. **Index** (one-time): `glean-index` reads 8 Markdown documents from `data/documents/`, creates the custom datasource, and POSTs them to the Glean Indexing API.
2. **Search**: On each question, `search.py` queries the Glean Search API for the top-N most relevant documents.
3. **Chat**: `chat.py` injects the retrieved snippets as grounding context and calls the Glean Chat API to generate a cited answer.
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
GLEAN_DATASOURCE=glean-mcp-exercise # Datasource name (can leave as default)
```

### 3. Index the sample documents (one-time)

```bash
glean-index
```

This registers the `glean-mcp-exercise` datasource and indexes **8 sample knowledge-base articles** covering HR policies, engineering onboarding, security, incident response, benefits, the product roadmap, remote work policy, and API rate limits.

Output:
```
Glean instance : acme
Datasource     : glean-mcp-exercise
Documents dir  : /path/to/data/documents

Step 1/3 – Registering datasource …
  Datasource 'glean-mcp-exercise' registered → HTTP 200

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

### 4. Run the MCP server

```bash
glean-mcp
```

The server starts on **stdio** (no port needed) and waits for MCP client connections.

---

## Using the MCP Tool in Cursor

Add this to your Cursor MCP configuration (`~/.cursor/mcp.json` or workspace `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "glean-rag-chatbot": {
      "command": "glean-mcp",
      "env": {
        "GLEAN_INSTANCE": "your-instance",
        "GLEAN_INDEXING_TOKEN": "glean_idx_...",
        "GLEAN_USER_TOKEN": "glean_...",
        "GLEAN_DATASOURCE": "glean-mcp-exercise"
      }
    }
  }
}
```

Then in Cursor chat, invoke the tool:

```
Use ask_glean to answer: "How many PTO days do employees get after 3 years?"
```

### Tool Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `question` | string | Yes | — | Natural-language question |
| `num_results` | int | No | 5 | Number of search results to use as context (1–10) |
| `datasource_filter` | string | No | None | Restrict search to a specific datasource |
| `chat_session_id` | string | No | None | Session ID for multi-turn conversation continuity |

### Example Response

```markdown
## Answer

Based on the PTO policy, employees who have been with Acme Corp for 2–5 years
accrue **20 days of PTO per year** (1.67 days/month). Since 3 years falls within
that range, an employee at 3 years would receive 20 days annually. [1]

## Sources

1. [Paid Time Off (PTO) Policy](https://wiki.acme-corp.example.com/docs/hr_pto_policy)
   *(datasource: glean-mcp-exercise)*
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
        "GLEAN_DATASOURCE": "glean-mcp-exercise"
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
    └── documents/              # Sample knowledge-base articles (Markdown)
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
| `GLEAN_INSTANCE` | Yes | Glean instance subdomain |
| `GLEAN_INDEXING_TOKEN` | Yes | Token for the Indexing API |
| `GLEAN_USER_TOKEN` | Yes | Token for Search and Chat APIs |
| `GLEAN_DATASOURCE` | No | Datasource name (default: `glean-mcp-exercise`) |
| `GLEAN_BASE_URL` | No | Override the backend URL (default: `https://{instance}-be.glean.com`) |
