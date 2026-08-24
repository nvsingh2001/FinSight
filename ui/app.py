import json
import os

import requests
import streamlit as st

API_URL = os.getenv("FINSIGHT_API_URL", "http://localhost:8000")

SAMPLE_QUESTIONS = [
    "What was NVIDIA's revenue in its latest fiscal year?",
    "How does Apple describe its supply chain risks?",
    "What risks did Apple flag in fiscal 2022?",
    "How has NVIDIA's revenue changed since 2020?",
    "Compare R&D spending across the three companies and explain what drives it.",
    "What risks do all three companies have in common?",
]

SUGGESTIONS = {
    "NVIDIA's latest revenue": SAMPLE_QUESTIONS[0],
    "Apple's supply chain risks": SAMPLE_QUESTIONS[1],
    "What Apple flagged in FY2022": SAMPLE_QUESTIONS[2],
    "NVIDIA's revenue since 2020": SAMPLE_QUESTIONS[3],
    "R&D across the three": SAMPLE_QUESTIONS[4],
}

ROUTE_LABELS = {
    "graph": "knowledge graph",
    "vector": "vector search",
    "hybrid": "hybrid (vector + graph)",
}


def answered_via(route, year):
    label = ROUTE_LABELS.get(route, route or "?")
    if year and year != "latest" and route in ("vector", "hybrid"):
        label += f", FY{year} filings"
    return f"answered via {label}"


def ask(question):
    resp = requests.post(f"{API_URL}/query", json={"question": question}, timeout=180)
    resp.raise_for_status()
    return resp.json()


def pick_suggestion():
    choice = st.session_state.suggestion
    if choice:
        st.session_state.pending = SUGGESTIONS[choice]
        st.session_state.suggestion = None


@st.cache_data(ttl=600, show_spinner=False)
def load_stats():
    try:
        resp = requests.get(f"{API_URL}/stats", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return None


def ask_stream(question):
    resp = requests.post(
        f"{API_URL}/query/stream",
        json={"question": question},
        stream=True,
        timeout=180,
    )
    resp.raise_for_status()
    for line in resp.iter_lines():
        if line:
            yield json.loads(line)


st.set_page_config(page_title="FinSight", page_icon="📊")
st.title("FinSight")
st.caption(
    "Ask about the 10-K filings of Apple, Microsoft, and NVIDIA. Quantitative "
    "questions hit the knowledge graph, narrative ones the vector store. Name a "
    "fiscal year and the filings for that year are the ones that get read."
)

with st.sidebar:
    st.subheader("Try asking")
    for sample in SAMPLE_QUESTIONS:
        if st.button(sample, width="stretch"):
            st.session_state.pending = sample
    st.divider()
    st.caption(f"API: {API_URL}")

if "history" not in st.session_state:
    st.session_state.history = []

question = st.chat_input("e.g. What was Apple's net income?", submit_mode="disable")
if question is None:
    question = st.session_state.pop("pending", None)

if not st.session_state.history and not question:
    stats = load_stats()
    if stats:
        cols = st.columns(3)
        cols[0].metric("Companies", stats["companies"], border=True)
        cols[1].metric(
            "Filings indexed",
            stats["filings"],
            border=True,
            help=f"{stats['chunks']:,} passages embedded for retrieval",
        )
        cols[2].metric(
            "Fiscal years per company",
            stats["fiscal_years"],
            border=True,
            help=f"{stats['first_year']}-{stats['last_year']} across the three",
        )

    st.pills(
        "Try one of these",
        list(SUGGESTIONS),
        key="suggestion",
        on_change=pick_suggestion,
    )

for entry in st.session_state.history:
    with st.chat_message("user"):
        st.write(entry["question"])
    with st.chat_message("assistant"):
        st.write(entry["answer"])
        st.caption(answered_via(entry["route"], entry.get("year")))

if question:
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        status = st.status("thinking...", expanded=False)
        box = st.empty()
        buf, meta = "", {}
        try:
            for ev in ask_stream(question):
                if ev["type"] == "progress":
                    status.update(label=ev["stage"])
                elif ev["type"] == "token":
                    buf += ev["text"]
                    box.markdown(buf + "▌")
                elif ev["type"] == "revising":
                    buf = ""
                    box.empty()
                    status.update(label="first draft rejected, revising...")
                elif ev["type"] == "done":
                    meta = ev
        except requests.RequestException:
            st.error(f"Could not reach the FinSight API at {API_URL}. Is it running?")
            st.stop()
        box.markdown(buf)
        status.update(
            state="complete",
            label=answered_via(meta.get("route"), meta.get("year")),
        )
    st.session_state.history.append(
        {
            "question": question,
            "answer": buf,
            "route": meta.get("route", "?"),
            "year": meta.get("year"),
        }
    )
