# 💹 Financial Analytics Platform

**An end-to-end financial analytics pipeline: raw stock & fundamentals data → MySQL warehouse (star schema) → 30 analytical SQL queries → interactive Power BI dashboard.**

Analyzing 15 years of daily price history and 10 years of financial fundamentals for **Apple (AAPL)**, **Microsoft (MSFT)**, and **JPMorgan Chase (JPM)**.

---

## 📖 Table of Contents
1. [Project Overview](#-project-overview)
2. [Data Source](#-data-source)
3. [Database Design (Star Schema)]#️⃣
4. [The 30 SQL Queries](#-the-30-sql-queries)
5. [Power BI Dashboard](#-power-bi-dashboard)
6. [Tech Stack](#-tech-stack)
7. [Repository Structure](#-repository-structure)
8. [How to Reproduce This Project](#-how-to-reproduce-this-project)
9. [Key Learnings](#-key-learnings)
10. [Future Enhancements](#-future-enhancements)

---

## 📊 Project Overview

This project answers the question every investor cares about — **"Which of these companies is the strongest investment, and how risky is it?"** — using real data, not opinions.

The pipeline has 4 stages:

| Stage | Tool | Output |
|---|---|---|
| 1. Data Collection | Stooq (free historical CSV downloads) + company filings | Raw daily prices & annual fundamentals |
| 2. Data Storage | MySQL 8.0 (star schema design) | `finance_platform` warehouse (~11,900 price rows) |
| 3. Analysis | 30 SQL queries (CTEs, window functions, aggregations) | Returns, volatility, valuation, risk metrics |
| 4. Visualization | Power BI | Interactive multi-page dashboard |

---

## 🌐 Data Source

| Data | Source | Coverage |
|---|---|---|
| Daily stock prices (OHLCV) | [Stooq](https://stooq.com) — free CSV exports | 2011 – 2026, ~15 years per company |
| Annual fundamentals (revenue, net income, free cash flow) | Company annual reports | FY2016 – FY2025 |

**Companies covered:** AAPL (Technology), MSFT (Technology), JPM (Financials)

---

## #️⃣ Database Design (Star Schema)

A classic star schema — one dimension table at the center of two fact tables, connected by foreign keys:

```
                    ┌──────────────────┐
                    │   dim_companies  │
                    │──────────────────│
                    │ company_id (PK)  │
                    │ ticker           │
                    │ company_name     │
                    │ sector           │
                    │ exchange         │
                    │ currency         │
                    └───────┬──────────┘
                            │
              ┌─────────────┴──────────────┐
              │ 1:N                        │ 1:N
   ┌──────────▼───────────┐      ┌──────────▼───────────┐
   │     fact_prices      │      │  fact_fundamentals   │
   │──────────────────────│      │──────────────────────│
   │ price_id (PK)        │      │ fund_id (PK)         │
   │ company_id (FK)      │      │ company_id (FK)      │
   │ trade_date           │      │ fiscal_year          │
   │ open_price           │      │ revenue              │
   │ high_price           │      │ net_income           │
   │ low_price            │      │ free_cash_flow       │
   │ close_price          │      │                      │
   │ adj_close_price      │      │                      │
   │ volume               │      │                      │
   │ UNIQUE(company_id,   │      │ UNIQUE(company_id,   │
   │        trade_date)   │      │        fiscal_year)  │
   └──────────────────────┘      └──────────────────────┘
```

Full DDL is in [`schema.sql`](schema.sql).

---

## 🔍 The 30 SQL Queries

All queries live in [`queries.sql`](queries.sql), grouped into 5 analytical themes:

| # | Queries | Theme | Sample Insights |
|---|---|---|---|
| 1 | Q1–Q5 | Data overview & returns | Total return over 15 years, yearly performance |
| 2 | Q6–Q10 | Business health | Revenue growth YoY, net margin, 5-year CAGR, free cash flow quality |
| 3 | Q11–Q15 | Volatility & risk | Annualized volatility, golden/death cross, max drawdown, Sharpe ratio |
| 4 | Q16–Q22 | Monthly & volume analysis | Monthly seasonality, volume spikes, high-volume vs normal-day returns |
| 5 | Q23–Q30 | Prices + fundamentals | Market cap, P/E ratio, return correlations, full company scorecard |

**SQL techniques used:** CTEs (`WITH`), window functions (`LAG`, `AVG OVER`, `MAX OVER`, `ROW_NUMBER`), subqueries, `CASE` logic, `DATE_FORMAT`, `POW`/`SQRT` (CAGR & annualization math), `STDDEV_POP` (risk metrics).

**The grand finale (Q30)** combines everything into a single company scorecard: latest price, net margin, FCF margin, and revenue CAGR — one row per company.

---

## 📈 Power BI Dashboard

The dashboard (`Financial_Analytics_Platform.pbix`) connects **live** to the MySQL warehouse and visualizes:

- 📉 **15-year price history** — interactive line chart for all 3 stocks
- 📊 **Fundamentals** — revenue, net income, and free cash flow trends
- ⚠️ **Risk metrics** — volatility and drawdown comparisons
- 🎯 **Scorecard** — the executive summary view

Dashboard screenshots are in the repo for a quick preview.

---

## 🛠️ Tech Stack

| Tool | Role |
|---|---|
| **MySQL 8.0** | Data warehouse (star schema, InnoDB, foreign keys) |
| **MySQL Workbench** | Schema design & query development |
| **Power BI Desktop** | Live connection to MySQL, dashboard & DAX measures |
| **SQL (MySQL dialect)** | All analytical logic — 30 production-ready queries |
| **GitHub** | Version control & portfolio showcase |

---

## 📁 Repository Structure

```
financial-analytics-platform/
│
├── README.md                          ← you are here
├── schema.sql                         ← DDL: database, tables, keys
├── queries.sql                        ← 30 analytical queries
├── Financial_Analytics_Platform.pbix  ← Power BI dashboard
└── screenshots/                       ← dashboard preview images
```

---

## 🚀 How to Reproduce This Project

1. **Create the warehouse** — run `schema.sql` in MySQL (creates `finance_platform` + 3 tables).
2. **Load data** — download CSVs from Stooq, clean them, and load into `fact_prices` and `fact_fundamentals` (INSERTs in `schema.sql` include the 30 fundamentals rows).
3. **Run the analysis** — execute `queries.sql` (all 30 queries are runnable top to bottom).
4. **Connect Power BI** — install *MySQL Connector/NET*, then in Power BI: Get Data → MySQL → Server `localhost`, Database `finance_platform`, credentials `root` → load the 3 tables.
5. **Build visuals** — line charts (price trends), card KPIs, slicers by ticker/date.

---

## 🌟 Key Learnings

- Designed a **star schema** from scratch and understood why it beats flat tables for analytics.
- Learned to write **window functions** to compute returns, moving averages, and drawdowns without leaving SQL.
- Learned how **volatility, Sharpe ratio, and max drawdown** actually quantify risk — not just "the price went up."
- Connected Power BI to a **live MySQL database** instead of importing static files.
- Learned that data quality (adjusted prices, unique keys) matters more than the visualization on top.

---

## 🔮 Future Enhancements

- Add more tickers (5–10 stocks across more sectors) for a true comparison universe
- Build an equal-weighted **portfolio backtest** and compare against the S&P 500
- Add monthly **DAX measures** in Power BI (dynamic Sharpe ratio, drawdown slicers)
- Automate data refresh via Python ETL script + scheduled load

---

## ⚠️ Disclaimer

This project is for **educational and portfolio purposes only**. Historical performance does not guarantee future results, and nothing here is investment advice.

---

## 🙋♀️ About

Built from scratch by **Syeda** — data collection, database design, SQL analysis, and dashboarding. Connect with me on GitHub!
