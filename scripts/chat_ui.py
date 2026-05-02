"""
Streamlit chat interface for the Glean RAG chatbot.

Usage (from repo root with venv active):
    streamlit run scripts/chat_ui.py
"""

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

with st.sidebar:
    st.header("Settings")
    num_results = st.slider("Search results to use", min_value=1, max_value=10, value=5)
    datasource = st.text_input("Datasource filter", value="interviewds")
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
            docs = build_documents(datasource)
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
