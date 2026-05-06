"""Unit tests for mcp_server.py — format and merge logic, no API calls."""

import pytest

from glean_chatbot.mcp_server import _format_output, _merge_sources
from glean_chatbot.models import (
    ChatbotResult,
    CitationSource,
    SearchResult,
    SearchResultMetadata,
    SearchResultSnippet,
)


def _make_search_result(
    doc_id="doc1",
    title="Test Doc",
    url="https://example.com/doc1",
    datasource="interviewds",
    snippet="A relevant excerpt.",
) -> SearchResult:
    return SearchResult(
        title=title,
        url=url,
        snippets=[SearchResultSnippet(text=snippet)],
        metadata=SearchResultMetadata(
            document_id=doc_id,
            datasource=datasource,
        ),
    )


class TestFormatOutput:
    def test_answer_section_present(self):
        result = ChatbotResult(answer="The answer is 42.", sources=[], search_result_count=3)
        output = _format_output(result)
        assert "## Answer" in output
        assert "The answer is 42." in output

    def test_sources_section_present(self):
        result = ChatbotResult(
            answer="Some answer.",
            sources=[CitationSource(title="PTO Policy", url="https://example.com/pto", datasource="interviewds")],
            search_result_count=1,
        )
        output = _format_output(result)
        assert "## Sources" in output
        assert "PTO Policy" in output
        assert "https://example.com/pto" in output
        assert "interviewds" in output

    def test_no_sources_section_when_empty(self):
        result = ChatbotResult(answer="Answer.", sources=[], search_result_count=0)
        output = _format_output(result)
        assert "## Sources" not in output

    def test_retrieved_count_footer(self):
        result = ChatbotResult(answer="Answer.", sources=[], search_result_count=5)
        output = _format_output(result)
        assert "5 document(s)" in output

    def test_source_without_url_renders_bold(self):
        result = ChatbotResult(
            answer="Answer.",
            sources=[CitationSource(title="No URL Doc", url=None)],
            search_result_count=1,
        )
        output = _format_output(result)
        assert "**No URL Doc**" in output
        assert "]()" not in output

    def test_snippet_truncated_to_200_chars(self):
        long_snippet = "x" * 300
        result = ChatbotResult(
            answer="Answer.",
            sources=[CitationSource(title="Doc", snippet=long_snippet)],
            search_result_count=1,
        )
        output = _format_output(result)
        assert "x" * 200 in output
        assert "x" * 201 not in output


class TestMergeSources:
    def test_search_results_come_first(self):
        search = [_make_search_result(doc_id="doc1", title="From Search")]
        chat = [CitationSource(document_id="doc2", title="From Chat", url="https://example.com/2")]
        merged = _merge_sources(chat, search)
        assert merged[0].title == "From Search"
        assert merged[1].title == "From Chat"

    def test_deduplication_by_doc_id(self):
        search = [_make_search_result(doc_id="doc1")]
        chat = [CitationSource(document_id="doc1", title="Duplicate")]
        merged = _merge_sources(chat, search)
        assert len(merged) == 1

    def test_deduplication_by_url(self):
        search = [_make_search_result(doc_id="", url="https://example.com/same")]
        chat = [CitationSource(url="https://example.com/same", title="Duplicate")]
        merged = _merge_sources(chat, search)
        assert len(merged) == 1

    def test_empty_inputs(self):
        assert _merge_sources([], []) == []

    def test_snippet_pulled_from_first_search_snippet(self):
        search = [_make_search_result(snippet="Key excerpt here.")]
        merged = _merge_sources([], search)
        assert merged[0].snippet == "Key excerpt here."

    def test_chat_only_sources_included(self):
        chat = [CitationSource(document_id="chat-only", title="Chat Only", url="https://example.com/c")]
        merged = _merge_sources(chat, [])
        assert len(merged) == 1
        assert merged[0].title == "Chat Only"
