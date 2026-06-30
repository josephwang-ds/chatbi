"""
ChatBI — retrieval, safety, and validation layer.

This module upgrades the demo from "dump the full schema → LLM → run whatever
SQL comes back" into a small but real RAG + guardrail pipeline:

  retrieve_context()  — schema linking + dynamic few-shot   (the RAG step)
  validate_sql()      — AST-based safety gate                (defense)
  validate_result()   — sanity checks on the returned rows   (verification)

It is kept Streamlit-free and dependency-light (sqlglot is optional, with a
regex fallback) so every function can be unit-tested in isolation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# sqlglot gives us a real parser (AST) instead of string matching. We degrade
# gracefully to a regex gate if it is not installed, so the app never crashes.
try:
    import sqlglot
    from sqlglot import exp

    _HAS_SQLGLOT = True
except Exception:  # pragma: no cover - exercised only when sqlglot missing
    _HAS_SQLGLOT = False


# ─────────────────────────────────────────────────────────────────────────────
# 1. RETRIEVAL  (schema linking + dynamic few-shot)
# ─────────────────────────────────────────────────────────────────────────────

_STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "to", "by", "for", "in", "on", "with",
    "what", "which", "who", "how", "show", "me", "give", "find", "list", "get",
    "is", "are", "do", "does", "per", "each", "all", "top", "vs", "after",
    "请", "查", "查询", "计算", "统计", "一下", "和", "的", "与", "按", "每",
    "哪些", "哪个", "多少", "是", "有", "在", "对", "我", "想", "看", "下",
}

# Business synonyms → schema-ish tokens. This is the "metric dictionary" that
# lets a vague business word retrieve the right tables/columns.
_SYNONYMS = {
    "revenue": ["revenue", "gmv", "sales", "net", "mrr"],
    "gmv": ["gmv", "revenue", "sales"],
    "sales": ["sales", "revenue", "orders", "units"],
    "profit": ["profit", "gross_profit", "margin", "cost"],
    "margin": ["margin", "gross_profit", "profit", "cost"],
    "refund": ["refund", "returns", "refund_amount"],
    "return": ["returns", "refund"],
    "churn": ["churn", "churned", "terminations", "mrr_movements", "attrition"],
    "attrition": ["attrition", "terminations", "churn"],
    "retention": ["retention", "churned", "engagement", "health"],
    "customer": ["customer", "customers", "accounts", "segment"],
    "account": ["accounts", "customer", "subscriptions"],
    "employee": ["employees", "headcount", "departments"],
    "headcount": ["employees", "headcount", "departments"],
    "pay": ["salary", "compensation", "compensation_benchmarks", "pay"],
    "salary": ["salary", "compensation", "compensation_benchmarks"],
    "engagement": ["engagement", "engagement_surveys", "health"],
    "usage": ["usage", "product_usage", "active"],
    "health": ["health", "health_scores", "risk"],
    "risk": ["risk", "health_scores", "flight", "churn"],
    "payment": ["invoices", "paid", "payment", "late"],
    "invoice": ["invoices", "payment"],
    "ad": ["marketing", "ad_spend", "impressions", "clicks"],
    "marketing": ["marketing", "ad_spend", "channel"],
    "promotion": ["promotions", "promo", "discount"],
    "discount": ["promotions", "discount", "promo"],
    "inventory": ["inventory", "stock", "stockout"],
    "stockout": ["inventory", "stock"],
    "mrr": ["mrr", "monthly_metrics", "subscriptions", "revenue"],
    "nrr": ["mrr_movements", "expansion", "contraction", "mrr"],
    "target": ["monthly_targets", "target", "attainment"],
    # Chinese surface forms
    "收入": ["revenue", "gmv", "net", "mrr"],
    "净收入": ["net", "revenue", "refund_amount"],
    "利润": ["profit", "gross_profit", "margin"],
    "毛利": ["gross_profit", "margin", "profit"],
    "退款": ["refund", "returns", "refund_amount"],
    "流失": ["churn", "churned", "terminations", "mrr_movements"],
    "客户": ["customer", "customers", "accounts", "segment"],
    "员工": ["employees", "departments", "headcount"],
    "薪资": ["salary", "compensation", "compensation_benchmarks"],
    "活跃": ["active", "is_active", "usage", "product_usage"],
    "投放": ["marketing", "ad_spend", "channel"],
    "促销": ["promotions", "discount", "promo"],
    "库存": ["inventory", "stock"],
    "订阅": ["subscriptions", "mrr", "monthly_metrics"],
    "渠道": ["channel", "marketing"],
}

# Domain-neutral few-shot library. Each example teaches one SQL *pattern*; the
# retriever picks the 1-2 most relevant to the question instead of pasting all.
FEWSHOT_LIBRARY = [
    {
        "tags": ["monthly", "trend", "moving average", "rolling", "month", "时间", "趋势", "月度", "移动平均"],
        "question": "Monthly revenue with a trailing 3-month moving average",
        "sql": (
            "WITH monthly AS (\n"
            "  SELECT strftime('%Y-%m', order_date) AS month, SUM(revenue) AS revenue\n"
            "  FROM orders GROUP BY month\n"
            ")\n"
            "SELECT month, revenue,\n"
            "       AVG(revenue) OVER (ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS ma_3m\n"
            "FROM monthly ORDER BY month;"
        ),
    },
    {
        "tags": ["rank", "top", "by", "segment", "category", "排名", "分组", "细分"],
        "question": "Rank categories by net revenue",
        "sql": (
            "SELECT category, SUM(revenue - refund_amount) AS net_revenue,\n"
            "       RANK() OVER (ORDER BY SUM(revenue - refund_amount) DESC) AS rnk\n"
            "FROM orders GROUP BY category ORDER BY net_revenue DESC;"
        ),
    },
    {
        "tags": ["join", "customer", "profile", "risk", "health", "关联", "客户", "风险"],
        "question": "High-risk customers with high net revenue",
        "sql": (
            "SELECT c.customer_id, c.segment, SUM(o.revenue - o.refund_amount) AS net_revenue\n"
            "FROM orders o JOIN customers c ON o.customer_id = c.customer_id\n"
            "WHERE c.health_score < 50\n"
            "GROUP BY c.customer_id, c.segment\n"
            "ORDER BY net_revenue DESC LIMIT 20;"
        ),
    },
    {
        "tags": ["rate", "ratio", "share", "percent", "占比", "比率", "退款率"],
        "question": "Refund rate by segment",
        "sql": (
            "SELECT segment,\n"
            "       SUM(refund_amount) * 1.0 / NULLIF(SUM(revenue), 0) AS refund_rate\n"
            "FROM orders GROUP BY segment ORDER BY refund_rate DESC;"
        ),
    },
    {
        "tags": ["change", "growth", "mom", "vs previous", "环比", "增长", "变化"],
        "question": "Month-over-month revenue change",
        "sql": (
            "WITH m AS (\n"
            "  SELECT strftime('%Y-%m', order_date) AS month, SUM(revenue) AS revenue\n"
            "  FROM orders GROUP BY month\n"
            ")\n"
            "SELECT month, revenue,\n"
            "       revenue - LAG(revenue) OVER (ORDER BY month) AS mom_change\n"
            "FROM m ORDER BY month;"
        ),
    },
]


_TABLE_HEADER = re.compile(r"^\s*(?:\d+\.|Table:)\s+([A-Za-z_]\w*)", re.MULTILINE)
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[一-鿿]+")


@dataclass
class TableInfo:
    name: str
    block: str
    tokens: set = field(default_factory=set)


def _tokenize(text: str) -> list:
    return [w.lower() for w in _WORD.findall(text or "")]


def parse_schema(schema_str: str) -> list:
    """Split a schema string into per-table blocks with a token bag for scoring.

    Handles both the sample-DB format ("1. orders (...)") and the uploaded-CSV
    format ("Table: data (...)\\nSample rows: ...").
    """
    matches = list(_TABLE_HEADER.finditer(schema_str or ""))
    tables = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(schema_str)
        block = schema_str[start:end].strip()
        name = m.group(1)
        tokens = set(_tokenize(block))
        tables.append(TableInfo(name=name, block=block, tokens=tokens))
    return tables


def _expand(tokens: list) -> set:
    out = set()
    for tok in tokens:
        if tok in _STOPWORDS:
            continue
        out.add(tok)
        for syn in _SYNONYMS.get(tok, []):
            out.add(syn.lower())
    return out


def retrieve_tables(question: str, schema_str: str, top_k: int = 4) -> dict:
    """Schema linking: pick the tables most relevant to the question.

    Returns a dict with the assembled schema text, the selected table names, and
    a per-table score trace (so the UI can *show* the retrieval step).
    """
    tables = parse_schema(schema_str)
    if not tables:
        return {"schema": schema_str, "selected": [], "trace": [], "linked": False}

    q_tokens = _expand(_tokenize(question))

    scored = []
    for tbl in tables:
        # Table-name hits are worth more than column hits.
        name_hit = 2 if tbl.name.lower() in q_tokens else 0
        col_hits = len(q_tokens & tbl.tokens)
        scored.append((tbl, name_hit + col_hits))

    scored.sort(key=lambda x: x[1], reverse=True)
    seeds = [t for t, s in scored if s > 0][:top_k]

    # Join expansion: pull in tables that share an id-style key with a seed so
    # the model can actually write the JOIN it needs.
    selected = list(seeds)
    seed_keys = {tok for t in seeds for tok in t.tokens if tok.endswith("_id")}
    for tbl, s in scored:
        if tbl in selected:
            continue
        if seed_keys & {tok for tok in tbl.tokens if tok.endswith("_id")}:
            selected.append(tbl)
        if len(selected) >= top_k + 2:
            break

    linked = len(selected) > 0 and len(selected) < len(tables)
    if not selected:
        # Nothing matched — fall back to the full schema rather than starve the model.
        selected = tables

    schema_text = "Tables:\n" + "\n".join(
        f"{i + 1}. {tbl.block.lstrip('0123456789. ').replace('Table: ', '')}"
        for i, tbl in enumerate(selected)
    )
    trace = [{"table": t.name, "score": s} for t, s in scored]
    return {
        "schema": schema_text,
        "selected": [t.name for t in selected],
        "trace": trace,
        "linked": linked,
    }


def retrieve_fewshots(question: str, n: int = 2) -> list:
    """Dynamic few-shot: return the n examples most similar to the question."""
    q_tokens = _expand(_tokenize(question))
    scored = []
    for ex in FEWSHOT_LIBRARY:
        tag_tokens = set()
        for tag in ex["tags"]:
            tag_tokens |= set(_tokenize(tag))
        score = len(q_tokens & tag_tokens)
        scored.append((ex, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [ex for ex, s in scored[:n] if s > 0]


def retrieve_context(question: str, schema_str: str, top_k: int = 4, n_shots: int = 2) -> dict:
    """One call that does the whole RAG step: schema linking + few-shot."""
    tbl = retrieve_tables(question, schema_str, top_k=top_k)
    shots = retrieve_fewshots(question, n=n_shots)
    return {**tbl, "fewshots": shots}


def render_fewshot_block(shots: list) -> str:
    if not shots:
        return ""
    parts = ["Here are relevant SQL examples for similar questions:"]
    for ex in shots:
        parts.append(f"-- Q: {ex['question']}\n{ex['sql']}")
    return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# 2. SAFETY  (AST-based SQL validation)
# ─────────────────────────────────────────────────────────────────────────────

_FORBIDDEN_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|replace|merge|grant|"
    r"revoke|attach|detach|pragma|vacuum|reindex)\b",
    re.IGNORECASE,
)


@dataclass
class SQLCheck:
    ok: bool
    reason_en: str = ""
    reason_zh: str = ""
    safe_sql: str = ""
    parser: str = "regex"
    tables: list = field(default_factory=list)


def validate_sql(sql: str, allowed_tables, max_rows: int = 1000) -> SQLCheck:
    """Read-only gate. Allows a single SELECT/CTE over whitelisted tables only,
    blocks every DDL/DML statement, and caps the row count.

    Uses sqlglot's AST when available (real parsing, not string matching) and
    falls back to a regex gate otherwise.
    """
    allowed = {str(t).lower() for t in (allowed_tables or [])}
    raw = (sql or "").strip().rstrip(";").strip()
    if not raw:
        return SQLCheck(False, "Empty SQL.", "SQL 为空。")

    if not _HAS_SQLGLOT:
        return _validate_sql_regex(raw, allowed, max_rows)

    # --- AST path -----------------------------------------------------------
    try:
        statements = [s for s in sqlglot.parse(raw, read="sqlite") if s is not None]
    except Exception as e:
        return SQLCheck(False, f"Could not parse SQL: {e}", f"无法解析 SQL：{e}", parser="sqlglot")

    if len(statements) != 1:
        return SQLCheck(
            False,
            "Only a single statement is allowed (no stacked queries).",
            "只允许单条语句，禁止堆叠多条查询。",
            parser="sqlglot",
        )

    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.With, exp.Union, exp.Subquery)):
        return SQLCheck(
            False,
            "Only read-only SELECT queries are allowed.",
            "只允许只读 SELECT 查询。",
            parser="sqlglot",
        )

    # Any write/DDL node anywhere in the tree is fatal.
    forbidden_types = (
        exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter,
        exp.Command, exp.Set, exp.AlterTable if hasattr(exp, "AlterTable") else exp.Alter,
    )
    for node in tree.walk():
        node = node[0] if isinstance(node, tuple) else node
        if isinstance(node, forbidden_types):
            return SQLCheck(
                False,
                "Statement contains a non-SELECT / DDL operation.",
                "语句包含非 SELECT 或 DDL 操作。",
                parser="sqlglot",
            )

    # Table whitelist (CTE names are allowed even if not physical tables).
    cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    used_tables = {t.name.lower() for t in tree.find_all(exp.Table) if t.name}
    unknown = sorted(used_tables - allowed - cte_names)
    if allowed and unknown:
        return SQLCheck(
            False,
            f"Query references tables outside the whitelist: {', '.join(unknown)}.",
            f"查询引用了白名单外的表：{', '.join(unknown)}。",
            parser="sqlglot",
            tables=sorted(used_tables),
        )

    # Enforce a row cap on the top-level query.
    try:
        if isinstance(tree, exp.Select) and not tree.args.get("limit"):
            tree = tree.limit(max_rows)
        safe_sql = tree.sql(dialect="sqlite", pretty=True)
    except Exception:
        safe_sql = raw

    return SQLCheck(True, parser="sqlglot", safe_sql=safe_sql, tables=sorted(used_tables))


def _validate_sql_regex(raw: str, allowed: set, max_rows: int) -> SQLCheck:
    if ";" in raw:
        return SQLCheck(False, "Multiple statements are not allowed.", "禁止多条语句。")
    if not re.match(r"^\s*(select|with)\b", raw, re.IGNORECASE):
        return SQLCheck(False, "Only SELECT queries are allowed.", "只允许 SELECT 查询。")
    if _FORBIDDEN_RE.search(raw):
        return SQLCheck(False, "Statement contains a forbidden keyword.", "语句包含被禁止的关键字。")
    safe_sql = raw
    if not re.search(r"\blimit\b", raw, re.IGNORECASE):
        safe_sql = f"{raw}\nLIMIT {max_rows}"
    return SQLCheck(True, parser="regex", safe_sql=safe_sql)


# ─────────────────────────────────────────────────────────────────────────────
# 3. VERIFICATION  (result sanity checks)
# ─────────────────────────────────────────────────────────────────────────────

def validate_result(df, max_rows: int = 1000) -> list:
    """Cheap sanity checks on the result set. Returns a list of warning dicts
    with bilingual messages; an empty list means the result looks fine."""
    warnings = []
    if df is None or len(df) == 0:
        warnings.append({
            "level": "warn",
            "en": "Query returned 0 rows — the filter may be too strict or a metric definition may be off.",
            "zh": "查询返回 0 行 —— 过滤条件可能过严，或指标口径有误。",
        })
        return warnings

    if len(df) >= max_rows:
        warnings.append({
            "level": "info",
            "en": f"Result hit the {max_rows}-row cap and may be truncated.",
            "zh": f"结果触达 {max_rows} 行上限，可能被截断。",
        })

    # Columns that are entirely NULL usually signal a wrong column/join.
    null_cols = [c for c in df.columns if df[c].isna().all()]
    if null_cols:
        warnings.append({
            "level": "warn",
            "en": f"Columns are entirely NULL: {', '.join(map(str, null_cols))}.",
            "zh": f"以下列全部为空：{', '.join(map(str, null_cols))}。",
        })

    return warnings
