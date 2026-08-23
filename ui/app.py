import os

import requests
import streamlit as st

API_URL = os.getenv("FINSIGHT_API_URL", "http://localhost:8000")

SAMPLE_QUESTIONS = [
    "What was NVIDIA's revenue in its latest fiscal year?",
    "How does Apple describe its supply chain risks?",
    "Compare R&D spending across the three companies and explain what drives it.",
    "What risks do all three companies have in common?",
]

ROUTE_LABELS = {
    "graph": "knowledge graph",
    "vector": "vector search",
    "hybrid": "hybrid (vector + graph)",
}


def ask(question):
    resp = requests.post(f"{API_URL}/query", json={"question": question}, timeout=180)
    resp.raise_for_status()
    return resp.json()


st.set_page_config(page_title="FinSight", page_icon="📊")
st.title("FinSight")
st.caption(
    "Ask about the latest 10-K filings of Apple, Microsoft, and NVIDIA. "
    "Quantitative questions hit the knowledge graph, narrative ones the vector store."
)

with st.sidebar:
    st.subheader("Try asking")
    for sample in SAMPLE_QUESTIONS:
        if st.button(sample, use_container_width=True):
            st.session_state.pending = sample
    st.divider()
    st.caption(f"API: {API_URL}")

if "history" not in st.session_state:
    st.session_state.history = []

for entry in st.session_state.history:
    with st.chat_message("user"):
        st.write(entry["question"])
    with st.chat_message("assistant"):
        st.write(entry["answer"])
        st.caption(f"answered via {ROUTE_LABELS.get(entry['route'], entry['route'])}")

question = st.chat_input("e.g. What was Apple's net income?")
if question is None:
    question = st.session_state.pop("pending", None)

if question:
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        with st.spinner("Routing, retrieving, generating..."):
            try:
                result = ask(question)
            except requests.HTTPError as e:
                st.error(f"API error {e.response.status_code}: {e.response.text[:200]}")
                st.stop()
            except requests.RequestException:
                st.error(f"Could not reach the FinSight API at {API_URL}. Is it running?")
                st.stop()
        st.write(result["answer"])
        st.caption(f"answered via {ROUTE_LABELS.get(result['route'], result['route'])}")
    st.session_state.history.append({"question": question, **result})
