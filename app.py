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
  .stButton>button * { color:inherit !important; }
  .stButton>button:hover { border-color:var(--primary-color); }
  .stButton>button[kind="primary"] {
    background:#2563eb !important;border-color:#1d4ed8 !important;color:#ffffff !important;
    box-shadow:0 1px 2px rgba(37,99,235,0.25);
  }
  .stButton>button:disabled {
    background:rgba(120,130,150,0.16) !important;border-color:rgba(120,130,150,0.35) !important;
    color:rgba(120,130,150,0.95) !important;opacity:1 !important;
  }
  [data-testid="stTextInput"] input {
    background:var(--secondary-background-color) !important;
    color:var(--text-color) !important;
    border:1px solid rgba(120,130,150,0.55) !important;
    border-radius:8px !important;
    caret-color:var(--primary-color) !important;
  }
  [data-testid="stTextInput"] input::placeholder { color:var(--text-color) !important; opacity:0.62 !important; }
  [data-testid="stTextInput"] input:focus {
    border-color:#2563eb !important;
    box-shadow:0 0 0 1px #2563eb !important;
  }
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
        "description": "Weekly sales, customers, marketing, inventory, product margin, and returns",
        "description_zh": "销售、客户、投放、库存、商品毛利和退款退货数据",
        "scenario": "GMV is growing, but leadership needs to know whether profit is leaking through discounts, refunds, ad spend, or stockouts.",
        "scenario_zh": "GMV 在增长，但管理层想知道利润是否被折扣、退款、投放和缺货吃掉。",
        "schema": """Tables:
1. orders (order_id, order_date, product, category, region, channel, units, unit_price, revenue, cost, gross_profit)
2. customers (customer_id, order_id, customer_name, segment, country, is_new)  — is_new: 1=new, 0=returning
3. marketing (week, channel, ad_spend, impressions, clicks, conversions)
4. products (product, category, supplier, launch_date, list_price, target_margin)
5. inventory (month, product, beginning_stock, ending_stock, stockouts)
6. returns (return_id, order_id, return_date, reason, refund_amount)
7. promotions (campaign_id, campaign_name, product, channel, start_date, end_date, discount_pct, promo_spend)
8. monthly_targets (month, category, target_gmv, target_gross_profit)""",
        "questions": [
            "Monthly GMV with trailing 3-month moving average",
            "Month-over-month GMV growth by channel",
            "New vs returning customer GMV and margin by segment",
            "Promotion lift after discounts and refunds",
            "GMV target attainment after stockouts",
            "Net profit by category after refunds, promo spend, and ad spend",
        ],
        "questions_zh": [
            "按月计算 GMV 和最近 3 个月移动平均",
            "按渠道计算 GMV 环比增长率",
            "按客群对比新客和老客 GMV 与毛利率",
            "扣除折扣和退款后分析促销提升",
            "分析缺货后的 GMV 目标达成率",
            "按品类计算扣除退款、促销和投放后的净利润",
        ],
        "setup": """
CREATE TABLE IF NOT EXISTS orders (order_id INTEGER PRIMARY KEY, order_date TEXT, product TEXT, category TEXT, region TEXT, channel TEXT, units INTEGER, unit_price REAL, revenue REAL, cost REAL, gross_profit REAL);
CREATE TABLE IF NOT EXISTS customers (customer_id INTEGER PRIMARY KEY, order_id INTEGER, customer_name TEXT, segment TEXT, country TEXT, is_new INTEGER);
CREATE TABLE IF NOT EXISTS marketing (week TEXT, channel TEXT, ad_spend REAL, impressions INTEGER, clicks INTEGER, conversions INTEGER);
CREATE TABLE IF NOT EXISTS products (product TEXT PRIMARY KEY, category TEXT, supplier TEXT, launch_date TEXT, list_price REAL, target_margin REAL);
CREATE TABLE IF NOT EXISTS inventory (month TEXT, product TEXT, beginning_stock INTEGER, ending_stock INTEGER, stockouts INTEGER);
CREATE TABLE IF NOT EXISTS returns (return_id INTEGER PRIMARY KEY, order_id INTEGER, return_date TEXT, reason TEXT, refund_amount REAL);
CREATE TABLE IF NOT EXISTS promotions (campaign_id INTEGER PRIMARY KEY, campaign_name TEXT, product TEXT, channel TEXT, start_date TEXT, end_date TEXT, discount_pct REAL, promo_spend REAL);
CREATE TABLE IF NOT EXISTS monthly_targets (month TEXT, category TEXT, target_gmv REAL, target_gross_profit REAL);
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
INSERT OR IGNORE INTO products VALUES
('Widget A','Electronics','Northstar Supply','2023-08-01',99.99,0.42),
('Widget B','Electronics','Apex Components','2023-10-15',149.99,0.36),
('Gadget X','Accessories','BrightWorks','2023-06-01',24.99,0.48),
('Gadget Y','Accessories','BrightWorks','2023-09-20',34.99,0.44);
INSERT OR IGNORE INTO inventory VALUES
('2024-01','Widget A',920,690,0),('2024-01','Widget B',620,430,1),('2024-01','Gadget X',1500,390,0),('2024-01','Gadget Y',1180,340,0),
('2024-02','Widget A',690,510,0),('2024-02','Widget B',430,335,2),('2024-02','Gadget X',390,110,3),('2024-02','Gadget Y',340,130,1),
('2024-03','Widget A',720,510,0),('2024-03','Widget B',520,400,0),('2024-03','Gadget X',900,600,0),('2024-03','Gadget Y',620,380,0),
('2024-04','Widget A',510,320,1),('2024-04','Widget B',400,255,0),('2024-04','Gadget X',600,260,0),('2024-04','Gadget Y',380,120,2),
('2024-05','Widget A',650,420,0),('2024-05','Widget B',500,350,1),('2024-05','Gadget X',800,420,0),('2024-05','Gadget Y',720,430,0),
('2024-06','Widget A',420,160,2),('2024-06','Widget B',350,180,1),('2024-06','Gadget X',420,10,4),('2024-06','Gadget Y',430,110,2);
INSERT OR IGNORE INTO returns VALUES
(1,2,'2024-01-05','Defective',149.99),(2,7,'2024-01-12','Late delivery',49.98),(3,14,'2024-01-28','Wrong item',149.99),
(4,22,'2024-02-12','Defective',299.98),(5,25,'2024-03-10','Buyer remorse',99.99),(6,28,'2024-03-16','Damaged package',69.98),
(7,30,'2024-04-08','Defective',299.98),(8,32,'2024-04-12','Late delivery',104.97),(9,35,'2024-05-12','Wrong item',74.97),
(10,37,'2024-06-08','Defective',199.98),(11,39,'2024-06-10','Damaged package',124.95),(12,40,'2024-06-16','Buyer remorse',69.98);
INSERT OR IGNORE INTO promotions VALUES
(1,'New Year Electronics Push','Widget A','Online','2024-01-01','2024-01-31',0.08,2400),
(2,'Retail Bundle Week','Gadget Y','Retail','2024-02-01','2024-02-29',0.12,1300),
(3,'Spring Accessory Boost','Gadget X','Online','2024-03-01','2024-03-31',0.10,1800),
(4,'April Electronics Promo','Widget B','Online','2024-04-01','2024-04-30',0.15,2600),
(5,'May Loyalty Offer','Widget A','Online','2024-05-01','2024-05-31',0.06,2100),
(6,'June Clearance','Gadget X','Online','2024-06-01','2024-06-30',0.18,3000);
INSERT OR IGNORE INTO monthly_targets VALUES
('2024-01','Electronics',112000,42000),('2024-01','Accessories',52000,23000),
('2024-02','Electronics',36000,12500),('2024-02','Accessories',17000,7000),
('2024-03','Electronics',39000,14500),('2024-03','Accessories',16500,7300),
('2024-04','Electronics',42000,15500),('2024-04','Accessories',19000,8200),
('2024-05','Electronics',46000,17000),('2024-05','Accessories',21000,9000),
('2024-06','Electronics',52000,19000),('2024-06','Accessories',24000,10200);
""",
    },
    "👥 HR Analytics": {
        "description": "Employee, department budget, performance review, engagement, and retention data",
        "description_zh": "员工、部门预算、绩效复评、敬业度和留存风险数据",
        "scenario": "The company is growing headcount, but wants to identify regrettable attrition and decide who needs a retention offer first.",
        "scenario_zh": "公司在扩张团队，但需要识别可惜流失，并决定哪些高价值员工要优先留才。",
        "schema": """Tables:
1. employees (emp_id, name, department, role, hire_date, salary, tenure_years, performance_score, is_active)
   — performance_score: 1–5, is_active: 1=current, 0=churned
2. departments (department, business_unit, annual_budget, headcount_target)
3. performance_reviews (review_id, emp_id, review_date, manager_rating, promotion_ready, flight_risk)
4. engagement_surveys (survey_id, emp_id, survey_date, engagement_score, workload_score)
5. terminations (emp_id, termination_date, exit_reason, regrettable)
6. compensation_benchmarks (role, market_midpoint, market_p75)""",
        "questions": [
            "Attrition rate by department and salary quartile",
            "Departments over budget with below-average engagement",
            "Regrettable attrition by department and exit reason",
            "High performers below market pay with high flight risk",
            "Workload and engagement drivers of regrettable attrition",
            "Retention save list ranked by performance, pay gap, and flight risk",
        ],
        "questions_zh": [
            "按部门和薪资四分位计算流失率",
            "找出超预算且敬业度低于平均的部门",
            "按部门和离职原因分析可惜流失",
            "找出低于市场薪资且高流失风险的高绩效员工",
            "分析工作量和敬业度对可惜流失的影响",
            "按绩效、薪资差距和流失风险生成留才名单",
        ],
        "setup": """
CREATE TABLE IF NOT EXISTS employees (emp_id INTEGER PRIMARY KEY, name TEXT, department TEXT, role TEXT, hire_date TEXT, salary REAL, tenure_years REAL, performance_score REAL, is_active INTEGER);
CREATE TABLE IF NOT EXISTS departments (department TEXT PRIMARY KEY, business_unit TEXT, annual_budget REAL, headcount_target INTEGER);
CREATE TABLE IF NOT EXISTS performance_reviews (review_id INTEGER PRIMARY KEY, emp_id INTEGER, review_date TEXT, manager_rating REAL, promotion_ready INTEGER, flight_risk TEXT);
CREATE TABLE IF NOT EXISTS engagement_surveys (survey_id INTEGER PRIMARY KEY, emp_id INTEGER, survey_date TEXT, engagement_score REAL, workload_score REAL);
CREATE TABLE IF NOT EXISTS terminations (emp_id INTEGER PRIMARY KEY, termination_date TEXT, exit_reason TEXT, regrettable INTEGER);
CREATE TABLE IF NOT EXISTS compensation_benchmarks (role TEXT PRIMARY KEY, market_midpoint REAL, market_p75 REAL);
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
INSERT OR IGNORE INTO departments VALUES
('Engineering','Product & Tech',1250000,7),('Product','Product & Tech',650000,4),('Marketing','Growth',360000,3),('Sales','Revenue',460000,5),('HR','Operations',220000,2);
INSERT OR IGNORE INTO performance_reviews VALUES
(1,1,'2024-01-15',4.6,1,'Medium'),(2,2,'2024-01-15',3.7,0,'Low'),(3,3,'2024-01-15',4.9,1,'Low'),(4,4,'2024-01-15',4.2,1,'Medium'),
(5,5,'2024-01-15',4.7,1,'Low'),(6,6,'2024-01-15',3.8,0,'Medium'),(7,7,'2024-01-15',3.4,0,'High'),(8,8,'2024-01-15',3.0,0,'High'),
(9,9,'2024-01-15',4.0,0,'Medium'),(10,10,'2024-01-15',4.8,1,'Low'),(11,11,'2024-01-15',4.2,0,'Low'),(12,12,'2024-01-15',3.5,0,'Medium'),
(13,13,'2024-01-15',4.1,0,'Low'),(14,14,'2024-01-15',3.3,0,'Medium'),(15,15,'2024-01-15',4.0,0,'Medium'),(16,16,'2024-01-15',2.8,0,'High'),
(17,17,'2024-01-15',4.3,1,'Medium'),(18,18,'2024-01-15',4.5,1,'High'),(19,19,'2024-01-15',3.0,0,'High'),(20,20,'2024-01-15',4.9,1,'Low');
INSERT OR IGNORE INTO engagement_surveys VALUES
(1,1,'2024-02-01',4.2,3.8),(2,2,'2024-02-01',3.6,4.1),(3,3,'2024-02-01',4.6,4.0),(4,4,'2024-02-01',4.0,3.7),
(5,5,'2024-02-01',4.5,3.6),(6,6,'2024-02-01',3.4,4.4),(7,7,'2024-02-01',2.9,4.7),(8,8,'2024-02-01',2.8,4.5),
(9,9,'2024-02-01',3.5,4.2),(10,10,'2024-02-01',4.4,3.5),(11,11,'2024-02-01',4.1,3.2),(12,12,'2024-02-01',3.7,3.9),
(13,13,'2024-02-01',3.9,4.0),(14,14,'2024-02-01',3.2,4.3),(15,15,'2024-02-01',3.8,3.8),(16,16,'2024-02-01',2.6,4.8),
(17,17,'2024-02-01',4.0,4.1),(18,18,'2024-02-01',3.3,4.7),(19,19,'2024-02-01',2.7,4.6),(20,20,'2024-02-01',4.7,3.4);
INSERT OR IGNORE INTO terminations VALUES
(16,'2024-03-31','Compensation',1),
(19,'2024-04-15','Manager fit',1);
INSERT OR IGNORE INTO compensation_benchmarks VALUES
('Senior Engineer',150000,168000),('Engineer',112000,126000),('Lead Engineer',172000,190000),
('PM',132000,148000),('Senior PM',162000,180000),('Marketing Manager',116000,130000),
('Analyst',86000,96000),('Senior Analyst',102000,115000),('Sales Rep',80000,91000),
('Senior Sales',104000,118000),('Sales Manager',142000,158000),('HR Manager',110000,124000),
('Recruiter',76000,86000),('Junior Engineer',90000,100000);
""",
    },
    "💰 SaaS Metrics": {
        "description": "Subscriptions, accounts, product usage, invoices, churn, CAC, and support data",
        "description_zh": "订阅、账户画像、产品使用、账单、流失、CAC 和客服数据",
        "scenario": "MRR is expanding, but the team needs to find accounts where low usage, contraction, late payment, or poor health puts revenue at risk.",
        "scenario_zh": "MRR 在增长，但团队需要找出低使用率、收缩、逾期付款或健康分低导致收入有风险的客户。",
        "schema": """Tables:
1. subscriptions (sub_id, customer, plan, mrr, start_date, end_date, churned, cac, country)
   — mrr in USD, churned: 1=churned, 0=active
2. monthly_metrics (month, plan, new_customers, churned_customers, mrr, support_tickets)
3. accounts (customer, segment, industry, seats, account_owner)
4. product_usage (month, customer, active_users, seats_used, ai_queries, dashboards_created)
5. invoices (invoice_id, customer, invoice_month, amount, paid_on_time)
6. mrr_movements (month, customer, starting_mrr, expansion_mrr, contraction_mrr, churn_mrr)
7. health_scores (month, customer, health_score, risk_reason)""",
        "questions": [
            "Monthly MRR with trailing 3-month moving average",
            "Net new customers and churn rate by plan over time",
            "NRR by segment with expansion and contraction",
            "Usage decline and health score churn risk",
            "Late payment, low usage, and high support risk accounts",
            "Customer save list ranked by MRR at risk",
        ],
        "questions_zh": [
            "按月计算 MRR 和最近 3 个月移动平均",
            "按方案计算净新增客户和流失率趋势",
            "按客群计算包含扩张和收缩的 NRR",
            "分析使用率下降和健康分带来的流失风险",
            "找出逾期、低使用、高工单风险账户",
            "按风险 MRR 生成客户挽留名单",
        ],
        "setup": """
CREATE TABLE IF NOT EXISTS subscriptions (sub_id INTEGER PRIMARY KEY, customer TEXT, plan TEXT, mrr REAL, start_date TEXT, end_date TEXT, churned INTEGER, cac REAL, country TEXT);
CREATE TABLE IF NOT EXISTS monthly_metrics (month TEXT, plan TEXT, new_customers INTEGER, churned_customers INTEGER, mrr REAL, support_tickets INTEGER);
CREATE TABLE IF NOT EXISTS accounts (customer TEXT PRIMARY KEY, segment TEXT, industry TEXT, seats INTEGER, account_owner TEXT);
CREATE TABLE IF NOT EXISTS product_usage (month TEXT, customer TEXT, active_users INTEGER, seats_used INTEGER, ai_queries INTEGER, dashboards_created INTEGER);
CREATE TABLE IF NOT EXISTS invoices (invoice_id INTEGER PRIMARY KEY, customer TEXT, invoice_month TEXT, amount REAL, paid_on_time INTEGER);
CREATE TABLE IF NOT EXISTS mrr_movements (month TEXT, customer TEXT, starting_mrr REAL, expansion_mrr REAL, contraction_mrr REAL, churn_mrr REAL);
CREATE TABLE IF NOT EXISTS health_scores (month TEXT, customer TEXT, health_score INTEGER, risk_reason TEXT);
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
INSERT OR IGNORE INTO accounts VALUES
('Acme Inc','Strategic','FinTech',120,'Nina'),('Beta LLC','SMB','E-commerce',12,'Owen'),('Gamma Co','SMB','Education',5,'Owen'),('Delta Ltd','Mid-Market','Healthcare',28,'Priya'),
('Echo Corp','Strategic','Manufacturing',140,'Nina'),('Foxtrot GmbH','Mid-Market','SaaS',24,'Priya'),('Golf SA','SMB','Retail',6,'Owen'),('Hotel Inc','Strategic','FinTech',180,'Nina'),
('India LLC','SMB','Marketing',14,'Owen'),('Juliet Co','SMB','Education',4,'Owen'),('Kilo Ltd','Mid-Market','Healthcare',36,'Priya'),('Lima Corp','Strategic','Logistics',95,'Nina'),
('Mike Inc','SMB','Retail',5,'Owen'),('Nov LLC','SMB','Marketing',11,'Owen'),('Oscar Co','Strategic','Manufacturing',160,'Nina'),('Papa Ltd','SMB','E-commerce',7,'Owen'),
('Quebec Corp','Mid-Market','SaaS',42,'Priya'),('Romeo Inc','SMB','Education',5,'Owen'),('Sierra LLC','Strategic','FinTech',110,'Nina'),('Tango Co','Mid-Market','Logistics',30,'Priya');
INSERT OR IGNORE INTO product_usage VALUES
('2023-04','Acme Inc',101,96,9100,48),('2023-05','Acme Inc',98,92,8700,45),('2023-06','Acme Inc',92,88,8200,42),
('2023-04','Beta LLC',9,8,780,7),('2023-05','Beta LLC',8,7,700,6),('2023-06','Beta LLC',7,6,640,5),
('2023-04','Gamma Co',3,3,220,2),('2023-05','Gamma Co',2,1,120,1),('2023-06','Gamma Co',1,1,55,1),
('2023-04','Delta Ltd',18,16,1800,12),('2023-05','Delta Ltd',19,17,1950,13),('2023-06','Delta Ltd',20,18,2100,14),
('2023-04','Echo Corp',102,94,8600,46),('2023-05','Echo Corp',106,98,9100,49),('2023-06','Echo Corp',110,102,9600,51),
('2023-04','Foxtrot GmbH',12,10,820,8),('2023-05','Foxtrot GmbH',8,6,460,4),('2023-06','Foxtrot GmbH',5,4,210,2),
('2023-04','Golf SA',4,3,240,2),('2023-05','Golf SA',4,3,250,2),('2023-06','Golf SA',4,3,260,2),
('2023-04','Hotel Inc',138,132,12400,60),('2023-05','Hotel Inc',145,139,13200,64),('2023-06','Hotel Inc',152,146,14000,68),
('2023-04','India LLC',8,7,760,5),('2023-05','India LLC',9,8,840,6),('2023-06','India LLC',10,9,950,7),
('2023-04','Juliet Co',3,2,160,1),('2023-05','Juliet Co',2,1,90,1),('2023-06','Juliet Co',1,1,45,0),
('2023-06','Kilo Ltd',31,28,3300,18),('2023-06','Lima Corp',72,66,6900,36),('2023-06','Mike Inc',3,2,180,1),('2023-06','Nov LLC',2,2,95,1),
('2023-06','Oscar Co',132,121,11800,58),('2023-06','Papa Ltd',5,4,310,3),('2023-06','Quebec Corp',35,33,4100,22),('2023-06','Romeo Inc',1,1,30,0),
('2023-06','Sierra LLC',82,75,7400,39),('2023-06','Tango Co',22,19,2400,12);
INSERT OR IGNORE INTO invoices VALUES
(1,'Acme Inc','2023-06',2500,1),(2,'Beta LLC','2023-06',299,1),(3,'Gamma Co','2023-06',49,0),(4,'Delta Ltd','2023-06',299,1),
(5,'Echo Corp','2023-06',2500,1),(6,'Foxtrot GmbH','2023-06',299,0),(7,'Golf SA','2023-06',49,1),(8,'Hotel Inc','2023-06',3500,1),
(9,'India LLC','2023-06',299,1),(10,'Juliet Co','2023-06',49,0),(11,'Kilo Ltd','2023-06',499,1),(12,'Lima Corp','2023-06',2500,1),
(13,'Mike Inc','2023-06',49,1),(14,'Nov LLC','2023-06',299,0),(15,'Oscar Co','2023-06',3500,1),(16,'Papa Ltd','2023-06',49,1),
(17,'Quebec Corp','2023-06',499,1),(18,'Romeo Inc','2023-06',49,0),(19,'Sierra LLC','2023-06',2500,1),(20,'Tango Co','2023-06',299,1);
INSERT OR IGNORE INTO mrr_movements VALUES
('2023-06','Acme Inc',2500,300,0,0),('2023-06','Beta LLC',299,0,50,0),('2023-06','Gamma Co',49,0,0,49),('2023-06','Delta Ltd',299,60,0,0),
('2023-06','Echo Corp',2500,500,0,0),('2023-06','Foxtrot GmbH',299,0,120,0),('2023-06','Golf SA',49,0,0,0),('2023-06','Hotel Inc',3500,700,0,0),
('2023-06','India LLC',299,80,0,0),('2023-06','Juliet Co',49,0,0,49),('2023-06','Kilo Ltd',499,100,0,0),('2023-06','Lima Corp',2500,250,0,0),
('2023-06','Mike Inc',49,0,0,0),('2023-06','Nov LLC',299,0,90,0),('2023-06','Oscar Co',3500,600,0,0),('2023-06','Papa Ltd',49,0,0,0),
('2023-06','Quebec Corp',499,120,0,0),('2023-06','Romeo Inc',49,0,0,49),('2023-06','Sierra LLC',2500,300,0,0),('2023-06','Tango Co',299,0,40,0);
INSERT OR IGNORE INTO health_scores VALUES
('2023-06','Acme Inc',78,'Usage decline'),('2023-06','Beta LLC',62,'Seat underuse'),('2023-06','Gamma Co',31,'Low usage and late payment'),('2023-06','Delta Ltd',82,'Healthy'),
('2023-06','Echo Corp',91,'Expansion ready'),('2023-06','Foxtrot GmbH',38,'Usage collapse'),('2023-06','Golf SA',70,'Stable'),('2023-06','Hotel Inc',94,'Expansion ready'),
('2023-06','India LLC',83,'Healthy'),('2023-06','Juliet Co',28,'Low usage and late payment'),('2023-06','Kilo Ltd',86,'Healthy'),('2023-06','Lima Corp',88,'Healthy'),
('2023-06','Mike Inc',66,'Low depth'),('2023-06','Nov LLC',35,'Late payment and low usage'),('2023-06','Oscar Co',92,'Expansion ready'),('2023-06','Papa Ltd',72,'Stable'),
('2023-06','Quebec Corp',89,'Expansion ready'),('2023-06','Romeo Inc',24,'Churned'),('2023-06','Sierra LLC',81,'Healthy'),('2023-06','Tango Co',58,'Seat underuse');
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

def generate_sql(client, question: str, schema: str, table_names: list, business_context: str = "") -> str:
    tables_hint = ", ".join(table_names)
    context_block = f"\nBusiness context and metric definitions:\n{business_context}\n" if business_context else ""
    system = (
        "You are an expert SQL analyst. Convert the business question to a valid SQLite query.\n\n"
        f"Schema:\n{schema}\n\n"
        f"Available tables: {tables_hint}\n\n"
        f"{context_block}"
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

def explain_result(client, question: str, sql: str, df: pd.DataFrame, lang: str, business_context: str = "") -> str:
    preview = df.head(10).to_string(index=False)
    context_block = f"\n\nBusiness context and metric definitions:\n{business_context}" if business_context else ""
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
                  {"role": "user", "content": f"Question: {question}\n\nSQL:\n{sql}\n\nResults:\n{preview}{context_block}"}],
        temperature=0.3, max_tokens=300,
    )
    return resp.choices[0].message.content.strip()

def auto_chart(df: pd.DataFrame):
    if df.empty or len(df) < 2:
        return None
    num_cols = df.select_dtypes("number").columns.tolist()
    cat_cols = [c for c in df.columns if c not in num_cols]
    if not num_cols:
        return None
    y = num_cols[0]
    x = cat_cols[0] if cat_cols else (num_cols[1] if len(num_cols) > 1 else None)
    if not x:
        return None
    try:
        kwargs = dict(color_discrete_sequence=CHART_THEME["color_sequence"], template=CHART_THEME["template"])
        fig = (px.bar(df, x=x, y=y, **kwargs) if df[x].nunique() <= 15
               else px.line(df, x=x, y=y, markers=True, **kwargs))
        fig.update_layout(margin=dict(t=30, b=20), height=320)
        st.plotly_chart(fig, use_container_width=True)
        return fig
    except Exception:
        return None

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
            "business_context_notes",
            "knowledge_docs",
            "suggestion_refresh_id",
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
business_context = ""

if mode == "sample":
    db_choice = st.selectbox(
        t("Select a sample database","选择示例数据库"),
        list(SAMPLE_DBS.keys()),
        label_visibility="collapsed",
    )
    db = SAMPLE_DBS[db_choice]
    st.markdown(f"<span class='muted-text'>📊 {db.get('description_zh') if lang == '中文' else db['description']}</span>",
                unsafe_allow_html=True)
    st.markdown(
        f"<div class='guide-box'><b>{t('Demo scenario','演示场景')}</b><br>"
        f"{db.get('scenario_zh') if lang == '中文' else db.get('scenario', '')}</div>",
        unsafe_allow_html=True,
    )

    with st.expander(f"📋 {t('View schema','查看 Schema')}"):
        st.code(db["schema"], language="text")

    # Build DB
    cache_key = f"db_v4_{db_choice}"
    if cache_key not in st.session_state:
        c = sqlite3.connect(":memory:", check_same_thread=False)
        c.executescript(db["setup"])
        c.commit()
        st.session_state[cache_key] = c
    conn = st.session_state[cache_key]
    schema_str = db["schema"]
    business_context = db.get("scenario_zh") if lang == "中文" else db.get("scenario", "")
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
    • <b>CSV 内容：</b>一行一条记录，第一行必须是列名；适合订单、客户、账单、工单、员工、产品使用等结构化表<br>
    • <b>CSV 大小：</b>建议单个文件 ≤ 50 MB，行数 ≤ 50 万；列名尽量使用英文、数字、下划线<br>
    • <b>多文件：</b>可以上传多个 CSV；如果需要跨表查询，请确保有可关联字段，例如 customer_id、order_id、month<br>
    • <b>知识文档：</b>可上传 .txt / .md，建议单个 ≤ 2 MB，用来说明业务背景、指标口径、字段含义、表关联规则<br>
    • <b>目的：</b>让 AI 不只看到 schema，还能理解 GMV、留存、流失风险、净收入等业务定义
    </div>""", unsafe_allow_html=True)
    else:
        st.markdown("""
    <div class="guide-box">
    <b>📎 Upload guidelines</b><br>
    • <b>CSV content:</b> One record per row, first row as headers; best for orders, customers, invoices, tickets, employees, or usage tables<br>
    • <b>CSV size:</b> Recommended ≤ 50 MB and ≤ 500k rows per file; keep column names simple with letters, numbers, and underscores<br>
    • <b>Multiple files:</b> Upload several CSVs for joins; include join keys such as customer_id, order_id, or month<br>
    • <b>Knowledge docs:</b> Optional .txt / .md files, recommended ≤ 2 MB each, for business context, metric definitions, field meanings, and join rules<br>
    • <b>Purpose:</b> Help AI understand business definitions like GMV, retention, churn risk, and net revenue beyond the schema
    </div>""", unsafe_allow_html=True)

    st.markdown(f"**{t('Business context / knowledge base','业务上下文 / 知识库')}**")
    with st.expander(t("What should I write here?","这里应该填什么？"), expanded=False):
        if lang == "中文":
            st.markdown(
                "- **业务目标：** 例如提升净收入、降低流失、找出库存缺口\n"
                "- **指标口径：** 例如 GMV = revenue - refund_amount，NRR = (starting_mrr + expansion - contraction - churn) / starting_mrr\n"
                "- **字段含义：** 例如 paid_on_time = 1 表示按时付款，health_score < 50 表示高风险\n"
                "- **关联规则：** 例如 orders.order_id = customers.order_id，usage.customer = subscriptions.customer"
            )
        else:
            st.markdown(
                "- **Business goal:** e.g. improve net revenue, reduce churn, find inventory gaps\n"
                "- **Metric definitions:** e.g. GMV = revenue - refund_amount, NRR = (starting_mrr + expansion - contraction - churn) / starting_mrr\n"
                "- **Field meanings:** e.g. paid_on_time = 1 means paid on time, health_score < 50 means high risk\n"
                "- **Join rules:** e.g. orders.order_id = customers.order_id, usage.customer = subscriptions.customer"
            )
    business_notes = st.text_area(
        t("Describe the business problem, KPI definitions, and join rules",
          "填写业务问题、指标口径和表关联规则"),
        placeholder=t(
            "Example: GMV = revenue - refund_amount. Active customer = is_active = 1. Join orders to customers by order_id.",
            "例：GMV = revenue - refund_amount；活跃客户 = is_active = 1；orders 和 customers 通过 order_id 关联。"
        ),
        height=130,
        key="business_context_notes",
        label_visibility="collapsed",
    )
    knowledge_files = st.file_uploader(
        t("Optional: upload business docs (.txt / .md, max 2 MB each)",
          "可选：上传业务说明文档（.txt / .md，单个最大 2 MB）"),
        type=["txt", "md"],
        accept_multiple_files=True,
        key="knowledge_docs",
    )
    doc_parts = []
    for doc in knowledge_files:
        if getattr(doc, "size", 0) > 2 * 1024 * 1024:
            st.warning(t(f"`{doc.name}` is larger than 2 MB and was skipped.",
                         f"`{doc.name}` 超过 2 MB，已跳过。"))
            continue
        doc_text = doc.getvalue().decode("utf-8", errors="replace").strip()
        if doc_text:
            doc_parts.append(f"Document: {doc.name}\n{doc_text[:8000]}")
    business_context = "\n\n".join(part for part in [business_notes.strip(), *doc_parts] if part)
    if business_context:
        st.caption(t(
            f"Knowledge context ready: {len(business_context):,} characters from notes and docs.",
            f"业务上下文已就绪：来自输入和文档的 {len(business_context):,} 个字符。"
        ))
    else:
        st.info(t(
            "Optional but recommended: add KPI definitions and join rules so generated SQL matches your business logic.",
            "可选但建议填写：加入指标口径和表关联规则，生成的 SQL 会更符合真实业务逻辑。"
        ))
    if st.button(t("Refresh suggested questions from context","根据业务上下文刷新建议问题"), use_container_width=True):
        st.session_state["suggestion_refresh_id"] = st.session_state.get("suggestion_refresh_id", 0) + 1
        st.rerun()

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
            table_summaries = []
            for f in uploaded:
                if getattr(f, "size", 0) > 50 * 1024 * 1024:
                    st.warning(t(f"`{f.name}` is larger than 50 MB and was skipped.",
                                 f"`{f.name}` 超过 50 MB，已跳过。"))
                    continue
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
                table_summaries.append({
                    "table": tname,
                    "rows": len(df_up),
                    "columns": len(df_up.columns),
                })
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
                st.session_state[f"{upload_key}_summary"] = table_summaries
            else:
                st.error(t("No valid CSV table loaded. Please upload at least one non-empty CSV.","未加载到有效 CSV 表。请上传至少一个非空 CSV 文件。"))
                conn = None

        if upload_key in st.session_state:
            conn = st.session_state[upload_key]
            schema_str = st.session_state[f"{upload_key}_schema"]
            table_names = st.session_state[f"{upload_key}_tables"]
            table_summaries = st.session_state.get(f"{upload_key}_summary", [])

            if table_summaries:
                st.markdown(f"**{t('Loaded tables','已加载表')}**")
                summary_df = pd.DataFrame(table_summaries).rename(columns={
                    "table": t("Table","表名"),
                    "rows": t("Rows","行数"),
                    "columns": t("Columns","列数"),
                })
                st.dataframe(summary_df, use_container_width=True, hide_index=True)

            with st.expander(f"📋 {t('Detected schema','检测到的 Schema')}"):
                st.code(schema_str, language="text")
        else:
            conn = None
            schema_str = ""
            table_names = []

        # Auto-generate column-aware suggestions once per upload
        suggestion_refresh_id = st.session_state.get("suggestion_refresh_id", 0)
        sugg_key = f"{upload_key}_suggestions_{lang}_{suggestion_refresh_id}"
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
                        {"role": "user", "content": f"Schema:\n{schema_str}\n\nBusiness context:\n{business_context}"}
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

    question_placeholder = (
        t("e.g. Calculate monthly net revenue by customer segment using our KPI definitions",
          "例：按照我填写的指标口径，按客户分群计算月度净收入")
        if mode == "upload"
        else t("e.g. Which product has the highest gross profit margin?","例：哪个产品毛利率最高？")
    )
    st.caption(t(
        "Use a suggested question, or ask your own business question in natural language.",
        "可以点击推荐问题，也可以直接用自然语言提出自己的业务问题。"
    ))
    question = st.text_input(
        t("Ask anything about your data","向数据提任何业务问题"),
        placeholder=question_placeholder,
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
                sql = generate_sql(client, question, schema_str, table_names, business_context)
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
                explanation = explain_result(client, question, sql, df_result, lang, business_context)
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
        fig = auto_chart(df)

        key_metric = ""
        if not df.empty:
            first_col = df.columns[0]
            second_col = df.columns[1] if len(df.columns) > 1 else None
            if second_col:
                key_metric = t(
                    f"Top signal right now: `{df.iloc[0][first_col]}` with `{df.iloc[0][second_col]}`.",
                    f"当前最强信号：`{df.iloc[0][first_col]}` 对应 `{df.iloc[0][second_col]}`。"
                )

        if explanation:
            st.markdown(f'<span class="section-tag">{t("Step 5 — Interpretation","第 5 步 — 解读")}</span>', unsafe_allow_html=True)
            st.markdown(
                f"<div class='insight-box'>{explanation}</div>",
                unsafe_allow_html=True,
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
        report_md = f"""# {t('ChatBI Analysis Report','ChatBI 分析报告')}

## {t('Question','问题')}
{st.session_state.get('last_question', 'N/A')}

## {t('Business Interpretation','业务解读')}
{explanation if explanation else t('No interpretation was generated.', '未生成业务解读。')}

## {t('Key Signal','关键信号')}
{key_metric if key_metric else t('Use the top row result as the primary evidence.', '以首行结果作为主要证据。')}

## {t('Generated SQL','生成的 SQL')}
```sql
{sql}
```

## {t('Result Preview','结果预览')}
```csv
{df.head(20).to_csv(index=False)}
```
"""
        st.markdown(f"**{t('Download package','下载结果包')}**")
        download_cols = st.columns(3)
        with download_cols[0]:
            st.download_button(t("Download CSV data","下载 CSV 数据"), csv_bytes, "chatbi_results.csv", "text/csv", use_container_width=True)
        with download_cols[1]:
            st.download_button(
                t("Download analysis report","下载分析总结"),
                report_md.encode("utf-8"),
                "chatbi_analysis_report.md",
                "text/markdown",
                use_container_width=True,
            )
        with download_cols[2]:
            if fig is not None:
                chart_html = fig.to_html(include_plotlyjs="cdn", full_html=True).encode("utf-8")
                st.download_button(
                    t("Download chart HTML","下载图表 HTML"),
                    chart_html,
                    "chatbi_chart.html",
                    "text/html",
                    use_container_width=True,
                )
            else:
                st.button(t("No chart available","暂无图表可下载"), disabled=True, use_container_width=True)
