# ChatBI

A Streamlit Text-to-SQL demo for business analytics. Ask a business question in natural language and get a retrieval-grounded SQL query, a read-only safety check, live results, charts, and a concise business interpretation.

## Overview

ChatBI is built for demoing how business users can explore data without writing SQL. It is not a thin "LLM writes SQL" wrapper — it implements a small but real **RAG → generate → validate → execute → verify** pipeline. It supports two paths:

- **Sample databases** for guided demos across E-commerce, HR Analytics, and SaaS Metrics.
- **Upload mode** for user CSV files, with an optional knowledge base for business context and metric definitions.

## Pipeline

```text
User question
      ↓
1. Retrieval (RAG)      schema linking picks the relevant tables +
                        dynamic few-shot pulls the most similar SQL examples
      ↓
2. SQL generation       DeepSeek writes SQLite from the *narrowed* schema + examples + metric dictionary
      ↓
3. Safety gate          AST parse (sqlglot): SELECT-only, table whitelist,
                        no DDL/DML, single statement, 1000-row cap
      ↓
4. Execution            runs against an in-memory SQLite database (read-only intent)
      ↓
5. Result validation    empty / truncated / all-NULL sanity checks
      ↓
6. Interpretation       3-sentence business read-out + logged to the query log
```

The retrieval, safety, and validation logic lives in `ragbi.py` (Streamlit-free, so it is unit-testable in isolation).

## Why RAG here

Dumping a full schema into the prompt does not scale past a handful of tables and dilutes the model's attention. ChatBI instead **retrieves** the relevant tables for each question (schema linking), expands business terms through a **metric/synonym dictionary** (e.g. "净收入" → `revenue`, `refund_amount`), and injects only the **few-shot examples most similar to the question**. At demo scale the sample DBs are small, but the retrieval step is real and visible in the UI — open *Step 2 — Retrieval (RAG)* to see the per-table relevance scores and the examples that were pulled.

## Features

- **Retrieval-grounded Text-to-SQL** — schema linking + dynamic few-shot + metric dictionary, then DeepSeek generates SQLite.
- **AST-based SQL safety gate** — `sqlglot` parses the query (not string matching): only a single read-only `SELECT`/CTE over whitelisted tables is allowed; `INSERT`/`UPDATE`/`DELETE`/`DROP`/`ALTER`/`PRAGMA`/`ATTACH` and stacked statements are blocked; a row cap is enforced. Falls back to a regex gate if `sqlglot` is unavailable.
- **Result validation** — flags empty results, truncated results, and all-NULL columns.
- **Query log** — every request records the retrieved tables, latency, validation status, and parser used.
- **Complex analytics** — supports joins, CTEs, CASE logic, rankings, cumulative totals, month-over-month changes, and rolling averages.
- **Live execution** — queries run against an in-memory SQLite database.
- **Bilingual UI** — English and Chinese labels, prompts, sample questions, and interpretations.
- **Theme-friendly UI** — light and dark mode readable buttons, inputs, result boxes, and upload controls.
- **Business context input** — users can describe KPI definitions, field meanings, and join rules.
- **Knowledge docs** — optional `.txt` / `.md` uploads to help the model understand business context.
- **CSV upload** — load one or more CSV files into SQLite tables for ad hoc querying.
- **CSV export** — download query results with one click.

## Built-In Demo Scenarios

### E-commerce

Scenario: GMV is growing, but leadership needs to know whether profit is leaking through discounts, refunds, ad spend, or stockouts.

Tables:

- `orders`
- `customers`
- `marketing`
- `products`
- `inventory`
- `returns`
- `promotions`
- `monthly_targets`

Good demo questions:

- Monthly GMV with trailing 3-month moving average
- Promotion lift after discounts and refunds
- GMV target attainment after stockouts
- Net profit by category after refunds, promo spend, and ad spend

### HR Analytics

Scenario: The company is growing headcount, but wants to identify regrettable attrition and decide who needs a retention offer first.

Tables:

- `employees`
- `departments`
- `performance_reviews`
- `engagement_surveys`
- `terminations`
- `compensation_benchmarks`

Good demo questions:

- Regrettable attrition by department and exit reason
- High performers below market pay with high flight risk
- Workload and engagement drivers of regrettable attrition
- Retention save list ranked by performance, pay gap, and flight risk

### SaaS Metrics

Scenario: MRR is expanding, but the team needs to find accounts where low usage, contraction, late payment, or poor health puts revenue at risk.

Tables:

- `subscriptions`
- `monthly_metrics`
- `accounts`
- `product_usage`
- `invoices`
- `mrr_movements`
- `health_scores`

Good demo questions:

- NRR by segment with expansion and contraction
- Usage decline and health score churn risk
- Late payment, low usage, and high support risk accounts
- Customer save list ranked by MRR at risk

## Upload Requirements

### CSV Files

- Format: `.csv`
- Recommended size: up to 50 MB per file
- Recommended row count: up to 500k rows per file
- Structure: one record per row, first row as column headers
- Column names: use simple names with letters, numbers, and underscores
- Multiple files: supported, especially when they share join keys such as `customer_id`, `order_id`, `emp_id`, `month`, or `date`

The app sanitizes uploaded table and column names for SQLite compatibility.

### Knowledge Docs

- Format: `.txt` or `.md`
- Recommended size: up to 2 MB per file
- Purpose: explain business context so generated SQL matches the user's data semantics
- Best content to include:
  - KPI definitions, such as `GMV = revenue - refund_amount`
  - Field meanings, such as `paid_on_time = 1 means paid on time`
  - Join rules, such as `orders.order_id = customers.order_id`
  - Business goals, such as reducing churn, improving net revenue, or finding inventory gaps

This knowledge text feeds the metric dictionary used during retrieval and is passed into the SQL-generation and interpretation prompts. The retrieval step here is lexical (token + synonym matching over schema and examples) rather than embedding-based — a deliberate, dependency-light choice for a demo. The same `retrieve_context()` seam in `ragbi.py` is where a vector store / embedding retriever would plug in for a production-scale schema.

## Are The Database Tables Created?

Yes. The built-in sample database tables are created automatically at runtime.

When the app starts and a sample database is selected, `app.py` creates an in-memory SQLite database with `sqlite3.connect(":memory:")`, then runs the sample database's `CREATE TABLE` and `INSERT` statements from `SAMPLE_DBS`.

For uploaded CSV files, the app creates an in-memory SQLite table for each uploaded file using `pandas.DataFrame.to_sql(...)`.

No physical database file is written. The data exists only in the current Streamlit session memory.

## Stack

| Layer | Tools |
|---|---|
| Frontend | Streamlit |
| Database | SQLite in memory |
| AI | DeepSeek `deepseek-chat` via OpenAI-compatible API |
| Retrieval + safety | `ragbi.py` — schema linking, dynamic few-shot, `sqlglot` AST safety gate, result validation |
| Charts | Plotly Express |

## Quickstart

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=your_deepseek_api_key
streamlit run app.py
```

## Related

- [AI Data Analyst](https://github.com/josephwang-ds/ai-data-analyst) — CSV upload → natural language analysis + charts
- [A/B Test Analyzer](https://github.com/josephwang-ds/ab-test-analyzer) — experiment data → significance test → verdict

---

[josephjwang.com](https://josephjwang.com) · [github.com/josephwang-ds](https://github.com/josephwang-ds)
