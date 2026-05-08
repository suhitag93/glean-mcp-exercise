"""
Streamlit chat interface for the Glean RAG chatbot.

Usage (from repo root with venv active):
    streamlit run scripts/chat_ui.py
"""

import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import find_dotenv, dotenv_values

# find_dotenv() walks up from this script's directory to locate .env, falling
# back to a cwd-based search. Using dotenv_values + os.environ.setdefault
# writes vars explicitly and avoids load_dotenv override-flag issues.
_dotenv_path = (
    find_dotenv(raise_error_if_not_found=False, usecwd=False)
    or find_dotenv(raise_error_if_not_found=False, usecwd=True)
)
for _k, _v in dotenv_values(_dotenv_path).items():
    if _v is not None:
        os.environ.setdefault(_k, _v)

import streamlit as st

from glean_chatbot.chat import chat
from glean_chatbot.config import get_config
from glean_chatbot.indexer import build_documents, register_datasource, _index_documents, _markdown_to_glean_doc, DOCUMENTS_DIR
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
    "interviewds3": ("https://internal.example.com/policies", "Code"),
    "interviewds4": ("https://internal.example.com/policies", "Article"),
    "interviewds5": ("https://internal.example.com/policies", "Article"),
    "interviewds6": ("https://internal.example.com/policies", "Article"),
}

DATASOURCE_OPTIONS = ["interviewds", "interviewds2", "interviewds3", "interviewds4", "interviewds5", "interviewds6"]

with st.sidebar:
    st.header("Settings")
    num_results = st.slider("Search results to use", min_value=1, max_value=10, value=5)
    datasource = st.selectbox("Select datasource", options=DATASOURCE_OPTIONS, index=0)

    doc_url_prefix, object_type = DATASOURCE_CONFIGS.get(
        datasource, ("https://internal.example.com/policies", "KnowledgeArticle")
    )

    st.write(f"**Object type:** `{object_type}`")

    st.divider()
    st.subheader("Index to Datasource")
    uploaded_file = st.file_uploader(
        "Upload a .md file (optional)",
        type=["md"],
        help="If provided, indexes this file. If omitted, indexes all files from data/documents/.",
    )

    if st.button("Index to datasource"):
        cfg = get_config()
        log = st.empty()
        try:
            log.info("Registering datasource…")
            register_datasource(
                base_url=cfg.base_url,
                indexing_token=cfg.indexing_token,
                datasource=datasource,
            )

            if uploaded_file is not None:
                # Index only the uploaded file
                with tempfile.NamedTemporaryFile(delete=False, suffix=".md", prefix=uploaded_file.name.replace(".md", "") + "_") as tmp:
                    tmp.write(uploaded_file.getvalue())
                    tmp_path = Path(tmp.name)
                try:
                    log.info(f"Indexing uploaded file '{uploaded_file.name}'…")
                    doc = _markdown_to_glean_doc(
                        tmp_path,
                        datasource,
                        url_prefix=doc_url_prefix,
                        object_type=object_type,
                    )
                    # Use the original filename as the document ID
                    doc.id = Path(uploaded_file.name).stem
                    _index_documents(
                        [doc],
                        base_url=cfg.base_url,
                        indexing_token=cfg.indexing_token,
                        datasource=datasource,
                    )
                    log.empty()
                    st.success(f"'{uploaded_file.name}' indexed into '{datasource}'. It may take a few minutes to appear in search.")
                finally:
                    os.unlink(tmp_path)
            else:
                # Index all documents from data/documents/
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
                    f"Indexing failed: object type **'{object_type}'** is not configured for "
                    f"datasource **'{datasource}'**. Update DATASOURCE_CONFIGS in chat_ui.py with the correct object type."
                )
            elif "does not match the URL Regex pattern" in msg:
                m = re.search(r"URL Regex pattern (.+?) for the datasource", msg)
                if m:
                    detected_regex = m.group(1)
                    detected_prefix = re.sub(r"/?\.?\*$", "", detected_regex)
                    detected_prefix = detected_prefix.replace("\\.", ".").rstrip("/")
                    DATASOURCE_CONFIGS[datasource] = (detected_prefix, object_type)
                    st.warning(
                        f"URL prefix auto-corrected to **`{detected_prefix}`** "
                        f"(detected from datasource regex `{detected_regex}`). "
                        "Click **Index to datasource** again to retry."
                    )
                else:
                    st.error(f"Indexing failed: {e}")
            else:
                st.error(f"Indexing failed: {e}")

    st.divider()
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
        with st.status("Thinking…", expanded=True) as status:
            st.write(f"Searching **{datasource}** for relevant documents…")
            try:
                cfg = get_config()
                results = search(
                    question,
                    cfg=cfg,
                    page_size=num_results,
                    datasource_filter=datasource or None,
                )
            except Exception as e:
                status.update(label="Search failed", state="error")
                st.error(f"Search failed: {e}")
                st.stop()

            st.write(f"Retrieved **{len(results)}** document(s) — building context…")

            st.write("Sending context to Glean Chat for answer generation…")
            try:
                response = chat(
                    question=question,
                    search_results=results,
                    cfg=cfg,
                    chat_session_id=st.session_state.chat_session_id,
                )
                st.session_state.chat_session_id = response.chat_session_id
            except Exception as e:
                status.update(label="Chat failed", state="error")
                st.error(f"Chat failed: {e}")
                st.stop()

            st.write(f"Done — answer ready from **{len(response.sources)}** cited source(s).")
            status.update(label="Answer ready", state="complete", expanded=False)

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
