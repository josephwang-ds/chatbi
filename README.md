# ChatBI

A natural language interface for business data — type a question, get SQL, results, and an explanation.

## Overview

ChatBI translates plain-English business questions into SQL, executes them against a live database, and returns the results alongside a concise interpretation. No SQL knowledge required.

```
"Which product has the highest gross profit margin?"
        ↓
SELECT product, ROUND(SUM(gross_profit)/SUM(revenue)*100, 2) AS margin_pct
FROM orders GROUP BY product ORDER BY margin_pct DESC
        ↓
| Gadget X | 50.1% |
| Widget A | 44.8% |
        ↓
"Gadget X leads with a 50% gross margin. Widget B is the weakest at 33% — consider a pricing review."
```

## Features

- **Text-to-SQL** — DeepSeek translates the question into valid SQLite, handling aggregations, joins, and ordering automatically
- **Live execution** — query runs against an in-memory SQLite database; results returned as a paginated table
- **Plain-English interpretation** — LLM explains what the numbers mean and highlights the most actionable finding
- **CSV export** — download any result set with one click
- **Built-in sample database** — 3 tables (orders, customers, marketing) with realistic e-commerce data

## Sample questions

- Which product has the highest total revenue?
- What is the gross profit margin by category?
- Compare online vs retail channel revenue
- Which week had the highest ad spend ROI?
- How many new vs returning customers per segment?

## Stack

| Layer | Tools |
|---|---|
| Frontend | Streamlit |
| Database | SQLite (in-memory) |
| AI | DeepSeek `deepseek-chat` via OpenAI-compatible API |

The architecture is database-agnostic — swap SQLite for BigQuery, Snowflake, or Redshift by changing the connection string.

## Quickstart

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=your_deepseek_api_key
streamlit run app.py
```

## Schema

```
orders      — order_id, date, product, category, region, channel, units, revenue, cost, gross_profit
customers   — customer_id, order_id, segment, country, is_new
marketing   — week, channel, ad_spend, impressions, clicks, conversions
```

## Related

- [AI Data Analyst](https://github.com/josephwang-ds/ai-data-analyst) — CSV upload → natural language analysis + charts
- [A/B Test Analyzer](https://github.com/josephwang-ds/ab-test-analyzer) — experiment data → significance test → verdict

---

[josephjwang.com](https://josephjwang.com) · [github.com/josephwang-ds](https://github.com/josephwang-ds)
