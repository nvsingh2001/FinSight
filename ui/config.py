import os

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

ROUTE_BADGE_COLORS = {
    "graph": "blue",
    "vector": "green",
    "hybrid": "violet",
}

ASSISTANT_AVATAR = ":material/insights:"
