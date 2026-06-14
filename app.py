"""
ChatBI / Text-to-SQL — Demo ②
Ask business questions in plain English → auto-generate SQL → run → explain results.
Supports: built-in sample databases + upload your own CSV.
"""

import os, re, sqlite3, json
import streamlit as st
import pandas as pd
import plotly.express as px
from openai import OpenAI

st.set_page_config(page_title="ChatBI — Natural Language Analytics", page_icon="💬", layout="wide")

st.markdown("""
<style>
  [data-testid="stAppViewContainer"] { background:var(--background-color); }
  [data-testid="stSidebar"] { background:var(--secondary-background-color); }
  [data-testid="stAppViewContainer"] .main .block-container { max-width:1220px; padding-top:1.2rem; }
  [data-testid="stSidebar"] { border-right:1px solid rgba(120,130,150,0.35); }
  [data-testid="stAppViewContainer"], [data-testid="stSidebar"] { font-size:16px; }
  p, label, [data-testid="stMarkdownContainer"] p { font-size:0.95rem; }
  .section-tag {
    display:inline-block;background:var(--secondary-background-color);color:var(--text-color) !important;
    border:1px solid rgba(120,130,150,0.35);
    font-size:0.76rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;
    padding:0.3rem 0.8rem;border-radius:4px;margin-bottom:1rem;
  }
  .stButton>button {
    background:var(--secondary-background-color);border:1px solid rgba(120,130,150,0.45);
    color:var(--text-color) !important;border-radius:8px;
    min-height:42px;font-weight:600;
  }
  .stButton>button:hover { border-color:var(--primary-color); }
  .stButton>button[kind="primary"] { background:var(--primary-color) !important;border-color:var(--primary-color) !important; color:white !important; }
  [data-testid="stDataFrame"] { border:1px solid rgba(120,130,150,0.45);border-radius:8px; }
  code { background:var(--secondary-background-color) !important; color:var(--text-color) !important; }
  [data-testid="stFileUploader"] {
    border:2px dashed rgba(120,130,150,0.45) !important;border-radius:10px !important;
    padding:1.1rem !important;background:var(--secondary-background-color) !important;
  }
  [data-testid="stFileUploaderDropzone"] { min-height:120px; background:var(--secondary-background-color) !important; border:0 !important; }
  [data-testid="stFileUploaderDropzone"] * { color:var(--text-color) !important; }
  [data-testid="stDownloadButton"]>button {
    background:var(--secondary-background-color) !important;border:1px solid rgba(120,130,150,0.45) !important;color:var(--text-color) !important;
    border-radius:8px !important;min-height:42px;font-weight:600;
  }
  [data-testid="stDownloadButton"]>button:hover { border-color:var(--primary-color) !important; }
  .privacy-box {
    background:var(--secondary-background-color);border:1px solid rgba(120,130,150,0.45);border-radius:8px;
    padding:0.8rem 1.1rem;color:var(--text-color) !important;font-size:0.83rem;line-height:1.7;
    margin-bottom:1rem;
  }
  .guide-box {
    background:var(--secondary-background-color);border:1px solid rgba(120,130,150,0.45);border-radius:8px;
    padding:1rem 1.2rem;color:var(--text-color) !important;font-size:0.85rem;line-height:1.8;margin-bottom:1rem;
  }
  .story-box {
    background:var(--secondary-background-color);border:1px solid rgba(99,102,241,0.45);
    border-left:3px solid #6366f1;border-radius:0 8px 8px 0;
    padding:1rem 1.2rem;color:var(--text-color) !important;font-size:0.87rem;line-height:1.8;margin-bottom:1rem;
  }
  .flow-label {
    color:var(--text-color);opacity:0.72;font-size:0.74rem;font-weight:700;letter-spacing:0.07em;
    text-transform:uppercase;display:block;margin-bottom:0.35rem;margin-top:0.5rem;
  }
  .muted-text { color:var(--text-color);opacity:0.72;font-size:0.85rem; }
  .insight-box {
    background:var(--secondary-background-color);border-left:3px solid #6366f1;border-radius:0 8px 8px 0;
    padding:1rem 1.2rem;color:var(--text-color) !important;line-height:1.8;
  }
</style>
""", unsafe_allow_html=True)

CHART_THEME = dict(template="streamlit",
                   color_sequence=["#6366f1","#06b6d4","#34d399","#f59e0b","#f43f5e","#a78bfa"])

# ── Sample databases ───────────────────────────────────────────────────────────

SAMPLE_DBS = {
    "🛒 E-commerce": {
        "description": "Weekly sales across products, regions, channels + marketing spend",
        "description_zh": "按产品、地区、渠道拆分的周度销售、客户与投放数据",
        "schema": """Tables:
1. orders (order_id, order_date, product, category, region, channel, units, unit_price, revenue, cost, gross_profit)
2. customers (customer_id, order_id, customer_name, segment, country, is_new)  — is_new: 1=new, 0=returning
3. marketing (week, channel, ad_spend, impressions, clicks, conversions)""",
        "questions": [
            "Monthly GMV with trailing 3-month moving average",
            "Month-over-month GMV growth by channel",
            "New vs returning customer GMV and margin by segment",
            "Rank each region's top product by gross profit",
            "Ad spend ROI by channel with revenue joined",
            "Cumulative GMV contribution by category over time",
        ],
        "questions_zh": [
            "按月计算 GMV 和最近 3 个月移动平均",
            "按渠道计算 GMV 环比增长率",
            "按客群对比新客和老客 GMV 与毛利率",
            "找出每个地区毛利最高的产品排名",
            "关联销售和投放计算各渠道广告 ROI",
            "按品类计算累计 GMV 贡献趋势",
        ],
        "setup": """
CREATE TABLE IF NOT EXISTS orders (order_id INTEGER PRIMARY KEY, order_date TEXT, product TEXT, category TEXT, region TEXT, channel TEXT, units INTEGER, unit_price REAL, revenue REAL, cost REAL, gross_profit REAL);
CREATE TABLE IF NOT EXISTS customers (customer_id INTEGER PRIMARY KEY, order_id INTEGER, customer_name TEXT, segment TEXT, country TEXT, is_new INTEGER);
CREATE TABLE IF NOT EXISTS marketing (week TEXT, channel TEXT, ad_spend REAL, impressions INTEGER, clicks INTEGER, conversions INTEGER);
INSERT OR IGNORE INTO orders VALUES
(1,'2024-01-01','Widget A','Electronics','North','Online',120,99.99,11999,7200,4799),
(2,'2024-01-01','Widget B','Electronics','South','Online',80,149.99,11999,8400,3599),
(3,'2024-01-01','Gadget X','Accessories','East','Retail',200,24.99,4998,2500,2498),
(4,'2024-01-01','Gadget Y','Accessories','West','Retail',150,34.99,5249,3000,2249),
(5,'2024-01-08','Widget A','Electronics','North','Online',140,99.99,13999,8400,5599),
(6,'2024-01-08','Widget B','Electronics','South','Retail',60,149.99,8999,6300,2699),
(7,'2024-01-08','Gadget X','Accessories','East','Online',220,24.99,5498,2750,2748),
(8,'2024-01-08','Gadget Y','Accessories','West','Online',130,34.99,4549,2600,1949),
(9,'2024-01-15','Widget A','Electronics','South','Online',160,99.99,15999,9600,6399),
(10,'2024-01-15','Widget B','Electronics','North','Retail',90,149.99,13499,9450,4049),
(11,'2024-01-15','Gadget X','Accessories','West','Retail',180,24.99,4498,2250,2248),
(12,'2024-01-15','Gadget Y','Accessories','East','Online',170,34.99,5949,3400,2549),
(13,'2024-01-22','Widget A','Electronics','East','Online',110,99.99,10999,6600,4399),
(14,'2024-01-22','Widget B','Electronics','West','Online',100,149.99,14999,10500,4499),
(15,'2024-01-22','Gadget X','Accessories','North','Retail',250,24.99,6248,3125,3123),
(16,'2024-01-22','Gadget Y','Accessories','South','Online',190,34.99,6648,3800,2848),
(17,'2024-01-29','Widget A','Electronics','West','Retail',130,99.99,12999,7800,5199),
(18,'2024-01-29','Widget B','Electronics','East','Online',70,149.99,10499,7350,3149),
(19,'2024-01-29','Gadget X','Accessories','South','Online',260,24.99,6497,3248,3249),
(20,'2024-01-29','Gadget Y','Accessories','North','Retail',200,34.99,6998,4000,2998),
(21,'2024-02-05','Widget A','Electronics','North','Online',180,99.99,17998,10800,7198),
(22,'2024-02-05','Widget B','Electronics','South','Retail',95,149.99,14249,9975,4274),
(23,'2024-02-05','Gadget X','Accessories','East','Online',280,24.99,6997,3500,3497),
(24,'2024-02-05','Gadget Y','Accessories','West','Retail',210,34.99,7348,4200,3148),
(25,'2024-03-04','Widget A','Electronics','East','Online',210,99.99,20998,12600,8398),
(26,'2024-03-04','Widget B','Electronics','North','Online',120,149.99,17999,12600,5399),
(27,'2024-03-04','Gadget X','Accessories','South','Retail',300,24.99,7497,3750,3747),
(28,'2024-03-04','Gadget Y','Accessories','West','Online',240,34.99,8398,4800,3598),
(29,'2024-04-01','Widget A','Electronics','South','Retail',190,99.99,18998,11400,7598),
(30,'2024-04-01','Widget B','Electronics','East','Online',145,149.99,21749,15225,6524),
(31,'2024-04-01','Gadget X','Accessories','North','Online',340,24.99,8497,4250,4247),
(32,'2024-04-01','Gadget Y','Accessories','West','Retail',260,34.99,9097,5200,3897),
(33,'2024-05-06','Widget A','Electronics','West','Online',230,99.99,22998,13800,9198),
(34,'2024-05-06','Widget B','Electronics','North','Retail',150,149.99,22499,15750,6749),
(35,'2024-05-06','Gadget X','Accessories','East','Online',380,24.99,9496,4750,4746),
(36,'2024-05-06','Gadget Y','Accessories','South','Online',290,34.99,10147,5800,4347),
(37,'2024-06-03','Widget A','Electronics','North','Online',260,99.99,25997,15600,10397),
(38,'2024-06-03','Widget B','Electronics','East','Retail',170,149.99,25498,17850,7648),
(39,'2024-06-03','Gadget X','Accessories','West','Online',410,24.99,10246,5125,5121),
(40,'2024-06-03','Gadget Y','Accessories','South','Retail',320,34.99,11197,6400,4797);
INSERT OR IGNORE INTO customers VALUES
(1,1,'Acme Corp','Enterprise','US',0),(2,2,'Beta LLC','SMB','US',1),(3,3,'Gamma Inc','Consumer','CA',1),(4,4,'Delta Co','SMB','CA',0),(5,5,'Acme Corp','Enterprise','US',0),(6,6,'Epsilon Ltd','Enterprise','UK',1),(7,7,'Zeta GmbH','SMB','DE',1),(8,8,'Eta SA','Consumer','FR',0),(9,9,'Theta Inc','SMB','US',1),(10,10,'Iota Corp','Enterprise','US',0),(11,11,'Kappa LLC','Consumer','CA',1),(12,12,'Lambda Co','SMB','UK',0),(13,13,'Mu Ltd','Consumer','US',1),(14,14,'Nu Corp','Enterprise','DE',0),(15,15,'Xi Inc','SMB','US',1),(16,16,'Omicron LLC','Consumer','CA',0),(17,17,'Pi Corp','Enterprise','US',1),(18,18,'Rho Ltd','SMB','UK',0),(19,19,'Sigma Inc','Consumer','FR',1),(20,20,'Tau Co','Enterprise','US',0),
(21,21,'Acme Corp','Enterprise','US',0),(22,22,'Beta LLC','SMB','US',0),(23,23,'Upsilon Inc','Consumer','CA',1),(24,24,'Delta Co','SMB','CA',0),(25,25,'Phi GmbH','Enterprise','DE',1),(26,26,'Iota Corp','Enterprise','US',0),(27,27,'Chi SA','Consumer','FR',1),(28,28,'Eta SA','Consumer','FR',0),(29,29,'Theta Inc','SMB','US',0),(30,30,'Psi Ltd','Enterprise','UK',1),(31,31,'Xi Inc','SMB','US',0),(32,32,'Omega LLC','Consumer','CA',1),(33,33,'Pi Corp','Enterprise','US',0),(34,34,'Nu Corp','Enterprise','DE',0),(35,35,'Zeta GmbH','SMB','DE',0),(36,36,'Sigma Inc','Consumer','FR',0),(37,37,'Acme Corp','Enterprise','US',0),(38,38,'Rho Ltd','SMB','UK',0),(39,39,'Lambda Co','SMB','UK',0),(40,40,'Omicron LLC','Consumer','CA',0);
INSERT OR IGNORE INTO marketing VALUES
('2024-01-01','Online',3200,120000,4800,384),('2024-01-01','Retail',1800,0,0,220),('2024-01-08','Online',3500,135000,5400,432),('2024-01-08','Retail',1900,0,0,195),('2024-01-15','Online',3800,150000,6000,510),('2024-01-15','Retail',2000,0,0,240),('2024-01-22','Online',3600,142000,5680,454),('2024-01-22','Retail',1950,0,0,228),('2024-01-29','Online',4000,160000,6400,544),('2024-01-29','Retail',2100,0,0,260),
('2024-02-05','Online',4500,180000,7200,640),('2024-02-05','Retail',2300,0,0,310),('2024-03-04','Online',5200,210000,8400,780),('2024-03-04','Retail',2600,0,0,345),('2024-04-01','Online',5600,230000,9200,830),('2024-04-01','Retail',2800,0,0,370),('2024-05-06','Online',6200,250000,10000,940),('2024-05-06','Retail',3100,0,0,410),('2024-06-03','Online',7000,285000,11400,1080),('2024-06-03','Retail',3500,0,0,460);
""",
    },
    "👥 HR Analytics": {
        "description": "Employee headcount, salaries, tenure, and performance ratings by department",
        "description_zh": "按部门拆分的员工人数、薪资、司龄、绩效与流失数据",
        "schema": """Tables:
1. employees (emp_id, name, department, role, hire_date, salary, tenure_years, performance_score, is_active)
   — performance_score: 1–5, is_active: 1=current, 0=churned""",
        "questions": [
            "Attrition rate by department and salary quartile",
            "Rank roles by pay vs performance efficiency",
            "Active headcount joined each year by department",
            "Departments with high pay but below-average retention",
            "Average tenure gap between active and churned employees",
            "Top performers whose salary is below role average",
        ],
        "questions_zh": [
            "按部门和薪资四分位计算流失率",
            "按薪资与绩效效率对岗位排名",
            "按部门统计每年入职的在职人数",
            "找出高薪但留存低于平均的部门",
            "对比在职与流失员工的平均司龄差",
            "找出薪资低于岗位平均的高绩效员工",
        ],
        "setup": """
CREATE TABLE IF NOT EXISTS employees (emp_id INTEGER PRIMARY KEY, name TEXT, department TEXT, role TEXT, hire_date TEXT, salary REAL, tenure_years REAL, performance_score REAL, is_active INTEGER);
INSERT OR IGNORE INTO employees VALUES
(1,'Alice Chen','Engineering','Senior Engineer','2019-03-01',145000,5.2,4.5,1),
(2,'Bob Zhang','Engineering','Engineer','2021-06-15',105000,2.8,3.8,1),
(3,'Carol Liu','Engineering','Lead Engineer','2017-09-01',168000,6.8,4.8,1),
(4,'David Wang','Product','PM','2020-01-10',130000,4.4,4.2,1),
(5,'Emily Xu','Product','Senior PM','2018-05-20',155000,6.1,4.6,1),
(6,'Frank Li','Marketing','Marketing Manager','2019-11-01',110000,4.6,3.9,1),
(7,'Grace Wu','Marketing','Analyst','2022-03-15',82000,2.2,3.5,1),
(8,'Henry Zhou','Sales','Sales Rep','2021-08-01',75000,2.9,3.2,1),
(9,'Iris Tang','Sales','Senior Sales','2019-02-14',98000,5.3,4.1,1),
(10,'Jack Ma','Sales','Sales Manager','2016-07-01',135000,8.0,4.7,1),
(11,'Karen Ho','HR','HR Manager','2018-04-01',105000,6.2,4.3,1),
(12,'Leo Ng','HR','Recruiter','2022-09-01',72000,1.8,3.6,1),
(13,'Mia Tan','Engineering','Engineer','2020-10-01',108000,3.7,4.0,1),
(14,'Nick Lim','Engineering','Junior Engineer','2023-01-15',88000,1.4,3.4,1),
(15,'Olivia Yeo','Product','PM','2021-03-01',128000,3.3,4.1,1),
(16,'Peter Koh','Sales','Sales Rep','2022-06-01',74000,2.0,2.9,0),
(17,'Queenie Soh','Marketing','Senior Analyst','2020-07-15',95000,4.0,4.2,1),
(18,'Ryan Ong','Engineering','Senior Engineer','2018-12-01',142000,5.6,4.4,1),
(19,'Sara Lau','Sales','Sales Rep','2021-11-01',76000,2.6,3.1,0),
(20,'Tom Phua','Product','Senior PM','2017-05-01',160000,7.1,4.9,1);
""",
    },
    "💰 SaaS Metrics": {
        "description": "Monthly recurring revenue, churn, CAC, and LTV across customer plans",
        "description_zh": "按订阅方案拆分的 MRR、流失、CAC、客服工单与增长数据",
        "schema": """Tables:
1. subscriptions (sub_id, customer, plan, mrr, start_date, end_date, churned, cac, country)
   — mrr in USD, churned: 1=churned, 0=active
2. monthly_metrics (month, plan, new_customers, churned_customers, mrr, support_tickets)""",
        "questions": [
            "Monthly MRR with trailing 3-month moving average",
            "Net new customers and churn rate by plan over time",
            "Plan-level CAC payback using active MRR",
            "Support tickets per $1k MRR by plan",
            "Countries with high MRR but high churn risk",
            "Rank plans by expansion quality and churn pressure",
        ],
        "questions_zh": [
            "按月计算 MRR 和最近 3 个月移动平均",
            "按方案计算净新增客户和流失率趋势",
            "用在订 MRR 计算各方案 CAC 回收期",
            "按方案计算每千美元 MRR 的工单数",
            "找出高 MRR 但高流失风险的国家",
            "按增长质量和流失压力给方案排名",
        ],
        "setup": """
CREATE TABLE IF NOT EXISTS subscriptions (sub_id INTEGER PRIMARY KEY, customer TEXT, plan TEXT, mrr REAL, start_date TEXT, end_date TEXT, churned INTEGER, cac REAL, country TEXT);
CREATE TABLE IF NOT EXISTS monthly_metrics (month TEXT, plan TEXT, new_customers INTEGER, churned_customers INTEGER, mrr REAL, support_tickets INTEGER);
INSERT OR IGNORE INTO subscriptions VALUES
(1,'Acme Inc','Enterprise',2500,'2023-01-01',NULL,0,1200,'US'),
(2,'Beta LLC','Pro',299,'2023-02-01',NULL,0,320,'US'),
(3,'Gamma Co','Starter',49,'2023-01-15','2023-08-15',1,180,'CA'),
(4,'Delta Ltd','Pro',299,'2023-03-01',NULL,0,310,'UK'),
(5,'Echo Corp','Enterprise',2500,'2023-01-01',NULL,0,1150,'US'),
(6,'Foxtrot GmbH','Pro',299,'2023-04-01','2023-11-01',1,340,'DE'),
(7,'Golf SA','Starter',49,'2023-02-15',NULL,0,160,'FR'),
(8,'Hotel Inc','Enterprise',3500,'2023-01-01',NULL,0,1400,'US'),
(9,'India LLC','Pro',299,'2023-05-01',NULL,0,295,'US'),
(10,'Juliet Co','Starter',49,'2023-03-01','2023-09-01',1,175,'CA'),
(11,'Kilo Ltd','Pro',499,'2023-01-01',NULL,0,380,'UK'),
(12,'Lima Corp','Enterprise',2500,'2023-06-01',NULL,0,1100,'AU'),
(13,'Mike Inc','Starter',49,'2023-04-15',NULL,0,155,'US'),
(14,'Nov LLC','Pro',299,'2023-07-01','2023-12-01',1,315,'US'),
(15,'Oscar Co','Enterprise',3500,'2023-02-01',NULL,0,1350,'US'),
(16,'Papa Ltd','Starter',49,'2023-08-01',NULL,0,165,'SG'),
(17,'Quebec Corp','Pro',499,'2023-03-15',NULL,0,390,'CA'),
(18,'Romeo Inc','Starter',49,'2023-09-01','2024-01-01',1,170,'UK'),
(19,'Sierra LLC','Enterprise',2500,'2023-05-01',NULL,0,1250,'US'),
(20,'Tango Co','Pro',299,'2023-10-01',NULL,0,305,'AU');
INSERT OR IGNORE INTO monthly_metrics VALUES
('2023-01','Starter',12,1,588,8),('2023-01','Pro',8,0,2392,12),('2023-01','Enterprise',3,0,8500,5),
('2023-02','Starter',10,2,490,9),('2023-02','Pro',6,1,2093,10),('2023-02','Enterprise',2,0,11000,4),
('2023-03','Starter',14,1,637,11),('2023-03','Pro',9,0,2691,13),('2023-03','Enterprise',1,0,13500,3),
('2023-04','Starter',11,3,539,10),('2023-04','Pro',7,2,2093,11),('2023-04','Enterprise',2,0,16000,4),
('2023-05','Starter',15,1,686,12),('2023-05','Pro',10,1,2990,14),('2023-05','Enterprise',3,0,18500,6),
('2023-06','Starter',13,2,637,9),('2023-06','Pro',8,0,3289,12),('2023-06','Enterprise',2,1,21000,5);
""",
    },
}

# ── Story opener ──────────────────────────────────────────────────────────────

def generate_story_opener(db_key: str, conn, lang: str) -> dict:
    try:
        if "E-commerce" in db_key:
            rev = pd.read_sql_query(
                "SELECT product, SUM(revenue) as rev, SUM(gross_profit) as gp FROM orders GROUP BY product",
                conn,
            )
            rev["margin"] = rev["gp"] / rev["rev"]
            top_rev = rev.loc[rev["rev"].idxmax()]
            top_margin = rev.loc[rev["margin"].idxmax()]
            ch = pd.read_sql_query(
                "SELECT channel, SUM(revenue) as rev FROM orders GROUP BY channel", conn
            )
            ch_ratio = ch.set_index("channel")["rev"]
            online_rev = ch_ratio.get("Online", 0)
            retail_rev = ch_ratio.get("Retail", 0)
            if lang == "中文":
                return {
                    "headline": (
                        f"<b>{top_rev['product']}</b> GMV 最高，达到 "
                        f"${top_rev['rev']:,.0f}；但 <b>{top_margin['product']}</b> 的毛利率为 "
                        f"{top_margin['margin']:.0%}，高出 "
                        f"{(top_margin['margin'] - top_rev['margin']):.0%}。"
                    ),
                    "insight": (
                        f"Online 渠道贡献了总 GMV 的 {online_rev/(online_rev+retail_rev):.0%}。"
                        f"可以继续追问投放 ROI 是否匹配 GMV 贡献。"
                    ),
                    "action": "建议按下方“发现 → 诊断 → 决策”的顺序演示复杂查询。",
                }
            return {
                "headline": (
                    f"<b>{top_rev['product']}</b> leads GMV at "
                    f"${top_rev['rev']:,.0f} — but <b>{top_margin['product']}</b> runs a "
                    f"{top_margin['margin']:.0%} gross margin, "
                    f"{(top_margin['margin'] - top_rev['margin']):.0%} higher."
                ),
                "insight": (
                    f"Online channel drives {online_rev/(online_rev+retail_rev):.0%} of total "
                    f"GMV vs Retail. Are you allocating ad spend to match?"
                ),
                "action": "Try the discovery flow below — each question builds on the last.",
            }
        elif "HR" in db_key:
            attrition = pd.read_sql_query(
                "SELECT department, "
                "SUM(CASE WHEN is_active=0 THEN 1 ELSE 0 END)*1.0/COUNT(*) as rate "
                "FROM employees GROUP BY department ORDER BY rate DESC",
                conn,
            )
            worst = attrition.iloc[0]
            avg_sal = pd.read_sql_query(
                "SELECT department, AVG(salary) as avg_sal FROM employees WHERE is_active=1 "
                "GROUP BY department ORDER BY avg_sal DESC",
                conn,
            ).iloc[0]
            if lang == "中文":
                return {
                    "headline": (
                        f"<b>{worst['department']}</b> 流失率最高，为 "
                        f"{worst['rate']:.0%}；<b>{avg_sal['department']}</b> 的在职员工平均薪资最高，"
                        f"为 ${avg_sal['avg_sal']:,.0f}/年。"
                    ),
                    "insight": "高流失和高薪资如果分布在不同部门，说明薪酬投入和留存效果可能不匹配。",
                    "action": "建议先看部门流失率，再交叉分析薪资、绩效和司龄。",
                }
            return {
                "headline": (
                    f"<b>{worst['department']}</b> has the highest attrition at "
                    f"{worst['rate']:.0%} — while <b>{avg_sal['department']}</b> "
                    f"pays ${avg_sal['avg_sal']:,.0f}/yr on average."
                ),
                "insight": "High attrition + high pay in separate departments signals a misalignment between compensation and retention.",
                "action": "Start with attrition by department, then cross-reference salaries.",
            }
        elif "SaaS" in db_key:
            churn = pd.read_sql_query(
                "SELECT plan, SUM(churned)*1.0/COUNT(*) as rate, COUNT(*) as total "
                "FROM subscriptions GROUP BY plan ORDER BY rate DESC",
                conn,
            )
            worst = churn.iloc[0]
            best_mrr = pd.read_sql_query(
                "SELECT plan, SUM(mrr) as total_mrr FROM subscriptions WHERE churned=0 "
                "GROUP BY plan ORDER BY total_mrr DESC",
                conn,
            ).iloc[0]
            if lang == "中文":
                return {
                    "headline": (
                        f"<b>{worst['plan']}</b> 方案流失率最高，为 {worst['rate']:.0%}；"
                        f"<b>{best_mrr['plan']}</b> 方案贡献了 ${best_mrr['total_mrr']:,.0f}/月的在订 MRR。"
                    ),
                    "insight": "入门方案的高流失会削弱后续升级漏斗，需要判断新增和扩张 MRR 是否覆盖流失。",
                    "action": "建议先比较各方案流失率，再追踪 MRR 的 rolling average 趋势。",
                }
            return {
                "headline": (
                    f"<b>{worst['plan']}</b> plan churn rate is {worst['rate']:.0%} — "
                    f"but <b>{best_mrr['plan']}</b> plan drives ${best_mrr['total_mrr']:,.0f}/mo in active MRR."
                ),
                "insight": "High churn in entry plans erodes the funnel that feeds upgrades. Is expansion MRR outpacing the leakage?",
                "action": "Compare churn rates across plans, then trace MRR trend over time.",
            }
    except Exception:
        pass
    return {}


# ── LLM ───────────────────────────────────────────────────────────────────────

def get_client():
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        st.error("⚠️ API key not configured.")
        st.stop()
    return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

def build_schema_from_df(df: pd.DataFrame, table_name: str = "data") -> str:
    col_info = ", ".join(f"{c} ({df[c].dtype})" for c in df.columns)
    sample = df.head(3).to_string(index=False)
    return f"Table: {table_name} ({col_info})\n\nSample rows:\n{sample}"

def generate_sql(client, question: str, schema: str, table_names: list) -> str:
    tables_hint = ", ".join(table_names)
    system = (
        "You are an expert SQL analyst. Convert the business question to a valid SQLite query.\n\n"
        f"Schema:\n{schema}\n\n"
        f"Available tables: {tables_hint}\n\n"
        "Rules: return ONLY the SQL, no markdown fences, no explanation. "
        "Use CTEs, joins, CASE expressions, date functions, and window functions when the question needs "
        "rolling averages, cumulative totals, rankings, month-over-month changes, or contribution analysis. "
        "Use proper aggregations and ORDER BY. Limit to 20 rows unless asked for all. "
        "Match column names exactly as in the schema."
    )
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": question}],
        temperature=0, max_tokens=800,
    )
    sql = resp.choices[0].message.content.strip()
    sql = re.sub(r"^```(?:sql)?\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\s*```$", "", sql)
    return sql.strip()

def explain_result(client, question: str, sql: str, df: pd.DataFrame, lang: str) -> str:
    preview = df.head(10).to_string(index=False)
    if lang == "中文":
        system = (
            "你是一位面向业务负责人的资深数据分析师。根据问题、SQL 和查询结果，"
            "用中文写一段简洁的 3 句话业务解读。"
            "第 1 句直接给出最重要的数字或发现，必须具体。"
            "第 2 句解释它对业务意味着什么，可以包含原因、对比或上下文。"
            "第 3 句给出下周可以执行的一条具体行动建议。"
            "不要使用 markdown，不要含糊。"
        )
    else:
        system = (
            "You are a senior business analyst presenting to a CMO. Given the question, SQL, and query results, "
            "write a crisp 3-sentence business interpretation. "
            "Sentence 1: Lead with the single most important number or finding — be specific. "
            "Sentence 2: Explain what it means for the business (cause, comparison, or context). "
            "Sentence 3: Give one concrete action the team should take next week based on this data. "
            "No hedging. No markdown. Write in plain business English."
        )
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": f"Question: {question}\n\nSQL:\n{sql}\n\nResults:\n{preview}"}],
        temperature=0.3, max_tokens=300,
    )
    return resp.choices[0].message.content.strip()

def auto_chart(df: pd.DataFrame):
    if df.empty or len(df) < 2:
        return
    num_cols = df.select_dtypes("number").columns.tolist()
    cat_cols = [c for c in df.columns if c not in num_cols]
    if not num_cols:
        return
    y = num_cols[0]
    x = cat_cols[0] if cat_cols else (num_cols[1] if len(num_cols) > 1 else None)
    if not x:
        return
    try:
        kwargs = dict(color_discrete_sequence=CHART_THEME["color_sequence"], template=CHART_THEME["template"])
        fig = (px.bar(df, x=x, y=y, **kwargs) if df[x].nunique() <= 15
               else px.line(df, x=x, y=y, markers=True, **kwargs))
        fig.update_layout(margin=dict(t=30, b=20), height=320)
        st.plotly_chart(fig, use_container_width=True)
    except Exception:
        pass

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    lang = st.radio("语言 / Language", ["English", "中文"], horizontal=True)

    def t(en: str, zh: str) -> str:
        return zh if lang == "中文" else en

    st.markdown(f"### 💬 ChatBI")
    st.divider()
    st.markdown(f"**{t('How it works','工作原理')}**")
    if lang == "中文":
        st.markdown("1. 选择示例数据库或上传自有 CSV\n"
                    "2. AI 编写 SQL 查询\n"
                    "3. 查询在实时内存数据库上运行\n"
                    "4. 结果 + 中文解读")
    else:
        st.markdown("1. Choose a sample database or upload your own CSV\n"
                    "2. AI writes the SQL query\n"
                    "3. Query runs on a live in-memory database\n"
                    "4. Results + plain-English interpretation")
    st.divider()
    st.markdown(f"**{t('Tips for better results','获得更好结果的技巧')}**")
    if lang == "中文":
        st.markdown("- 使用 schema 中的列名\n"
                    "- 指定具体指标：收入、利润率、数量\n"
                    "- 对比效果好：'X vs Y'、'前 5'、'按地区'\n"
                    "- 支持多表联查")
    else:
        st.markdown("- Use column names from the schema\n"
                    "- Ask for specific metrics: revenue, margin, count\n"
                    "- Comparisons work well: 'X vs Y', 'top 5', 'by region'\n"
                    "- Multi-table joins are supported")
    st.divider()
    st.markdown(f"**{t('Business impact','业务价值')}**")
    st.markdown(t("~80% of routine data requests become self-serve. Days → minutes.",
                  "约 80% 的常规数据需求变为自助查询。天级 → 分钟级。"))
    st.divider()
    if st.button(t("Reset","重置"), use_container_width=True):
        for key in [
            "_q_inject",
            "question_input",
            "last_sql",
            "last_df",
            "last_explanation",
            "last_question",
        ]:
            st.session_state.pop(key, None)
        st.rerun()
    st.divider()
    st.markdown(f"{t('Built by','作者')} [Joseph Wang](https://josephjwang.com)")

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown(f"""
<h1 style='background:linear-gradient(90deg,#6366f1,#06b6d4);
-webkit-background-clip:text;-webkit-text-fill-color:transparent;
font-size:2.2rem;font-weight:700;margin-bottom:0.2rem'>💬 ChatBI</h1>
<p style='color:var(--text-color);opacity:0.72;font-size:1rem;margin-bottom:1.5rem'>
{t('Ask any business question → AI writes SQL → live results + interpretation',
   '用自然语言提问 → AI 生成 SQL → 实时结果 + 解读')}</p>
""", unsafe_allow_html=True)

if lang == "中文":
    st.markdown(
        """
<div class="guide-box" style="margin-top:0.2rem">
<b>工作原理</b> — 选择示例数据库，用中文或英文提出业务问题。
AI 生成 SQL 并实时执行，给出带有建议行动的一段解读。
无需 SQL 知识。切换到"上传"模式可在自有 CSV 上运行。<br><br>
<b>建议流程（2–3 分钟）：</b>选择电商数据 → 按下方"发现 → 诊断 → 决策"顺序提问。
</div>
""", unsafe_allow_html=True)
else:
    st.markdown(
        """
<div class="guide-box" style="margin-top:0.2rem">
<b>How it works</b> — Pick a sample database, ask a business question in plain English.
The AI writes the SQL, runs it live, and gives you a one-paragraph interpretation with a recommended action.
No SQL knowledge needed. Switch to Upload mode to run it on your own CSV.<br><br>
<b>Suggested flow (2–3 min):</b> Choose E-commerce → follow the Discover → Diagnose → Decide questions below.
</div>
""", unsafe_allow_html=True)

# ── Step 1: Choose data source ─────────────────────────────────────────────────
st.markdown(f'<span class="section-tag">{t("Step 1 — Choose your data","第 1 步 — 选择数据")}</span>', unsafe_allow_html=True)

mode = st.radio(
    "Data source",
    ["sample", "upload"],
    format_func=lambda value: t("Use a sample database", "使用示例数据库") if value == "sample" else t("Upload my own CSV", "上传自有 CSV"),
    horizontal=True,
    label_visibility="collapsed",
    key="data_source_mode",
)

conn = None
schema_str = ""
table_names = []
sample_questions = []

if mode == "sample":
    db_choice = st.selectbox(
        t("Select a sample database","选择示例数据库"),
        list(SAMPLE_DBS.keys()),
        label_visibility="collapsed",
    )
    db = SAMPLE_DBS[db_choice]
    st.markdown(f"<span class='muted-text'>📊 {db.get('description_zh') if lang == '中文' else db['description']}</span>",
                unsafe_allow_html=True)

    with st.expander(f"📋 {t('View schema','查看 Schema')}"):
        st.code(db["schema"], language="text")

    # Build DB
    cache_key = f"db_v2_{db_choice}"
    if cache_key not in st.session_state:
        c = sqlite3.connect(":memory:", check_same_thread=False)
        c.executescript(db["setup"])
        c.commit()
        st.session_state[cache_key] = c
    conn = st.session_state[cache_key]
    schema_str = db["schema"]
    sample_questions = db.get("questions_zh", db["questions"]) if lang == "中文" else db["questions"]
    # Extract table names from schema
    table_names = re.findall(r"^\d+\.\s+(\w+)", db["schema"], re.MULTILINE)
    # Compute and cache story opener
    story_key = f"{cache_key}_story_{lang}"
    if story_key not in st.session_state:
        st.session_state[story_key] = generate_story_opener(db_choice, conn, lang)
    st.session_state["_current_story"] = st.session_state[story_key]

else:
    # Privacy notice
    if lang == "中文":
        st.markdown("""
    <div class="privacy-box">
    🔒 <b>您的数据完全私密。</b>上传文件仅加载到当前会话的内存数据库中——
    不存储、不记录，除生成 SQL 外不发送至任何服务器。关闭标签页即清除所有数据。
    </div>""", unsafe_allow_html=True)
    else:
        st.markdown("""
    <div class="privacy-box">
    🔒 <b>Your data stays private.</b> Uploaded files are loaded into an in-memory database
    that exists only for your current session — nothing is stored, logged, or sent to any server
    other than the AI model to generate SQL. When you close the tab, all data is gone.
    </div>""", unsafe_allow_html=True)

    # Upload guidelines
    if lang == "中文":
        st.markdown("""
    <div class="guide-box">
    <b>📎 上传须知</b><br>
    • <b>格式：</b>仅支持 CSV（UTF-8 或常见编码）<br>
    • <b>大小：</b>~50 MB / ~50 万行以内效果良好<br>
    • <b>列名：</b>保持简单——不含空格或特殊字符（使用下划线）<br>
    • <b>多文件：</b>上传多个 CSV 以支持跨表查询<br>
    • <b>最适合：</b>交易数据、报表、Excel / Google Sheets / BI 工具导出
    </div>""", unsafe_allow_html=True)
    else:
        st.markdown("""
    <div class="guide-box">
    <b>📎 Upload guidelines</b><br>
    • <b>Format:</b> CSV files only (UTF-8 or common encodings)<br>
    • <b>Size:</b> Up to ~50 MB / ~500k rows work well<br>
    • <b>Column names:</b> Keep them simple — no spaces or special characters (use underscores)<br>
    • <b>Multiple files:</b> Upload several CSVs to enable cross-table queries<br>
    • <b>What works best:</b> Transactional data, reports, exports from Excel / Google Sheets / BI tools
    </div>""", unsafe_allow_html=True)

    st.session_state["_current_story"] = {}
    uploaded = st.file_uploader(
        t("Upload CSV file(s)","上传 CSV 文件"),
        type=["csv"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if uploaded:
        upload_key = f"upload_{'-'.join(sorted(f.name for f in uploaded))}"
        if upload_key not in st.session_state:
            c = sqlite3.connect(":memory:", check_same_thread=False)
            schemas = []
            tables = []
            for f in uploaded:
                tname = re.sub(r"[^\w]", "_", f.name.rsplit(".", 1)[0]).lower()
                try:
                    df_up = pd.read_csv(f)
                except Exception as e:
                    st.error(f"{t('Failed to parse','解析失败')} `{f.name}`. {t('Please confirm CSV encoding and delimiter. Detail:','请确认 CSV 编码和分隔符。详情：')} {e}")
                    continue
                if df_up.empty:
                    st.warning(t(f"`{f.name}` is empty. Skipped.", f"`{f.name}` 是空文件，已跳过。"))
                    continue
                # Sanitize column names
                df_up.columns = [re.sub(r"[^\w]", "_", col).lower() for col in df_up.columns]
                df_up.to_sql(tname, c, if_exists="replace", index=False)
                tables.append(tname)
                schemas.append(build_schema_from_df(df_up, tname))
                st.success(t(
                    f"Loaded `{tname}` — {len(df_up):,} rows × {len(df_up.columns)} columns",
                    f"已加载 `{tname}` — {len(df_up):,} 行 × {len(df_up.columns)} 列"
                ))
            c.commit()
            if tables:
                st.session_state[upload_key] = c
                st.session_state[f"{upload_key}_schema"] = "\n\n".join(schemas)
                st.session_state[f"{upload_key}_tables"] = tables
            else:
                st.error(t("No valid CSV table loaded. Please upload at least one non-empty CSV.","未加载到有效 CSV 表。请上传至少一个非空 CSV 文件。"))
                conn = None

        if upload_key in st.session_state:
            conn = st.session_state[upload_key]
            schema_str = st.session_state[f"{upload_key}_schema"]
            table_names = st.session_state[f"{upload_key}_tables"]

            with st.expander(f"📋 {t('Detected schema','检测到的 Schema')}"):
                st.code(schema_str, language="text")
        else:
            conn = None
            schema_str = ""
            table_names = []

        # Auto-generate column-aware suggestions once per upload
        sugg_key = f"{upload_key}_suggestions_{lang}"
        if conn is not None and sugg_key not in st.session_state:
            try:
                client = get_client()
                resp = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content":
                            (
                                "You are a data analyst. Given a database schema, suggest exactly 6 short, "
                                "specific business questions a user might ask. Return a JSON array of 6 strings only. "
                                "Each question should be under 12 words. No numbering. "
                                f"Write every question in {'Chinese' if lang == '中文' else 'English'}."
                            )},
                        {"role": "user", "content": f"Schema:\n{schema_str}"}
                    ],
                    temperature=0.3, max_tokens=300,
                )
                raw = resp.choices[0].message.content.strip()
                raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
                raw = re.sub(r"\s*```$", "", raw)
                suggestions = json.loads(raw)
                st.session_state[sugg_key] = suggestions[:6]
            except Exception:
                st.session_state[sugg_key] = (
                    [
                        "按月计算核心指标移动平均",
                        "按分组计算环比增长率",
                        "找出累计贡献最高的类别",
                        "按维度排名并计算占比",
                        "对比高价值和低价值分组",
                        "找出异常波动最大的时间段",
                    ]
                    if lang == "中文"
                    else [
                        "Monthly metrics with moving average",
                        "Month-over-month growth by group",
                        "Categories with highest cumulative contribution",
                        "Rank dimensions and calculate share",
                        "Compare high-value and low-value groups",
                        "Find periods with largest anomalies",
                    ]
                )
        sample_questions = st.session_state[sugg_key] if sugg_key in st.session_state else []
    else:
        st.info(t("⬆ Upload one or more CSV files to get started.","⬆ 上传一个或多个 CSV 文件开始分析。"))

# ── Step 2: Ask ────────────────────────────────────────────────────────────────
if conn is not None:
    st.divider()
    st.markdown(f'<span class="section-tag">{t("Step 2 — Ask a question","第 2 步 — 提问")}</span>', unsafe_allow_html=True)

    # Story opener for sample databases
    story = st.session_state.get("_current_story", {})
    if story:
        st.markdown(
            f"""<div class="story-box">
<b>📊 {t("What this data is telling you","数据在告诉你什么")}</b><br>
{story['headline']}<br><br>
💡 {story['insight']}<br>
🎯 {story['action']}
</div>""",
            unsafe_allow_html=True,
        )

    if sample_questions:
        row1 = sample_questions[:3]
        row2 = sample_questions[3:6]
        st.markdown(f'<span class="flow-label">🔍 {t("Discover — start here","发现 — 从这里开始")}</span>', unsafe_allow_html=True)
        cols = st.columns(3)
        for i, q in enumerate(row1):
            with cols[i]:
                if st.button(q, key=f"sq_{sample_questions.index(q)}", use_container_width=True):
                    st.session_state["_q_inject"] = q
                    st.rerun()
        st.markdown(f'<span class="flow-label">💡 {t("Diagnose & decide","诊断与决策")}</span>', unsafe_allow_html=True)
        cols2 = st.columns(3)
        for i, q in enumerate(row2):
            with cols2[i]:
                if st.button(q, key=f"sq_{sample_questions.index(q)}", use_container_width=True):
                    st.session_state["_q_inject"] = q
                    st.rerun()

    if "_q_inject" in st.session_state:
        st.session_state["question_input"] = st.session_state.pop("_q_inject")

    question = st.text_input(
        t("Ask anything about your data","向数据提任何业务问题"),
        placeholder=t("e.g. Which product has the highest gross profit margin?","例：哪个产品毛利率最高？"),
        key="question_input",
        label_visibility="collapsed",
    )

    col_run, col_clear, _ = st.columns([1, 1, 6])
    with col_run:
        run = st.button(t("Run","运行"), type="primary", disabled=not question, use_container_width=True)
    with col_clear:
        if st.button(t("Clear","清除"), use_container_width=True):
            for k in ["last_sql", "last_df", "last_explanation", "last_question"]:
                st.session_state.pop(k, None)
            st.session_state["_q_inject"] = ""
            st.rerun()

    # ── Execute ────────────────────────────────────────────────────────────────
    if run and question:
        client = get_client()
        with st.spinner(t("Writing SQL…","正在生成 SQL…")):
            try:
                sql = generate_sql(client, question, schema_str, table_names)
                st.session_state["last_sql"] = sql
                st.session_state["last_question"] = question
            except Exception as e:
                st.error(f"{t('SQL generation failed:','SQL 生成失败：')} {e}")
                st.stop()

        with st.spinner(t("Running query…","正在执行查询…")):
            try:
                df_result = pd.read_sql_query(sql, conn)
                st.session_state["last_df"] = df_result
            except Exception as e:
                st.error(f"{t('Query error:','查询错误：')} {e}")
                st.code(sql, language="sql")
                st.stop()

        with st.spinner(t("Interpreting…","正在解读结果…")):
            try:
                explanation = explain_result(client, question, sql, df_result, lang)
                st.session_state["last_explanation"] = explanation
            except Exception:
                st.session_state["last_explanation"] = ""

        st.session_state["_q_inject"] = ""
        st.rerun()

    # ── Results ────────────────────────────────────────────────────────────────
    if "last_df" in st.session_state:
        df = st.session_state["last_df"]
        sql = st.session_state.get("last_sql", "")
        explanation = st.session_state.get("last_explanation", "")

        st.divider()
        st.markdown(f'<span class="section-tag">{t("Step 3 — Generated SQL","第 3 步 — 生成的 SQL")}</span>', unsafe_allow_html=True)
        st.code(sql, language="sql")
        st.caption(t("Read-only analytics intent. If SQL fails, rephrase your question with explicit metric + dimension.",
                     "只读分析意图。如 SQL 执行失败，请用明确的指标 + 维度重新描述问题。"))

        st.markdown(f'<span class="section-tag">{t("Step 4 — Results","第 4 步 — 查询结果")}</span>', unsafe_allow_html=True)
        st.markdown(f"<span class='muted-text'>{len(df):,} {t('rows returned','行结果')}</span>",
                    unsafe_allow_html=True)
        st.dataframe(df, use_container_width=True, height=min(300, 55 + len(df) * 35))
        auto_chart(df)

        if explanation:
            st.markdown(f'<span class="section-tag">{t("Step 5 — Interpretation","第 5 步 — 解读")}</span>', unsafe_allow_html=True)
            st.markdown(
                f"<div class='insight-box'>{explanation}</div>",
                unsafe_allow_html=True,
            )
            key_metric = ""
            if not df.empty:
                first_col = df.columns[0]
                second_col = df.columns[1] if len(df.columns) > 1 else None
                if second_col:
                    key_metric = t(
                        f"Top signal right now: `{df.iloc[0][first_col]}` with `{df.iloc[0][second_col]}`.",
                        f"当前最强信号：`{df.iloc[0][first_col]}` 对应 `{df.iloc[0][second_col]}`。"
                    )
            st.markdown(f'<span class="section-tag">{t("Step 6 — Decision action","第 6 步 — 决策行动")}</span>', unsafe_allow_html=True)
            st.markdown(
                f"<div class='guide-box'><b>{t('Decision memo','决策备忘录')}</b><br>"
                f"{t('Question','问题')}: {st.session_state.get('last_question', 'N/A')}<br>"
                f"{key_metric if key_metric else t('Use the top row result as your primary evidence.','以首行结果作为主要证据。')}<br>"
                f"{t('Suggested next move: assign one owner and one timeline to this insight in the next ops meeting.','建议下一步：在下次运营会议中为此洞察分配负责人和时间线。')}</div>",
                unsafe_allow_html=True,
            )

        st.divider()
        csv_bytes = df.to_csv(index=False).encode()
        st.download_button(t("⬇ Download results as CSV","⬇ 下载结果为 CSV"), csv_bytes, "results.csv", "text/csv")
