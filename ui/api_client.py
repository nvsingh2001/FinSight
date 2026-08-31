import json

import requests
import streamlit as st

from config import API_URL


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
