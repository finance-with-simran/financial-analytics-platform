"""
Financial Analytics Platform — Streamlit Dashboard
SQL star schema (MySQL) -> 34 analytical queries -> interactive web dashboard.
Companies: AAPL, MSFT, JPM | 15 yrs prices | 10 yrs fundamentals | DCF valuation.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ----------------------------- PAGE SETUP -----------------------------
st.set_page_config(
    page_title="Financial Analytics Platform",
    page_icon="💹",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----------------------------- CONSTANTS -----------------------------
DCF_GROWTH = {"AAPL": 6.0, "MSFT": 10.0, "JPM": 5.0}      # % FCF growth (Q32)
BASE_WACC = 9.0                                            # % discount rate
TERMINAL_G = 2.5                                           # % perpetual growth
SHARES_M = {"AAPL": 15000, "MSFT": 7430, "JPM": 2800}      # shares out (millions)
Q33_INTRINSIC = {"AAPL": 135.20, "MSFT": 267.90, "JPM": 58.02}  # SQL-verified
FCF_FALLBACK = {"JPM": 8533.0}  # Q32: JPM 2025 FCF negative -> median used
COLORS = {"AAPL": "#A2AAAD", "MSFT": "#0078D4", "JPM": "#003087"}
RISK_FREE = 4.5  # % used for Sharpe ratio

# ----------------------------- DATA LOADING -----------------------------
@st.cache_data(show_spinner="Loading warehouse data...")
def load_data():
    companies = pd.read_csv("data/companies.csv")
    prices = pd.read_csv("data/prices.csv", parse_dates=["trade_date"])
    fundamentals = pd.read_csv("data/fundamentals.csv")
    return companies, prices, fundamentals

try:
    companies, prices, fundamentals = load_data()
except FileNotFoundError as e:
    st.error(f"Data file not found: {e.filename}. Make sure data/companies.csv, "
             "data/prices.csv and data/fundamentals.csv are in the repo.")
    st.stop()

ticker_map = dict(zip(companies["company_id"], companies["ticker"]))
name_map = dict(zip(companies["ticker"], companies["company_name"]))
prices["ticker"] = prices["company_id"].map(ticker_map)
fundamentals["ticker"] = fundamentals["company_id"].map(ticker_map)
prices = prices.sort_values(["ticker", "trade_date"]).reset_index(drop=True)

# ----------------------------- KPI HELPERS -----------------------------
def latest_price(tkr):
    df = prices[prices.ticker == tkr]
    return float(df.close_price.iloc[-1]), df.trade_date.iloc[-1]

def annualized_return(tkr):
    df = prices[prices.ticker == tkr]
    years = (df.trade_date.iloc[-1] - df.trade_date.iloc[0]).days / 365.25
    cagr = (df.close_price.iloc[-1] / df.close_price.iloc[0]) ** (1 / years) - 1
    return cagr * 100

def risk_metrics(tkr):
    df = prices[prices.ticker == tkr].copy()
    ret = df.close_price.pct_change().dropna()
    vol = ret.std() * np.sqrt(252) * 100
    sharpe = (annualized_return(tkr) - RISK_FREE) / vol if vol else np.nan
    roll_max = df.close_price.cummax()
    drawdown = (df.close_price / roll_max - 1).min() * 100
    return vol, sharpe, drawdown

def kpi_card(label, value, sub=""):
    st.markdown(
        f"<div style='background:#0e1117;padding:14px 18px;border-radius:10px;"
        f"border-left:4px solid #21c7c7;'><span style='color:#8b93a1;"
        f"font-size:0.8rem;'>{label}</span><div style='font-size:1.5rem;"
        f"font-weight:700;color:#ffffff;'>{value}</div>"
        f"<div style='color:#8b93a1;font-size:0.75rem;'>{sub}</div></div>",
        unsafe_allow_html=True,
    )

# ----------------------------- SIDEBAR -----------------------------
st.sidebar.title("💹 Financial Analytics Platform")
st.sidebar.caption("SQL warehouse → analytics → valuation")
page = st.sidebar.radio(
    "Navigate", ["📈 Trading Charts", "📊 Fundamentals",
                 "⚠️ Risk Metrics", "💰 DCF Valuation", "🛠 Project Story"])
st.sidebar.markdown("---")
st.sidebar.info("Built with MySQL · SQL (34 analytical queries) · "
                 "Power BI · Streamlit · Python")
tkr = st.sidebar.selectbox("Company", ["AAPL", "MSFT", "JPM"],
                           format_func=lambda t: f"{t} — {name_map.get(t, '')}")

# ----------------------------- PAGE 1: TRADING CHARTS -----------------------------
if page == "📈 Trading Charts":
    st.title(f"📈 {tkr} — {name_map.get(tkr, '')}")
    px, dt = latest_price(tkr)
    vol, sharpe, dd = risk_metrics(tkr)
    st.caption(f"15 years of daily prices · latest close {dt:%d %b %Y}")

c1, c2, c3, c4 = st.columns(4)
    with c1: kpi_card("Latest Close", f"\${px:,.2f}", name_map.get(tkr, ""))
    with c2: kpi_card("15Y CAGR", f"{annualized_return(tkr):.1f}%", "price growth p.a.")
    with c3: kpi_card("Annual Volatility", f"{vol:.1f}%", "std of daily returns × √252")
    with c4: kpi_card("Max Drawdown", f"{dd:.1f}%", "worst peak-to-trough")

df = prices[prices.ticker == tkr].copy()
    df["sma50"] = df.close_price.rolling(50).mean()
    df["sma200"] = df.close_price.rolling(200).mean()
    fig = make_subplots(shared_xaxes=True, row_heights=[0.75, 0.25],
                        vertical_spacing=0.03, rows=2, cols=1)
    fig.add_trace(go.Candlestick(x=df.trade_date, open=df.open_price,
                                 high=df.high_price, low=df.low_price,
                                 close=df.close_price, name="OHLC",
                                 increasing_line_color="#26a69a",
                                 decreasing_line_color="#ef5350"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.trade_date, y=df.sma50, name="SMA 50",
                             line=dict(color="#ffb74d", width=1.2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.trade_date, y=df.sma200, name="SMA 200",
                             line=dict(color="#64b5f6", width=1.2)), row=1, col=1)
    fig.add_trace(go.Bar(x=df.trade_date, y=df.volume, name="Volume",
                         marker_color="#5c6bc0", opacity=0.6), row=2, col=1)
    fig.update_layout(height=620, xaxis_rangeslider_visible=False,
                      legend=dict(orientation="h", y=1.06),
                      margin=dict(l=10, r=10, t=30, b=10),
                      paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                      font=dict(color="#e8eaed"))
    fig.update_yaxes(gridcolor="#1f2733")
    fig.update_xaxes(gridcolor="#1f2733")
    st.plotly_chart(fig, use_container_width=True)
    st.markdown("**Trend read:** SMA 50 above SMA 200 = golden-cross uptrend; "
                "the opposite signals weakness. Volume spikes mark institutional "
                "activity (earnings, macro events).")

# ----------------------------- PAGE 2: FUNDAMENTALS -----------------------------
elif page == "📊 Fundamentals":
    st.title(f"📊 {tkr} — 10 Years of Fundamentals")
    f = fundamentals[fundamentals.ticker == tkr].sort_values("fiscal_year")

t1, t2, t3 = st.columns(3)
    last = f.iloc[-1]
    with t1: kpi_card("Revenue (latest FY)", f"\${last.revenue:,.0f}M", "net sales")
    with t2: kpi_card("Net Income (latest FY)", f"\${last.net_income:,.0f}M",
                      f"margin {100*last.net_income/last.revenue:.1f}%")
    with t3: kpi_card("Free Cash Flow (latest FY)",
                      f"\${last.free_cash_flow:,.0f}M", "cash the DCF runs on")

fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=f.fiscal_year, y=f.revenue, name="Revenue",
                         marker_color=COLORS[tkr], opacity=0.85), secondary_y=False)
    fig.add_trace(go.Scatter(x=f.fiscal_year, y=f.net_income, name="Net Income",
                             line=dict(color="#ffb74d", width=3)), secondary_y=True)
    fig.add_trace(go.Scatter(x=f.fiscal_year, y=f.free_cash_flow, name="Free Cash Flow",
                             line=dict(color="#66bb6a", width=3)), secondary_y=True)
    fig.update_layout(height=480, barmode="group", hovermode="x unified",
                      legend=dict(orientation="h", y=1.15),
                      paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                      font=dict(color="#e8eaed"))
    fig.update_yaxes(gridcolor="#1f2733")
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Full fundamentals table (from fact_fundamentals)")
    st.dataframe(f[["fiscal_year", "revenue", "net_income", "free_cash_flow"]]
                 .set_index("fiscal_year").style.format("{:,.0f}"),
                 use_container_width=True)

# ----------------------------- PAGE 3: RISK -----------------------------
elif page == "⚠️ Risk Metrics":
    st.title("⚠️ Risk–Return Dashboard (Q11 · Q14 · Q15 · Q28 · Q29)")
    rows = []
    for t in ["AAPL", "MSFT", "JPM"]:
        v, s, d = risk_metrics(t)
        px, _ = latest_price(t)
        rows.append({"Ticker": t, "Close": px, "15Y CAGR %": annualized_return(t),
                     "Volatility %": v, "Sharpe": s, "Max Drawdown %": d,
                     "Market Cap \$B": px * SHARES_M[t] / 1000})
    tbl = pd.DataFrame(rows).set_index("Ticker")
    st.dataframe(tbl.style.format("{:,.2f}"), use_container_width=True)

fig = go.Figure()
    for t in ["AAPL", "MSFT", "JPM"]:
        df = prices[prices.ticker == t].copy()
        df["dd"] = (df.close_price / df.close_price.cummax() - 1) * 100
        fig.add_trace(go.Scatter(x=df.trade_date, y=df.dd, name=t,
                                 line=dict(color=COLORS[t], width=1.4)))
    fig.update_layout(height=420, yaxis_title="Drawdown %",
                      title="Underwater curve — every 0% peak is an all-time high",
                      paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                      font=dict(color="#e8eaed"),
                      legend=dict(orientation="h", y=1.15))
    fig.update_yaxes(gridcolor="#1f2739")
    st.plotly_chart(fig, use_container_width=True)
    st.info(f"Sharpe = (CAGR − {RISK_FREE}% risk-free) ÷ volatility. "
            "Correlation between the three names' daily returns was computed in "
            "SQL (Q28) — see queries.sql in the GitHub repo.")

# ----------------------------- PAGE 4: DCF -----------------------------
elif page == "💰 DCF Valuation":
    st.title("💰 DCF Valuation — 10-Year Intrinsic Value Model")
    st.caption("Engine mirrors SQL queries Q31–Q34: FCF projection → "
               "discount at WACC → terminal value → value per share.")

f = fundamentals[fundamentals.ticker == tkr].sort_values("fiscal_year")
    base_fcf = float(f.free_cash_flow.iloc[-1])
    if base_fcf <= 0:
        base_fcf = FCF_FALLBACK[tkr]
        st.warning(f"Latest FCF was negative — using median FCF "
                   f"\${base_fcf:,.0f}M as base (same assumption as SQL Q32).")

c1, c2, c3 = st.columns(3)
    with c1:
        g = st.slider("FCF growth, Years 1–10 (%)", 0.0, 15.0,
                      DCF_GROWTH[tkr], 0.5, key=f"g_{tkr}")
    with c2:
        wacc = st.slider("WACC / discount rate (%)", 5.0, 15.0, BASE_WACC, 0.5,
                         key=f"w_{tkr}")
    with c3:
        gt = st.slider("Terminal growth (%)", 0.5, 5.0, TERMINAL_G, 0.5,
                       key=f"t_{tkr}")

# ---- DCF engine (same math as SQL Q32/Q33) ----
    years = np.arange(1, 11)
    fcf_proj = base_fcf * (1 + g / 100) ** years
    disc = (1 + wacc / 100) ** years
    pv_explicit = float((fcf_proj / disc).sum())

if wacc / 100 <= gt / 100:
        st.error("WACC must be higher than terminal growth — the "
                 "Gordon Growth formula divides by (WACC − g).")
        st.stop()
    tv = fcf_proj[-1] * (1 + gt / 100) / ((wacc - gt) / 100)
    pv_tv = float(tv / disc[-1])
    equity_value = pv_explicit + pv_tv
    per_share = equity_value / SHARES_M[tkr]

market, mkt_date = latest_price(tkr)
    upside = (per_share / market - 1) * 100
    q33 = Q33_INTRINSIC[tkr]

k1, k2, k3, k4 = st.columns(4)
    with k1: kpi_card("DCF Value / Share", f"\${per_share:,.2f}", "your slider inputs")
    with k2: kpi_card("Market Price", f"\${market:,.2f}", f"as of {mkt_date:%d %b %Y}")
    with k3: kpi_card("Upside / Downside", f"{upside:+.1f}%", "DCF vs market")
    with k4: kpi_card("SQL Benchmark (Q33)", f"\${q33:,.2f}",
                      "growth / 9% WACC / 2.5% terminal")

verdict = "UNDERVALUED ⬆️" if upside > 15 else \
              "OVERVALUED ⬇️" if upside < -15 else "FAIRLY VALUED ➡️"
    if abs(per_share - q33) < 0.01:
        st.success(f"**Verdict: {verdict}** — slider inputs match the SQL "
                   "model exactly. Play with the sliders to see how "
                   "sensitive the verdict is.")
    else:
        st.info(f"**Verdict: {verdict}** — you moved the assumptions away "
                "from the SQL baseline (Q33). This is DCF sensitivity in "
                "action: change WACC or growth and the verdict can flip.")

st.subheader("Projected Free Cash Flow (10-year explicit forecast)")
    fig = go.Figure(go.Bar(x=years, y=fcf_proj, name="Projected FCF",
                           marker_color=COLORS[tkr], opacity=0.85))
    fig.add
    fig = go.Figure()
    fig.add_trace(go.Bar(x=years, y=fcf_proj, name="Projected FCF",
                         marker_color=COLORS[tkr], opacity=0.85))
    fig.add_trace(go.Scatter(x=years, y=fcf_proj / disc, name="PV of FCF",
                             line=dict(color="#ffb74d", width=3)))
    fig.update_layout(height=380, xaxis_title="Forecast year",
                      yaxis_title="$ millions", barmode="group",
                      hovermode="x unified",
                      paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                      font=dict(color="#e8eaed"))
    fig.update_yaxes(gridcolor="#1f2733")
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Sensitivity — DCF value per share vs WACC & growth")
    waccs = [7.0, 8.0, 9.0, 10.0]
    grows = np.arange(0.0, 12.1, 2.0)
    matrix = []
    for gg in grows:
        row = []
        for ww in waccs:
            proj = base_fcf * (1 + gg / 100) ** years
            d2 = (1 + ww / 100) ** years
            pv = (proj / d2).sum() + proj[-1] * (1 + gt / 100) / \
                 ((ww - gt) / 100) / d2[-1]
            row.append(pv / SHARES_M[tkr])
        matrix.append(row)
    sens = pd.DataFrame(matrix, index=[f"{gg:.0f}%" for gg in grows],
                        columns=[f"WACC {ww:.0f}%" for ww in waccs])
    st.dataframe(sens.style.format("${:,.2f}").background_gradient(
        cmap="RdYlGn"), use_container_width=True)
    st.caption("Green = higher intrinsic value. Find the combination where "
               f"the cell exceeds the market price (${market:,.2f}) — that's "
               "the bull case.")

# ----------------------------- PAGE 5: PROJECT STORY -----------------------------
else:
    st.title("🛠️ How This Project Was Built")
    st.markdown("""
    **Pipeline:** raw market CSVs → **MySQL star schema** (`dim_companies`,
    `fact_prices`, `fact_fundamentals`) → **34 analytical SQL queries**
    (window functions, recursive CTEs, CAGR math) → **Power BI** report →
    **this Streamlit dashboard** (Python / Pandas / Plotly).

**Data:** 15 years of daily OHLCV prices (~11,900 rows) + 10 years of
    fundamentals (FY2016–FY2025) for Apple, Microsoft and JPMorgan.

**The DCF tab** reproduces the SQL valuation (Q31–Q34) interactively:
    10-year FCF projection, discounting at WACC, Gordon Growth terminal
    value — with live sliders and a sensitivity matrix.

**Headline result (SQL-verified):** under conservative assumptions
    (growth AAPL 6% / MSFT 10% / JPM 5%, WACC 9%, terminal growth 2.5%),
    intrinsic values were AAPL $135.20, MSFT $267.90, JPM $58.02 —
    all below market prices, demonstrating DCF sensitivity.

*Educational/portfolio project — not investment advice.*
    """)
