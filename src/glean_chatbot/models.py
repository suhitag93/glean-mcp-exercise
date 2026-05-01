"""Shared Pydantic models for Glean API payloads and responses."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Indexing models
# ---------------------------------------------------------------------------


class DocumentPermissions(BaseModel):
    allow_anonymous_access: bool = True


class ContentSection(BaseModel):
    mime_type: str = "text/plain"
    text_content: str


class DocumentMetadata(BaseModel):
    datasource: str
    object_type: str = "Document"
    doc_id: str
    title: str
    url: str
    summary: str | None = None
    author: str | None = None
    create_time: int | None = None
    update_time: int | None = None


class GleanDocument(BaseModel):
    id: str
    datasource: str
    object_type: str = "Document"
    title: str
    view_url: str
    body: ContentSection
    summary: ContentSection | None = None
    permissions: DocumentPermissions = Field(
        default_factory=DocumentPermissions
    )
    updated_at: int | None = None
    author: dict | None = None
    custom_properties: list[dict] | None = None


class IndexDocumentsRequest(BaseModel):
    datasource: str
    documents: list[GleanDocument]


# ---------------------------------------------------------------------------
# Search models
# ---------------------------------------------------------------------------


class SearchRequestOptions(BaseModel):
    datasource_filter: list[str] | None = None
    result_tab_ids: list[str] | None = None


class SearchRequest(BaseModel):
    query: str
    page_size: int = 5
    request_options: SearchRequestOptions | None = None


class SearchResultSnippet(BaseModel):
    text: str
    ranges: list | None = None


class SearchResultMetadata(BaseModel):
    datasource: str | None = None
    object_type: str | None = None
    document_id: str | None = None
    update_time: str | None = None
    author: dict | None = None


class SearchResult(BaseModel):
    title: str | None = None
    url: str | None = None
    snippets: list[SearchResultSnippet] | None = None
    document: dict | None = None
    metadata: SearchResultMetadata | None = None


class SearchResponse(BaseModel):
    results: list[SearchResult] = Field(default_factory=list)
    total_count: int | None = None
    has_more_results: bool = False


# ---------------------------------------------------------------------------
# Chat models
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str  # "USER" or "ASSISTANT"
    content: str


class CitationSource(BaseModel):
    document_id: str | None = None
    title: str | None = None
    url: str | None = None
    datasource: str | None = None
    snippet: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[CitationSource] = Field(default_factory=list)
    chat_session_id: str | None = None


# ---------------------------------------------------------------------------
# MCP tool output
# ---------------------------------------------------------------------------


class ChatbotResult(BaseModel):
    answer: str
    sources: list[CitationSource] = Field(default_factory=list)
    search_result_count: int = 0
