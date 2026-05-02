"""
Glean Indexing API client.

Reads Markdown documents from data/documents/, converts them to Glean
document payloads, and POSTs them to the Indexing API.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

from .config import get_config
from .models import ContentSection, DocumentPermissions, GleanDocument

# Path to the bundled sample documents
DOCUMENTS_DIR = Path(__file__).parent.parent.parent / "data" / "documents"


def _markdown_to_glean_doc(path: Path, datasource: str) -> GleanDocument:
    """Parse a Markdown file into a GleanDocument."""
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()

    # Extract title from first H1 heading
    title = path.stem.replace("_", " ").title()
    for line in lines:
        if line.startswith("# "):
            title = line[2:].strip()
            break

    # Extract summary from the first non-empty, non-heading paragraph
    summary: str | None = None
    in_frontmatter = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("**") or not stripped:
            continue
        if "|" in stripped:  # skip table rows
            continue
        summary = stripped[:200]
        break

    # Stable document ID derived from filename (no spaces, lowercase)
    doc_id = path.stem.replace(" ", "-").lower()

    # URL must match the datasource's configured regex: https://internal\.example\.com/policies/.*
    url = f"https://internal.example.com/policies/{doc_id}"

    return GleanDocument(
        id=doc_id,
        datasource=datasource,
        object_type="KnowledgeArticle",
        title=title,
        view_url=url,
        body=ContentSection(mime_type="text/markdown", text_content=raw),
        summary=ContentSection(mime_type="text/plain", text_content=summary or title),
        permissions=DocumentPermissions(allow_anonymous_access=True),
        updated_at=int(time.time()),
    )


def build_documents(datasource: str) -> list[GleanDocument]:
    """Load all Markdown files from DOCUMENTS_DIR and return GleanDocument list."""
    docs = []
    for md_file in sorted(DOCUMENTS_DIR.glob("*.md")):
        docs.append(_markdown_to_glean_doc(md_file, datasource))
    return docs


def _index_documents(
    documents: list[GleanDocument],
    *,
    base_url: str,
    indexing_token: str,
    datasource: str,
    batch_size: int = 50,
) -> None:
    """Send documents to the Glean Indexing API in batches."""
    headers = {
        "Authorization": f"Bearer {indexing_token}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=60) as client:
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            payload = {
                "datasource": datasource,
                "documents": [_doc_to_payload(d) for d in batch],
            }
            url = f"{base_url}/api/index/v1/indexdocuments"
            response = client.post(url, headers=headers, json=payload)
            if not response.is_success:
                raise httpx.HTTPStatusError(
                    f"HTTP {response.status_code}: {response.text}",
                    request=response.request,
                    response=response,
                )
            print(
                f"  Indexed batch {i // batch_size + 1} "
                f"({len(batch)} documents) → HTTP {response.status_code}"
            )


def _doc_to_payload(doc: GleanDocument) -> dict:
    """Convert a GleanDocument to the raw JSON structure expected by the API."""
    payload: dict = {
        "id": doc.id,
        "datasource": doc.datasource,
        "objectType": doc.object_type,
        "title": doc.title,
        "viewURL": doc.view_url,
        "body": {
            "mimeType": doc.body.mime_type,
            "textContent": doc.body.text_content,
        },
        "permissions": {
            "allowAnonymousAccess": doc.permissions.allow_anonymous_access,
        },
    }
    if doc.summary:
        payload["summary"] = {
            "mimeType": doc.summary.mime_type,
            "textContent": doc.summary.text_content,
        }
    if doc.updated_at is not None:
        payload["updatedAt"] = doc.updated_at
    return payload


def register_datasource(
    *,
    base_url: str,
    indexing_token: str,
    datasource: str,
) -> None:
    """
    Ensure the custom datasource exists in Glean.

    This calls the adddatasource endpoint.  If the datasource already exists,
    Glean returns a 200 with the existing config, which is safe to ignore.
    """
    headers = {
        "Authorization": f"Bearer {indexing_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "name": datasource,
        "displayName": "Acme Corp Knowledge Base",
        "datasourceCategory": "UNCATEGORIZED",
        "urlRegex": "https://wiki\\.acme-corp\\.example\\.com/.*",
        "iconUrl": "https://wiki.acme-corp.example.com/favicon.ico",
        "objectDefinitions": [
            {
                "name": "KnowledgeArticle",
                "displayLabel": "Knowledge Article",
                "docCategory": "PUBLISHED_CONTENT",
            }
        ],
        "isUserReferencedByEmail": False,
        "trustUrlRegexForViewActivity": True,
    }
    url = f"{base_url}/api/index/v1/adddatasource"
    with httpx.Client(timeout=30) as client:
        response = client.post(url, headers=headers, json=payload)
        if response.status_code in (400, 403, 409):
            # Sandbox datasources are typically pre-created in the admin console.
            # 400/403 = no permission to create; 409 = already exists. All are safe to skip.
            print(
                f"  Datasource registration skipped (HTTP {response.status_code}) – "
                f"assuming '{datasource}' is pre-configured in the Glean admin console."
            )
            return
        response.raise_for_status()
        print(f"  Datasource '{datasource}' registered → HTTP {response.status_code}")


def main() -> None:
    """Entry-point: index all sample documents into Glean."""
    cfg = get_config()
    print(f"Glean instance : {cfg.instance}")
    print(f"Datasource     : {cfg.datasource}")
    print(f"Documents dir  : {DOCUMENTS_DIR}")
    print()

    print("Step 1/3 – Registering datasource …")
    register_datasource(
        base_url=cfg.base_url,
        indexing_token=cfg.indexing_token,
        datasource=cfg.datasource,
    )

    print("\nStep 2/3 – Loading documents from disk …")
    documents = build_documents(cfg.datasource)
    print(f"  Loaded {len(documents)} documents")
    for doc in documents:
        print(f"    • [{doc.id}] {doc.title}")

    print("\nStep 3/3 – Sending documents to Glean Indexing API …")
    _index_documents(
        documents,
        base_url=cfg.base_url,
        indexing_token=cfg.indexing_token,
        datasource=cfg.datasource,
    )

    print("\nDone. Documents have been submitted for indexing.")
    print("Note: It may take a few minutes for documents to appear in search results.")


if __name__ == "__main__":
    main()
