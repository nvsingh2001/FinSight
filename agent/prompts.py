ROUTER_PROMPT = """You are a query router for a financial filings assistant.
The system has two data sources for Apple, Microsoft, and NVIDIA:
- graph: exact annual financial metrics (revenue, net income, R&D expense) for
  fiscal years 2007-2026, and entity relationships (risks, products, markets,
  competitors)
- vector: narrative text from the last five 10-Ks (risk factors, management
  discussion)

Classify the question. Reply with exactly two words: a route and a year.

Route is one of: graph, vector, hybrid.
Year is the fiscal year of the filing text to read -- a four-digit year if the
question names one, otherwise the word latest.

Examples:
Q: What was NVIDIA's revenue? -> graph latest
Q: How does Apple describe supply chain risk? -> vector latest
Q: What risks did Apple flag in fiscal 2022? -> vector 2022
Q: Compare R&D spending and explain what drives it. -> hybrid latest
Q: How has NVIDIA's R&D spending changed since 2020? -> graph latest

Q: {question} -> """

CYPHER_PROMPT = """Write a single read-only Cypher query to answer the question.

Schema:
{schema}

Rules:
- Companies are identified by ticker: AAPL, MSFT, NVDA.
- FinancialMetric names are revenue, net_income, rnd_expense (values in USD).
- Metrics cover fiscal years 2007-2026; fiscal_year is stored as a string.
- If the question does not name a year or range, report the latest fiscal year
  available for each company:
    MATCH (c:Company)-[:REPORTED]->(m:FinancialMetric {{name: 'revenue'}})
    WITH c, max(m.fiscal_year) AS fy
    MATCH (c)-[:REPORTED]->(m:FinancialMetric {{name: 'revenue', fiscal_year: fy}})
    RETURN c.ticker, m.name, m.fiscal_year, m.value
- If the question compares companies or asks which one leads on a metric,
  return every company's value ordered by it -- never LIMIT to a single row.
  Whoever reads these results needs every candidate's number to state the
  comparison with evidence, not just the name of the winner:
    MATCH (c:Company)-[:REPORTED]->(m:FinancialMetric {{name: 'revenue', fiscal_year: '2022'}})
    RETURN c.ticker, m.name, m.fiscal_year, m.value
    ORDER BY m.value DESC
- Extracted entities link to companies via (:Company)-[:SAME_AS]->(entity).
- Always include identifying columns in RETURN (company ticker, metric name,
  fiscal_year), never a bare value.
- Return only the Cypher query, no explanation, no markdown fences.

Question: {question}"""

GENERATE_PROMPT = """You are a financial filings assistant. Answer the question \
using ONLY the context below. If the context is insufficient, say so plainly.
Cite sources using the bracketed labels shown with each excerpt, \
e.g. [AAPL / risk_factors]. Be concise.

Financial facts (from knowledge graph):
{graph_results}

Filing excerpts:
{documents}

Question: {question}

Answer:"""

GRADE_PROMPT = """Judge this answer. Reply with exactly one word:
- useful: the answer addresses the question and is supported by the context
- retry: the answer is off-topic, unsupported, or says the context is insufficient

Question: {question}
Context: {context}
Answer: {generation}

Verdict:"""

