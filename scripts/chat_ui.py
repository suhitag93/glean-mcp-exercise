"""
Streamlit chat interface for the Glean RAG chatbot.

Usage (from repo root with venv active):
    streamlit run scripts/chat_ui.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import streamlit as st

from glean_chatbot.chat import chat
from glean_chatbot.config import get_config
from glean_chatbot.indexer import build_documents, register_datasource, _index_documents
from glean_chatbot.search import search

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Glean Knowledge Base",
    page_icon="🔍",
    layout="centered",
)

st.title("🔍 Glean Knowledge Base")
st.caption("Ask anything about the Acme Corp knowledge base.")

# ── Sidebar settings ─────────────────────────────────────────────────────────

# Known datasource configs: (url_prefix, object_type)
DATASOURCE_CONFIGS: dict[str, tuple[str, str]] = {
    "interviewds":  ("https://internal.example.com/policies", "KnowledgeArticle"),
    "interviewds2": ("https://internal.example.com/policies", "Article"),
    "interviewds4": ("https://internal.example.com/policies", "Article"),
    "interviewds5": ("https://internal.example.com/policies", "Article"),
    "interviewds6": ("https://internal.example.com/policies", "Article"),
}

with st.sidebar:
    st.header("Settings")
    num_results = st.slider("Search results to use", min_value=1, max_value=10, value=5)
    datasource = st.text_input("Datasource filter", value="interviewds")

    default_url, default_obj = DATASOURCE_CONFIGS.get(
        datasource, ("https://internal.example.com/policies", "KnowledgeArticle")
    )
    doc_url_prefix = st.text_input(
        "Document URL prefix",
        value=default_url,
        help="Must match the URL regex configured for the datasource in Glean admin",
    )
    object_type = st.text_input(
        "Object type",
        value=default_obj,
        help="Must match an object definition configured for the datasource in Glean admin",
    )
    if st.button("Index this datasource", help="Index all documents from data/documents/ into the selected datasource"):
        cfg = get_config()
        log = st.empty()
        try:
            log.info("Registering datasource…")
            register_datasource(
                base_url=cfg.base_url,
                indexing_token=cfg.indexing_token,
                datasource=datasource,
            )
            log.info("Loading documents…")
            docs = build_documents(datasource, url_prefix=doc_url_prefix, object_type=object_type)
            log.info(f"Indexing {len(docs)} documents into '{datasource}'…")
            _index_documents(
                docs,
                base_url=cfg.base_url,
                indexing_token=cfg.indexing_token,
                datasource=datasource,
            )
            log.empty()
            st.success(f"Indexed {len(docs)} documents into '{datasource}'. It may take a few minutes to appear in search.")
        except Exception as e:
            log.empty()
            msg = str(e)
            if "Object definitions not found" in msg or "object types" in msg:
                st.error(
                    f"Indexing failed: the object type **'{object_type}'** is not configured for "
                    f"datasource **'{datasource}'**. Update the 'Object type' field to match what's "
                    "defined for this datasource in the Glean admin console."
                )
            elif "does not match the URL Regex pattern" in msg:
                # Extract the required regex from the error and derive a usable prefix
                m = re.search(r"URL Regex pattern (.+?) for the datasource", msg)
                if m:
                    detected_regex = m.group(1)
                    # Remove trailing wildcard (e.g. /.*  or .*) then unescape dots
                    detected_prefix = re.sub(r"/?\.?\*$", "", detected_regex)
                    detected_prefix = detected_prefix.replace("\\.", ".").rstrip("/")
                    DATASOURCE_CONFIGS[datasource] = (detected_prefix, object_type)
                    st.warning(
                        f"URL prefix auto-corrected to **`{detected_prefix}`** "
                        f"(detected from datasource regex `{detected_regex}`). "
                        "Click **Index this datasource** again to retry."
                    )
                else:
                    st.error(f"Indexing failed: {e}")
            else:
                st.error(f"Indexing failed: {e}")
    show_sources = st.toggle("Show sources", value=True)
    st.divider()
    if st.button("Clear conversation"):
        st.session_state.messages = []
        st.session_state.chat_session_id = None
        st.rerun()

# ── Session state ─────────────────────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []

if "chat_session_id" not in st.session_state:
    st.session_state.chat_session_id = None

if "active_datasource" not in st.session_state:
    st.session_state.active_datasource = datasource

# Clear conversation when datasource changes
if datasource != st.session_state.active_datasource:
    st.session_state.messages = []
    st.session_state.chat_session_id = None
    st.session_state.active_datasource = datasource

# ── Render chat history ───────────────────────────────────────────────────────

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if show_sources and msg.get("sources"):
            with st.expander("Sources"):
                for i, source in enumerate(msg["sources"], 1):
                    title = source.get("title") or "Untitled"
                    url = source.get("url") or ""
                    snippet = source.get("snippet") or ""
                    if url:
                        st.markdown(f"**{i}. [{title}]({url})**")
                    else:
                        st.markdown(f"**{i}. {title}**")
                    if snippet:
                        st.caption(snippet[:200])

# ── Chat input ────────────────────────────────────────────────────────────────

if question := st.chat_input("Ask a question…"):
    # Show the user message immediately
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    # Run the RAG pipeline
    with st.chat_message("assistant"):
        with st.spinner("Searching…"):
            try:
                cfg = get_config()
                results = search(
                    question,
                    cfg=cfg,
                    page_size=num_results,
                    datasource_filter=datasource or None,
                )
            except Exception as e:
                st.error(f"Search failed: {e}")
                st.stop()

        with st.spinner("Generating answer…"):
            try:
                response = chat(
                    question=question,
                    search_results=results,
                    cfg=cfg,
                    chat_session_id=st.session_state.chat_session_id,
                )
                st.session_state.chat_session_id = response.chat_session_id
            except Exception as e:
                st.error(f"Chat failed: {e}")
                st.stop()

        st.markdown(response.answer)

        sources_data = [
            {
                "title": s.title,
                "url": s.url,
                "snippet": s.snippet,
                "datasource": s.datasource,
            }
            for s in response.sources
        ]

        if show_sources and sources_data:
            with st.expander("Sources"):
                for i, source in enumerate(sources_data, 1):
                    title = source.get("title") or "Untitled"
                    url = source.get("url") or ""
                    snippet = source.get("snippet") or ""
                    if url:
                        st.markdown(f"**{i}. [{title}]({url})**")
                    else:
                        st.markdown(f"**{i}. {title}**")
                    if snippet:
                        st.caption(snippet[:200])

    st.session_state.messages.append({
        "role": "assistant",
        "content": response.answer,
        "sources": sources_data,
    })
