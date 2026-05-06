"""Unit tests for indexer.py — document parsing, no API calls."""

import time
from pathlib import Path

import pytest

from glean_chatbot.indexer import _markdown_to_glean_doc


@pytest.fixture
def tmp_md(tmp_path):
    """Factory that writes a .md file and returns its path."""
    def _make(content: str, filename: str = "test_doc.md") -> Path:
        p = tmp_path / filename
        p.write_text(content, encoding="utf-8")
        return p
    return _make


class TestMarkdownToGleanDoc:
    def test_title_extracted_from_h1(self, tmp_md):
        path = tmp_md("# My Great Policy\n\nSome content here.")
        doc = _markdown_to_glean_doc(path, "interviewds")
        assert doc.title == "My Great Policy"

    def test_title_falls_back_to_filename(self, tmp_md):
        path = tmp_md("No heading here, just prose.")
        doc = _markdown_to_glean_doc(path, "interviewds")
        assert doc.title == "Test Doc"

    def test_doc_id_derived_from_stem(self, tmp_md):
        path = tmp_md("# Title", filename="hr_pto_policy.md")
        doc = _markdown_to_glean_doc(path, "interviewds")
        assert doc.id == "hr_pto_policy"

    def test_view_url_uses_prefix_and_id(self, tmp_md):
        path = tmp_md("# Title", filename="my_doc.md")
        doc = _markdown_to_glean_doc(
            path, "interviewds", url_prefix="https://example.com/docs"
        )
        assert doc.view_url == "https://example.com/docs/my_doc"

    def test_url_prefix_trailing_slash_normalised(self, tmp_md):
        path = tmp_md("# Title", filename="my_doc.md")
        doc = _markdown_to_glean_doc(
            path, "interviewds", url_prefix="https://example.com/docs/"
        )
        assert doc.view_url == "https://example.com/docs/my_doc"

    def test_object_type_passed_through(self, tmp_md):
        path = tmp_md("# Title")
        doc = _markdown_to_glean_doc(path, "interviewds2", object_type="Article")
        assert doc.object_type == "Article"

    def test_datasource_set(self, tmp_md):
        path = tmp_md("# Title")
        doc = _markdown_to_glean_doc(path, "interviewds4")
        assert doc.datasource == "interviewds4"

    def test_body_contains_raw_markdown(self, tmp_md):
        content = "# Title\n\nBody paragraph."
        path = tmp_md(content)
        doc = _markdown_to_glean_doc(path, "interviewds")
        assert doc.body.text_content == content

    def test_anonymous_access_enabled(self, tmp_md):
        path = tmp_md("# Title")
        doc = _markdown_to_glean_doc(path, "interviewds")
        assert doc.permissions.allow_anonymous_access is True

    def test_updated_at_is_recent_timestamp(self, tmp_md):
        before = int(time.time())
        path = tmp_md("# Title")
        doc = _markdown_to_glean_doc(path, "interviewds")
        after = int(time.time())
        assert before <= doc.updated_at <= after
