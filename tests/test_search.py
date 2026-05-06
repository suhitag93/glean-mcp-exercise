"""Unit tests for search.py — no live API calls."""

import pytest

from glean_chatbot.search import (
    _extract_snippet_text,
    _parse_search_response,
    format_results_for_context,
)
from glean_chatbot.models import SearchResult, SearchResultSnippet


class TestExtractSnippetText:
    def test_plain_string(self):
        assert _extract_snippet_text("hello world") == "hello world"

    def test_dict_with_snippet_string(self):
        assert _extract_snippet_text({"snippet": "hello"}) == "hello"

    def test_dict_with_snippet_nested(self):
        assert _extract_snippet_text({"snippet": {"text": "nested"}}) == "nested"

    def test_dict_with_text_key(self):
        assert _extract_snippet_text({"text": "direct"}) == "direct"

    def test_empty_dict(self):
        assert _extract_snippet_text({}) == ""

    def test_non_dict_non_string(self):
        assert _extract_snippet_text(42) == "42"

    def test_empty_string(self):
        assert _extract_snippet_text("") == ""


class TestParseSearchResponse:
    def test_empty_results(self):
        assert _parse_search_response({}) == []
        assert _parse_search_response({"results": []}) == []

    def test_basic_result(self):
        data = {
            "results": [
                {
                    "title": "PTO Policy",
                    "url": "https://example.com/pto",
                    "snippets": [{"snippet": "Employees get 20 days PTO."}],
                    "document": {
                        "id": "hr_pto_policy",
                        "datasource": "interviewds",
                        "objectType": "KnowledgeArticle",
                        "metadata": {},
                    },
                }
            ]
        }
        results = _parse_search_response(data)
        assert len(results) == 1
        assert results[0].title == "PTO Policy"
        assert results[0].url == "https://example.com/pto"
        assert results[0].snippets[0].text == "Employees get 20 days PTO."
        assert results[0].metadata.datasource == "interviewds"

    def test_snippet_shapes(self):
        """All three snippet shapes Glean returns should parse to text."""
        data = {
            "results": [
                {
                    "title": "Doc",
                    "url": "",
                    "snippets": [
                        "plain string",
                        {"snippet": "dict snippet"},
                        {"snippet": {"text": "nested snippet"}},
                    ],
                    "document": {},
                }
            ]
        }
        results = _parse_search_response(data)
        texts = [s.text for s in results[0].snippets]
        assert texts == ["plain string", "dict snippet", "nested snippet"]

    def test_missing_fields_dont_crash(self):
        data = {"results": [{}]}
        results = _parse_search_response(data)
        assert len(results) == 1
        assert results[0].title == ""
        assert results[0].snippets == []


class TestFormatResultsForContext:
    def test_no_results(self):
        assert format_results_for_context([]) == "No relevant documents found."

    def test_single_result(self):
        results = [
            SearchResult(
                title="PTO Policy",
                url="https://example.com/pto",
                snippets=[SearchResultSnippet(text="Employees get 20 days.")],
            )
        ]
        output = format_results_for_context(results)
        assert "[1] PTO Policy" in output
        assert "https://example.com/pto" in output
        assert "Employees get 20 days." in output

    def test_multiple_results_numbered(self):
        results = [
            SearchResult(title=f"Doc {i}", url=f"https://example.com/{i}", snippets=[])
            for i in range(1, 4)
        ]
        output = format_results_for_context(results)
        assert "[1] Doc 1" in output
        assert "[2] Doc 2" in output
        assert "[3] Doc 3" in output

    def test_result_without_url(self):
        results = [SearchResult(title="No URL Doc", url=None, snippets=[])]
        output = format_results_for_context(results)
        assert "[1] No URL Doc" in output
        assert "URL:" not in output

    def test_result_without_title_uses_untitled(self):
        results = [SearchResult(title=None, url=None, snippets=[])]
        output = format_results_for_context(results)
        assert "Untitled" in output
