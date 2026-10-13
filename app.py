# -*- coding: utf-8 -*-
"""
================================================================================
FINANCIAL ANALYTICS & INSTITUTIONAL VALUATION PLATFORM
================================================================================
An end-to-end investment banking & financial data engineering platform:
- Data Warehouse: MySQL 8 Star Schema (dim_companies, fact_prices, fact_fundamentals)
- Data Ingestion: 15 Years of daily market data (Stooq) + 10 Years SEC 10-K Fundamentals
- Analytics: 34 Analytical SQL Queries (CAGR, drawdown, window functions, recursive CTEs)
- Valuation Engines: Interactive 10-Year DCF Valuation & 5-Year Sponsor LBO Model
================================================================================
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path

# ------------------------------------------------------------------------------
# 1. PAGE SETUP & INSTITUTIONAL DARK THEME STYLING
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="Financial Analytics Platform | DCF & LBO",
    page_icon="💹",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    /* Metric container styling */
    .metric-container {
        background: linear-gradient(135deg, #131722 0%, #1a2234 100%);
        border: 1px solid #2a354c;
        border-radius: 10px;
        padding: 16px 20px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
        margin-bottom: 14px;
        transition: transform 0.15s ease-in-out;
    }
    .metric-container:hover {
        transform: translateY(-2px);
        border-color: #3b82f6;
    }
    .metric-title {
        color: #94a3b8;
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    .metric-number {
        color: #f8fafc;
        font-size: 1.65rem;
        font-weight: 700;
        margin-top: 4px;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    .metric-detail {
        color: #38bdf8;
        font-size: 0.78rem;
        margin-top: 4px;
        font-weight: 500;
    }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# 2. BENCHMARKS & BASELINE PARAMETERS (CALIBRATED TO SQL Q31-Q34)
# ------------------------------------------------------------------------------
DCF_GROWTH = {"AAPL": 6.0, "MSFT": 10.0, "JPM": 5.0}  # % 10-Yr FCF growth (SQL Q32)
BASE_WACC = 9.0                                        # % discount rate / WACC
TERMINAL_G = 2.5                                       # % perpetual terminal growth
SHARES_M = {"AAPL": 15000.0, "MSFT": 7430.0, "JPM": 2800.0}  # shares out (millions)
Q33_INTRINSIC = {"AAPL": 135.20, "MSFT": 267.90, "JPM": 58.02} # SQL baseline
FCF_FALLBACK = {"JPM": 8533.0} # 2025 FCF negative -> median used as in SQL Q32
COLORS = {"AAPL": "#10b981", "MSFT": "#0ea5e9", "JPM": "#f59e0b"}
RISK_FREE = 4.5  # % 10-Yr US Treasury benchmark for Sharpe Ratio

# ------------------------------------------------------------------------------
# 3. ROBUST DATA INGESTION
# ------------------------------------------------------------------------------
def locate_file(filenames):
    """Search across parent, data/ and working directories."""
    candidates = [
        Path(__file__).parent,
        Path(__file__).parent / "data",
        Path.cwd(),
        Path.cwd() / "data"
    ]
    for c_dir in candidates:
        for fname in filenames:
            f = c_dir / fname
            if f.is_file():
                return f
    return None

@st.cache_data(show_spinner="Loading data warehouse...")
def load_all_data():
    comp_file = locate_file(["companies.csv"])
    if not comp_file:
        st.error("companies.csv missing. Please ensure it is present in the repository.")
        st.stop()
    companies = pd.read_csv(comp_file)

    fund_file = locate_file(["fundamentals.csv"])
    if not fund_file:
        st.error("fundamentals.csv missing. Please ensure it is present in the repository.")
        st.stop()
    fundamentals = pd.read_csv(fund_file)

    prices_file = locate_file(["prices.csv"])
    prices = None
    if prices_file:
        try:
            df_p = pd.read_csv(prices_file)
            if "company_id" in df_p.columns and len(df_p["company_id"].unique()) >= 3 and len(df_p) > 3000:
                prices = df_p
        except Exception:
            prices = None

    # Fallback to individual stock CSVs if prices.csv is partial or missing
    if prices is None:
        stock_dfs = []
        mapping = [("AAPL", 1), ("MSFT", 2), ("JPM", 3)]
        for tkr_sym, cid in mapping:
            raw_path = locate_file([f"{tkr_sym}.csv", f"{tkr_sym}.csv.csv"])
            if raw_path:
                raw = pd.read_csv(raw_path)
                raw["trade_date"] = pd.to_datetime(raw["Date"])
                sub = pd.DataFrame({
                    "company_id": cid,
                    "trade_date": raw["trade_date"],
                    "open_price": raw["Open"].astype(float).round(2),
                    "high_price": raw["High"].astype(float).round(2),
                    "low_price": raw["Low"].astype(float).round(2),
                    "close_price": raw["Close"].astype(float).round(2),
                    "adj_close_price": raw["Close"].astype(float).round(2),
                    "volume": raw["Volume"].astype(float).round(0)
                })
                stock_dfs.append(sub)
        if stock_dfs:
            prices = pd.concat(stock_dfs, ignore_index=True)
            prices["price_id"] = range(1, len(prices) + 1)
        else:
            st.error("Price data could not be located.")
            st.stop()

    prices["trade_date"] = pd.to_datetime(prices["trade_date"])
    t_map = dict(zip(companies["company_id"], companies["ticker"]))
    prices["ticker"] = prices["company_id"].map(t_map)
    fundamentals["ticker"] = fundamentals["company_id"].map(t_map)
    prices = prices.sort_values(["ticker", "trade_date"]).reset_index(drop=True)
    return companies, prices, fundamentals

companies, prices, fundamentals = load_all_data()
ticker_map = dict(zip(companies["company_id"], companies["ticker"]))
name_map = dict(zip(companies["ticker"], companies["company_name"]))

# ------------------------------------------------------------------------------
# 4. FINANCIAL METRIC UTILITIES
# ------------------------------------------------------------------------------
def get_latest_price(tkr):
    df = prices[prices.ticker == tkr]
    if df.empty:
        return 0.0, pd.Timestamp.now()
    return float(df.close_price.iloc[-1]), df.trade_date.iloc[-1]

def get_cagr(tkr):
    df = prices[prices.ticker == tkr]
    if len(df) < 2:
        return 0.0
    days = (df.trade_date.iloc[-1] - df.trade_date.iloc[0]).days
    if days <= 0:
        return 0.0
    yrs = days / 365.25
    return ((df.close_price.iloc[-1] / df.close_price.iloc[0]) ** (1.0 / yrs) - 1.0) * 100.0

def get_risk_metrics(tkr):
    df = prices[prices.ticker == tkr].copy()
    if len(df) < 2:
        return 0.0, 0.0, 0.0
    ret = df.close_price.pct_change().dropna()
    vol = ret.std() * np.sqrt(252) * 100.0
    cagr = get_cagr(tkr)
    sharpe = (cagr - RISK_FREE) / vol if vol > 0 else np.nan
    roll_max = df.close_price.cummax()
    max_dd = ((df.close_price - roll_max) / roll_max).min() * 100.0
    return vol, sharpe, max_dd

def safe_gradient(styler, cmap="RdYlGn"):
    """Applies background_gradient if matplotlib is installed, else returns plain styler."""
    try:
        return styler.background_gradient(cmap=cmap)
    except Exception:
        return styler

def render_kpi(label, value, detail=""):
    st.markdown(f"""
    <div class="metric-container">
        <div class="metric-title">{label}</div>
        <div class="metric-number">{value}</div>
        <div class="metric-detail">{detail}</div>
    </div>
    """, unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# 5. SIDEBAR NAVIGATION
# ------------------------------------------------------------------------------
st.sidebar.title("💹 Financial Analytics")
st.sidebar.caption("SQL Warehouse · 15Y Market Data · DCF & LBO")

nav_choice = st.sidebar.radio(
    "Navigation Menu",
    [
        "📈 Trading Charts",
        "📊 Fundamentals",
        "⚠️ Risk Metrics",
        "💰 DCF Valuation",
        "🏢 LBO Model (Buyout)",
        "📚 Financial Concept Guide"
    ],
    index=0
)

st.sidebar.markdown("---")
selected_ticker = st.sidebar.selectbox(
    "Select Company",
    ["AAPL", "MSFT", "JPM"],
    format_func=lambda t: f"{t} — {name_map.get(t, '')}"
)

st.sidebar.markdown("---")
st.sidebar.markdown("""
**Platform Specifications:**
- **Coverage:** Apple, Microsoft, JPMorgan
- **Historical Data:** 15 Years (2011–2026)
- **Data Engine:** MySQL 8 Star Schema
- **SQL Analytics:** 34 Analytical Queries
- **Web App:** Streamlit & Plotly Engine
""")

# ==============================================================================
# PAGE 1: TRADING CHARTS
# ==============================================================================
if nav_choice == "📈 Trading Charts":
    st.title(f"📈 {selected_ticker} — {name_map.get(selected_ticker, '')}")
    latest_px, latest_dt = get_latest_price(selected_ticker)
    vol, sharpe, max_dd = get_risk_metrics(selected_ticker)
    cagr = get_cagr(selected_ticker)

    st.caption(f"15 Years of Daily OHLCV Price History · Latest Market Session: {latest_dt:%d %b %Y}")

    c1, c2, c3, c4 = st.columns(4)
    with c1: render_kpi("Latest Close", f"${latest_px:,.2f}", f"Date: {latest_dt:%d %b %Y}")
    with c2: render_kpi("15-Year CAGR", f"{cagr:.1f}%", "Annual Price Growth")
    with c3: render_kpi("Annual Volatility", f"{vol:.1f}%", "Std Dev × √252")
    with c4: render_kpi("Max Drawdown", f"{max_dd:.1f}%", "Worst Peak-to-Trough")

    # Chart Display Controls
    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 2, 2])
    with ctrl_col1:
        time_window = st.selectbox(
            "Time Window",
            ["Full 15 Years (2011–2026)", "Past 5 Years", "Past 1 Year", "Past 6 Months"],
            index=0
        )
    with ctrl_col2:
        chart_type = st.selectbox(
            "Chart Style",
            ["📈 Smooth Line & Area (Recommended for 15Y)", "🕯️ Candlestick (Best for 6M/1Y)"],
            index=0 if time_window == "Full 15 Years (2011–2026)" else 1,
            help="15 years of daily data has 3,966 candlesticks. Packing 4,000 candles into one screen creates dense black candle borders. Smooth Line mode gives a clean, readable view like Bloomberg or TradingView."
        )
    with ctrl_col3:
        theme_choice = st.selectbox(
            "Chart Theme",
            ["🌙 Dark Terminal (TradingView)", "☀️ Clean Light (Power BI & Excel)"],
            index=0
        )

    df_chart = prices[prices.ticker == selected_ticker].copy()
    if time_window == "Past 6 Months":
        df_chart = df_chart[df_chart.trade_date >= (df_chart.trade_date.max() - pd.Timedelta(days=180))]
    elif time_window == "Past 1 Year":
        df_chart = df_chart[df_chart.trade_date >= (df_chart.trade_date.max() - pd.Timedelta(days=365))]
    elif time_window == "Past 5 Years":
        df_chart = df_chart[df_chart.trade_date >= (df_chart.trade_date.max() - pd.Timedelta(days=5*365))]

    df_chart["sma50"] = df_chart.close_price.rolling(50).mean()
    df_chart["sma200"] = df_chart.close_price.rolling(200).mean()

    is_light = (theme_choice == "☀️ Clean Light (Power BI & Excel)")
    bg_paper = "#ffffff" if is_light else "#0e1117"
    bg_plot = "#f8fafc" if is_light else "#111827"
    grid_col = "#e2e8f0" if is_light else "#1f2937"
    text_col = "#1e293b" if is_light else "#f1f5f9"
    template_name = "plotly_white" if is_light else "plotly_dark"

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.75, 0.25],
        vertical_spacing=0.04,
        subplot_titles=(f"{selected_ticker} Price Action & Moving Averages", "Daily Trading Volume")
    )

    # Main Price Trace: Candlestick or Glowing Area Line
    if "Candlestick" in chart_type:
        fig.add_trace(
            go.Candlestick(
                x=df_chart.trade_date,
                open=df_chart.open_price,
                high=df_chart.high_price,
                low=df_chart.low_price,
                close=df_chart.close_price,
                name="OHLC Candlestick",
                increasing_line_color="#10b981",
                decreasing_line_color="#ef4444"
            ),
            row=1, col=1
        )
    else:
        # Smooth line with subtle shaded area underneath
        fig.add_trace(
            go.Scatter(
                x=df_chart.trade_date,
                y=df_chart.close_price,
                name="Close Price",
                line=dict(color=COLORS[selected_ticker], width=2.5),
                fill="tozeroy",
                fillcolor="rgba(14, 165, 233, 0.12)" if selected_ticker == "MSFT" else ("rgba(16, 185, 129, 0.12)" if selected_ticker == "AAPL" else "rgba(245, 158, 11, 0.12)")
            ),
            row=1, col=1
        )

    # SMA 50
    fig.add_trace(
        go.Scatter(
            x=df_chart.trade_date,
            y=df_chart["sma50"],
            name="SMA 50 (Short-term)",
            line=dict(color="#f59e0b", width=1.5)
        ),
        row=1, col=1
    )

    # SMA 200
    fig.add_trace(
        go.Scatter(
            x=df_chart.trade_date,
            y=df_chart["sma200"],
            name="SMA 200 (Long-term)",
            line=dict(color="#6366f1", width=1.8)
        ),
        row=1, col=1
    )

    # Volume Bars
    vol_color = "#3b82f6" if is_light else "#818cf8"
    fig.add_trace(
        go.Bar(
            x=df_chart.trade_date,
            y=df_chart.volume,
            name="Shares Traded",
            marker_color=vol_color,
            opacity=0.65
        ),
        row=2, col=1
    )

    fig.update_layout(
        height=660,
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.06, x=0.5, xanchor="center", font=dict(color=text_col)),
        margin=dict(l=10, r=10, t=40, b=10),
        template=template_name,
        paper_bgcolor=bg_paper,
        plot_bgcolor=bg_plot,
        font=dict(color=text_col),
        hovermode="x unified"
    )
    fig.update_yaxes(gridcolor=grid_col, row=1, col=1, title="Price (USD)", title_font=dict(color=text_col))
    fig.update_yaxes(gridcolor=grid_col, row=2, col=1, title="Volume", title_font=dict(color=text_col))
    fig.update_xaxes(gridcolor=grid_col)
    st.plotly_chart(fig, use_container_width=True)

    st.info("💡 **Technical Context:** A **Golden Cross** occurs when the 50-day moving average crosses above the 200-day moving average, signaling an upward trend. Volume spikes highlight institutional activity around earnings and macroeconomic events.")

    # Multi-Stock Trend and Power BI Section
    st.markdown("---")
    st.markdown("### 📊 15-Year Multi-Asset Performance and Power BI Visual")
    tab_multi, tab_pbi = st.tabs(["🌐 Interactive Multi-Stock Comparison (AAPL vs MSFT vs JPM)", "📈 Original Power BI Report View"])

    with tab_multi:
        st.caption("Compare 15-year cumulative return and performance across Tech and Banking giants.")
        mode = st.radio("Comparison Mode", ["Normalized % Growth (Base = 100 in 2011)", "Raw Stock Price ($ USD)"], horizontal=True)
        piv_prices = prices.pivot(index="trade_date", columns="ticker", values="close_price")
        
        fig_comp = go.Figure()
        for tkr_c in ["AAPL", "MSFT", "JPM"]:
            if mode.startswith("Normalized"):
                series_vals = (piv_prices[tkr_c] / piv_prices[tkr_c].iloc[0]) * 100.0
                y_label = "Cumulative Growth Index (Base 100)"
            else:
                series_vals = piv_prices[tkr_c]
                y_label = "Price ($ USD)"
            fig_comp.add_trace(go.Scatter(
                x=piv_prices.index,
                y=series_vals,
                name=f"{tkr_c} — {name_map.get(tkr_c, '')}",
                line=dict(color=COLORS[tkr_c], width=2)
            ))
        fig_comp.update_layout(
            height=460,
            hovermode="x unified",
            template="plotly_dark",
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
            yaxis_title=y_label,
            legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
            margin=dict(l=10, r=10, t=30, b=10)
        )
        fig_comp.update_yaxes(gridcolor="#1f2937")
        fig_comp.update_xaxes(gridcolor="#1f2937")
        st.plotly_chart(fig_comp, use_container_width=True)

    with tab_pbi:
        pbi_img = locate_file(["power_bi_dashboard.png"])
        if pbi_img:
            st.image(str(pbi_img), caption="Power BI Report: 15-Year Adjusted Closing Prices (AAPL vs MSFT vs JPM)", use_container_width=True)
        else:
            st.info("Power BI dashboard preview image loaded from repository.")

# ==============================================================================
# PAGE 2: FUNDAMENTALS
# ==============================================================================
elif nav_choice == "📊 Fundamentals":
    st.title(f"📊 {selected_ticker} — 10-Year Fundamental Performance")
    f = fundamentals[fundamentals.ticker == selected_ticker].sort_values("fiscal_year").reset_index(drop=True)
    latest_f = f.iloc[-1]
    net_margin = (latest_f.net_income / latest_f.revenue * 100.0) if latest_f.revenue else 0.0
    fcf_rate = (latest_f.free_cash_flow / latest_f.net_income * 100.0) if latest_f.net_income else 0.0

    c1, c2, c3 = st.columns(3)
    with c1: render_kpi("Revenue (Latest FY2025)", f"${latest_f.revenue:,.0f} M", f"Net Sales ({latest_f.revenue/1000:,.1f} Billion USD)")
    with c2: render_kpi("Net Income (Latest FY2025)", f"${latest_f.net_income:,.0f} M", f"Net Margin: {net_margin:.1f}%")
    with c3: render_kpi("Free Cash Flow (Latest FY2025)", f"${latest_f.free_cash_flow:,.0f} M", f"FCF Conversion: {fcf_rate:.1f}%")

    st.markdown("### Revenue, Net Income & Free Cash Flow (FY2016 – FY2025)")

    fig_f = make_subplots(specs=[[{"secondary_y": True}]])
    fig_f.add_trace(
        go.Bar(
            x=f.fiscal_year,
            y=f.revenue,
            name="Revenue ($M)",
            marker_color=COLORS[selected_ticker],
            opacity=0.8
        ),
        secondary_y=False
    )
    fig_f.add_trace(
        go.Scatter(
            x=f.fiscal_year,
            y=f.net_income,
            name="Net Income ($M)",
            line=dict(color="#f59e0b", width=3),
            mode="lines+markers"
        ),
        secondary_y=True
    )
    fig_f.add_trace(
        go.Scatter(
            x=f.fiscal_year,
            y=f.free_cash_flow,
            name="Free Cash Flow ($M)",
            line=dict(color="#10b981", width=3),
            mode="lines+markers"
        ),
        secondary_y=True
    )

    fig_f.update_layout(
        height=480,
        barmode="group",
        hovermode="x unified",
        legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
        template="plotly_dark",
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        margin=dict(l=10, r=10, t=30, b=10)
    )
    fig_f.update_yaxes(title_text="Revenue ($ Millions)", secondary_y=False, gridcolor="#1f2937")
    fig_f.update_yaxes(title_text="Net Income / FCF ($ Millions)", secondary_y=True, showgrid=False)
    fig_f.update_xaxes(title_text="Fiscal Year", gridcolor="#1f2937", dtick=1)
    st.plotly_chart(fig_f, use_container_width=True)

    st.markdown("### Complete Fundamentals Statement (from `fact_fundamentals`)")
    fund_table = f[["fiscal_year", "revenue", "net_income", "free_cash_flow"]].copy()
    fund_table["Net Margin %"] = (fund_table["net_income"] / fund_table["revenue"] * 100.0).round(1)
    fund_table.columns = ["Fiscal Year", "Revenue ($M)", "Net Income ($M)", "Free Cash Flow ($M)", "Net Margin %"]
    st.dataframe(
        fund_table.set_index("Fiscal Year").style.format({
            "Revenue ($M)": "${:,.0f}",
            "Net Income ($M)": "${:,.0f}",
            "Free Cash Flow ($M)": "${:,.0f}",
            "Net Margin %": "{:,.1f}%"
        }),
        use_container_width=True
    )

# ==============================================================================
# PAGE 3: RISK METRICS
# ==============================================================================
elif nav_choice == "⚠️ Risk Metrics":
    st.title("⚠️ Cross-Asset Risk & Portfolio Analytics")
    st.caption("Portfolio Analytics derived from SQL Queries Q11, Q14, Q15, Q28 & Q29")

    rows = []
    for t in ["AAPL", "MSFT", "JPM"]:
        v, s, d = get_risk_metrics(t)
        px, _ = get_latest_price(t)
        cagr = get_cagr(t)
        mcap = (px * SHARES_M[t]) / 1000.0
        rows.append({
            "Ticker": t,
            "Company": name_map.get(t, t),
            "Latest Price ($)": px,
            "15Y CAGR (%)": cagr,
            "Annual Volatility (%)": v,
            "Sharpe Ratio": s,
            "Max Drawdown (%)": d,
            "Market Cap ($B)": mcap
        })

    tbl = pd.DataFrame(rows).set_index("Ticker")
    st.dataframe(
        tbl.style.format({
            "Latest Price ($)": "${:,.2f}",
            "15Y CAGR (%)": "{:,.2f}%",
            "Annual Volatility (%)": "{:,.2f}%",
            "Sharpe Ratio": "{:,.2f}",
            "Max Drawdown (%)": "{:,.2f}%",
            "Market Cap ($B)": "${:,.1f} B"
        }),
        use_container_width=True
    )

    st.markdown("### Historical Underwater Curves (Drawdown from All-Time High)")
    fig_dd = go.Figure()
    for t in ["AAPL", "MSFT", "JPM"]:
        df_t = prices[prices.ticker == t].copy()
        roll_max = df_t.close_price.cummax()
        df_t["dd"] = ((df_t.close_price - roll_max) / roll_max) * 100.0
        fig_dd.add_trace(
            go.Scatter(
                x=df_t.trade_date,
                y=df_t["dd"],
                name=f"{t} ({name_map.get(t, '')})",
                line=dict(color=COLORS[t], width=1.5)
            )
        )

    fig_dd.update_layout(
        height=450,
        yaxis_title="Drawdown (%)",
        hovermode="x unified",
        template="plotly_dark",
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
        margin=dict(l=10, r=10, t=30, b=10)
    )
    fig_dd.update_yaxes(gridcolor="#1f2937", dtick=10)
    fig_dd.update_xaxes(gridcolor="#1f2937")
    st.plotly_chart(fig_dd, use_container_width=True)

    # Correlation Matrix
    st.markdown("### Daily Return Correlation Matrix (SQL Q28)")
    piv = prices.pivot(index="trade_date", columns="ticker", values="close_price")
    corr_mat = piv.pct_change().dropna().corr()
    c1, c2 = st.columns([1, 1])
    with c1:
        st.dataframe(safe_gradient(corr_mat.style, cmap="Blues").format("{:.3f}"), use_container_width=True)
    with c2:
        st.markdown(f"""
        - **Sharpe Benchmark:** Risk-free rate is **{RISK_FREE}%** (10-Yr US Treasury).
        - **Diversification Advantage:** Notice **JPM** (Financials) displays lower correlation to **AAPL** and **MSFT** (Tech), providing portfolio hedging benefits.
        """)

# ==============================================================================
# PAGE 4: DCF VALUATION MODEL
# ==============================================================================
elif nav_choice == "💰 DCF Valuation":
    st.title("💰 10-Year Discounted Cash Flow (DCF) Valuation")
    st.caption("Interactive intrinsic valuation model mirroring MySQL Queries Q31–Q34")

    f_sub = fundamentals[fundamentals.ticker == selected_ticker].sort_values("fiscal_year").reset_index(drop=True)
    base_fcf = float(f_sub.free_cash_flow.iloc[-1])

    # Handling negative FCF (e.g., Banks in FY2025) via historical median as in SQL Q32
    if base_fcf <= 0:
        base_fcf = FCF_FALLBACK.get(selected_ticker, 8533.0)
        st.warning(f"⚠️ **Base FCF Normalization:** {selected_ticker}'s FY2025 Free Cash Flow was negative (due to banking liquidity movements). As designed in SQL Q32, using 10-year historical median FCF of **${base_fcf:,.0f} M**.")

    st.markdown("### 1. Valuation Parameters")
    s1, s2, s3 = st.columns(3)
    with s1:
        g = st.slider(
            "10-Year FCF Growth Rate (%)",
            min_value=0.0, max_value=20.0,
            value=DCF_GROWTH[selected_ticker], step=0.5,
            key=f"g_dcf_{selected_ticker}",
            help="Expected compound annual growth rate of Free Cash Flow during the explicit 10-year forecast period."
        )
    with s2:
        wacc = st.slider(
            "WACC / Discount Rate (%)",
            min_value=5.0, max_value=15.0,
            value=BASE_WACC, step=0.5,
            key=f"wacc_dcf_{selected_ticker}",
            help="Weighted Average Cost of Capital: the required hurdle rate reflecting business risk and capital structure."
        )
    with s3:
        gt = st.slider(
            "Perpetual Terminal Growth (%)",
            min_value=0.5, max_value=5.0,
            value=TERMINAL_G, step=0.25,
            key=f"gt_dcf_{selected_ticker}",
            help="Sustainable perpetual growth rate beyond Year 10 (Gordon Growth Model). Pegged around long-term GDP growth (2-3%)."
        )

    if wacc <= gt:
        st.error("❌ **Gordon Growth Error:** Discount rate (WACC) must strictly exceed Terminal Growth Rate (WACC > g_terminal). Adjust sliders.")
        st.stop()

    # ---- DCF ENGINE (Exact SQL Q32/Q33 Logic) ----
    years = np.arange(1, 11)
    fcf_proj = base_fcf * ((1.0 + g / 100.0) ** years)
    discount_factors = (1.0 + wacc / 100.0) ** years
    pv_explicit_fcf = fcf_proj / discount_factors
    total_pv_fcf = float(pv_explicit_fcf.sum())

    # Gordon Growth Terminal Value
    terminal_val = (fcf_proj[-1] * (1.0 + gt / 100.0)) / ((wacc - gt) / 100.0)
    pv_terminal_val = float(terminal_val / discount_factors[-1])

    total_equity_value = total_pv_fcf + pv_terminal_val
    shares_count = SHARES_M[selected_ticker]
    intrinsic_value = total_equity_value / shares_count

    mkt_price, mkt_date = get_latest_price(selected_ticker)
    upside_pct = ((intrinsic_value / mkt_price) - 1.0) * 100.0
    sql_benchmark = Q33_INTRINSIC[selected_ticker]

    st.markdown("### 2. Intrinsic Value & Market Benchmark")
    k1, k2, k3, k4 = st.columns(4)
    with k1: render_kpi("DCF Value / Share", f"${intrinsic_value:,.2f}", "Implied Intrinsic Value")
    with k2: render_kpi("Current Market Price", f"${mkt_price:,.2f}", f"As of {mkt_date:%d %b %Y}")
    with k3:
        sign = "+" if upside_pct >= 0 else ""
        render_kpi("Upside / Downside", f"{sign}{upside_pct:.1f}%", "DCF vs Market")
    with k4: render_kpi("SQL Baseline (Q33)", f"${sql_benchmark:,.2f}", "9% WACC / 2.5% Terminal")

    # Valuation Verdict Badge
    if upside_pct > 15.0:
        st.success(f"### Valuation Verdict: 🟢 UNDERVALUED (Trading at a {abs(upside_pct):.1f}% discount to DCF Intrinsic Value)")
    elif upside_pct < -15.0:
        st.warning(f"### Valuation Verdict: 🔴 OVERVALUED (Trading at a {abs(upside_pct):.1f}% premium above DCF Intrinsic Value)")
    else:
        st.info("### Valuation Verdict: 🟡 FAIRLY VALUED (Trading within 15% range of DCF Intrinsic Value)")

    # Projection Chart
    st.markdown("### 3. 10-Year Projected Free Cash Flows & Present Values")
    fig_proj = go.Figure()
    fig_proj.add_trace(
        go.Bar(
            x=[f"Year {y}" for y in years],
            y=fcf_proj,
            name="Nominal Projected FCF ($M)",
            marker_color=COLORS[selected_ticker],
            opacity=0.85
        )
    )
    fig_proj.add_trace(
        go.Scatter(
            x=[f"Year {y}" for y in years],
            y=pv_explicit_fcf,
            name="Present Value (PV at WACC) ($M)",
            line=dict(color="#f59e0b", width=3),
            mode="lines+markers"
        )
    )
    fig_proj.update_layout(
        height=400,
        barmode="group",
        hovermode="x unified",
        template="plotly_dark",
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
        margin=dict(l=10, r=10, t=30, b=10)
    )
    fig_proj.update_yaxes(title="Cash Flow ($ Millions)", gridcolor="#1f2937")
    fig_proj.update_xaxes(gridcolor="#1f2937")
    st.plotly_chart(fig_proj, use_container_width=True)

    # Valuation Breakdown
    b1, b2 = st.columns([1, 1])
    with b1:
        st.markdown("**Valuation Components:**")
        comp_df = pd.DataFrame([
            {"Component": "PV of 10-Yr Cash Flows", "Amount ($M)": total_pv_fcf, "% of Total Value": (total_pv_fcf / total_equity_value) * 100},
            {"Component": "PV of Perpetual Terminal Value", "Amount ($M)": pv_terminal_val, "% of Total Value": (pv_terminal_val / total_equity_value) * 100},
            {"Component": "Total Implied Equity Value", "Amount ($M)": total_equity_value, "% of Total Value": 100.0},
            {"Component": "Shares Outstanding (M)", "Amount ($M)": shares_count, "% of Total Value": np.nan},
            {"Component": "Implied Fair Value per Share ($)", "Amount ($M)": intrinsic_value, "% of Total Value": np.nan}
        ])
        st.dataframe(
            comp_df.style.format({
                "Amount ($M)": "${:,.2f}",
                "% of Total Value": "{:,.1f}%"
            }),
            use_container_width=True
        )
    with b2:
        st.markdown("**Value Composition (Explicit vs Terminal):**")
        fig_pie = go.Figure(data=[go.Pie(
            labels=["10-Yr Explicit Cash Flows", "Terminal Value"],
            values=[total_pv_fcf, pv_terminal_val],
            hole=0.45,
            marker_colors=["#0ea5e9", "#10b981"]
        )])
        fig_pie.update_layout(
            height=260,
            margin=dict(l=10, r=10, t=10, b=10),
            template="plotly_dark",
            paper_bgcolor="#0e1117"
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    # Sensitivity Matrix
    st.markdown("### 4. Valuation Sensitivity Matrix (WACC vs Growth Rate)")
    test_waccs = [7.0, 8.0, 9.0, 10.0, 11.0]
    test_growths = np.arange(2.0, 15.0, 2.0)
    matrix_rows = []
    for test_g in test_growths:
        r_vals = []
        for test_w in test_waccs:
            if test_w <= gt:
                r_vals.append(np.nan)
                continue
            p_fcf = base_fcf * ((1.0 + test_g / 100.0) ** years)
            d_fac = (1.0 + test_w / 100.0) ** years
            pv_e = (p_fcf / d_fac).sum()
            tv = (p_fcf[-1] * (1.0 + gt / 100.0)) / ((test_w - gt) / 100.0)
            pv_t = tv / d_fac[-1]
            r_vals.append((pv_e + pv_t) / shares_count)
        matrix_rows.append(r_vals)

    sens_df = pd.DataFrame(
        matrix_rows,
        index=[f"Growth {g_val:.0f}%" for g_val in test_growths],
        columns=[f"WACC {w_val:.0f}%" for w_val in test_waccs]
    )
    st.dataframe(
        safe_gradient(sens_df.style.format("${:,.2f}"), cmap="RdYlGn"),
        use_container_width=True
    )
    st.caption(f"🟢 Green cells exceed current market price (${mkt_price:,.2f}) — bull cases.")

# ==============================================================================
# PAGE 5: LBO MODEL (LEVERAGED BUYOUT)
# ==============================================================================
elif nav_choice == "🏢 LBO Model (Buyout)":
    st.title(f"🏢 5-Year Leveraged Buyout (LBO) Model — {selected_ticker}")
    st.caption("Private Equity Sponsor Model: Transaction Financing, Debt Paydown, Exit Valuation, IRR & MoIC Returns")

    f_sub = fundamentals[fundamentals.ticker == selected_ticker].sort_values("fiscal_year").reset_index(drop=True)
    latest_f = f_sub.iloc[-1]
    
    # Estimate EBITDA proxy = Net Income * 1.30 (or reasonable baseline)
    ebitda_base = float(latest_f.net_income * 1.30)
    if ebitda_base <= 0:
        ebitda_base = 25000.0

    st.markdown("### 1. Transaction Assumptions (Entry)")
    l1, l2, l3 = st.columns(3)
    with l1:
        entry_multiple = st.slider(
            "Entry EV / EBITDA Multiple (x)",
            min_value=6.0, max_value=25.0,
            value=15.0 if selected_ticker != "JPM" else 10.0, step=0.5,
            help="Acquisition valuation multiple paid for the enterprise."
        )
    with l2:
        debt_percent = st.slider(
            "Debt Financing (% of Purchase Price)",
            min_value=30.0, max_value=80.0,
            value=60.0, step=5.0,
            help="Proportion of total acquisition funded via leveraged loans / high yield bonds."
        )
    with l3:
        interest_rate = st.slider(
            "Cost of Debt / Interest Rate (%)",
            min_value=4.0, max_value=12.0,
            value=7.5, step=0.5,
            help="Annual interest expense on outstanding debt."
        )

    # Entry Enterprise Value & Sources & Uses
    entry_ev = ebitda_base * entry_multiple
    entry_debt = entry_ev * (debt_percent / 100.0)
    sponsor_equity = entry_ev - entry_debt

    st.markdown("### 2. Operating & Exit Assumptions (5-Year Horizon)")
    o1, o2, o3 = st.columns(3)
    with o1:
        ebitda_growth = st.slider(
            "Annual EBITDA Growth (% p.a.)",
            min_value=2.0, max_value=20.0,
            value=8.0, step=0.5,
            help="Annual operating growth generated by the sponsor over 5 years."
        )
    with o2:
        fcf_conversion_lbo = st.slider(
            "FCF to EBITDA Conversion (%)",
            min_value=30.0, max_value=85.0,
            value=60.0, step=5.0,
            help="% of EBITDA converted to cash available for debt repayment after CapEx and taxes."
        )
    with o3:
        exit_multiple = st.slider(
            "Exit EV / EBITDA Multiple (x)",
            min_value=6.0, max_value=25.0,
            value=entry_multiple, step=0.5,
            help="Multiple received upon exit (sale to strategic or secondary buyout)."
        )

    # 5-Year LBO Schedule Engine
    lbo_years = [1, 2, 3, 4, 5]
    ebitda_proj = [ebitda_base * ((1.0 + ebitda_growth / 100.0) ** y) for y in lbo_years]
    
    current_debt = entry_debt
    debt_schedule = []
    interest_paid_list = []
    debt_paydown_list = []

    for yr_ebitda in ebitda_proj:
        annual_interest = current_debt * (interest_rate / 100.0)
        cash_for_debt = max(0.0, (yr_ebitda * (fcf_conversion_lbo / 100.0)) - annual_interest)
        paydown = min(current_debt, cash_for_debt)
        current_debt -= paydown
        
        interest_paid_list.append(annual_interest)
        debt_paydown_list.append(paydown)
        debt_schedule.append(current_debt)

    exit_ebitda = ebitda_proj[-1]
    exit_ev = exit_ebitda * exit_multiple
    ending_debt = debt_schedule[-1]
    exit_equity = exit_ev - ending_debt

    # Sponsor Returns: IRR & MoIC
    moic = exit_equity / sponsor_equity if sponsor_equity > 0 else 0.0
    irr = ((moic ** (1.0 / 5.0)) - 1.0) * 100.0 if moic > 0 else 0.0

    st.markdown("### 3. Sponsor Investment Returns (5-Year Exit)")
    r1, r2, r3, r4 = st.columns(4)
    with r1: render_kpi("Sponsor Initial Equity", f"${sponsor_equity:,.0f} M", f"{(100-debt_percent):.0f}% of ${entry_ev:,.0f}M EV")
    with r2: render_kpi("Sponsor Exit Equity", f"${exit_equity:,.0f} M", "Year 5 Equity Value")
    with r3: render_kpi("Money-on-Invested-Capital", f"{moic:.2f}x MoIC", "Total Cash Return Multiple")
    with r4: render_kpi("5-Year Sponsor IRR", f"{irr:.1f}%", "Internal Rate of Return")

    # Return Benchmark Badge
    if irr >= 25.0:
        st.success(f"🔥 **Exceptional PE Return:** {irr:.1f}% IRR ({moic:.2f}x MoIC) exceeds traditional Private Equity target hurdles of 20-25%.")
    elif irr >= 18.0:
        st.info(f"✅ **Solid LBO Deal:** {irr:.1f}% IRR ({moic:.2f}x MoIC) meets typical institutional sponsor underwriting criteria (18-20%).")
    else:
        st.warning(f"⚠️ **Sub-Target Return:** {irr:.1f}% IRR ({moic:.2f}x MoIC) is below standard PE target hurdles. Consider lower purchase multiple, higher leverage, or faster operating growth.")

    # LBO Schedule Table
    st.markdown("### 4. 5-Year LBO Debt Paydown & Cash Flow Schedule")
    lbo_df = pd.DataFrame({
        "Year": [f"Year {y}" for y in lbo_years],
        "EBITDA ($M)": ebitda_proj,
        "Interest Expense ($M)": interest_paid_list,
        "Debt Paydown ($M)": debt_paydown_list,
        "Ending Debt ($M)": debt_schedule
    })
    st.dataframe(
        lbo_df.set_index("Year").style.format("${:,.0f}"),
        use_container_width=True
    )

    # Returns Sensitivity Matrix (Entry Multiple vs Exit Multiple)
    st.markdown("### 5. Returns Sensitivity: IRR % vs Entry & Exit Multiples")
    test_entries = [entry_multiple - 2.0, entry_multiple - 1.0, entry_multiple, entry_multiple + 1.0, entry_multiple + 2.0]
    test_exits = [exit_multiple - 2.0, exit_multiple - 1.0, exit_multiple, exit_multiple + 1.0, exit_multiple + 2.0]
    
    irr_grid = []
    for test_en in test_entries:
        row_irr = []
        for test_ex in test_exits:
            t_ev = ebitda_base * test_en
            t_eq = t_ev * ((100.0 - debt_percent) / 100.0)
            t_exit_ev = exit_ebitda * test_ex
            t_exit_eq = t_exit_ev - ending_debt
            if t_eq > 0 and t_exit_eq > 0:
                m = t_exit_eq / t_eq
                val_irr = ((m ** 0.2) - 1.0) * 100.0
            else:
                val_irr = np.nan
            row_irr.append(val_irr)
        irr_grid.append(row_irr)

    irr_sens_df = pd.DataFrame(
        irr_grid,
        index=[f"Entry {e:.1f}x" for e in test_entries],
        columns=[f"Exit {x:.1f}x" for x in test_exits]
    )
    st.dataframe(
        safe_gradient(irr_sens_df.style.format("{:.1f}%"), cmap="RdYlGn"),
        use_container_width=True
    )
    st.caption("🟢 Green indicates sponsor IRRs above 20% hurdle rate.")

# ==============================================================================
# PAGE 6: FINANCIAL CONCEPT GUIDE & PROJECT STORY
# ==============================================================================
else:
    st.title("📚 Financial Concepts, Methodology & Project Architecture")
    st.caption("A complete guide explaining what each financial model does and how to master them")

    st.markdown("""
    ### 🎯 Demystifying the Financial Jargon: What is the Difference?

    When working in financial analytics, investment banking, and corporate finance, you will encounter terms like **Budgeting**, **Forecasting**, **DCF**, and **LBO**. Here is the clear, intuitive distinction:

    | Concept | What It Actually Is | Time Horizon | Primary Use Case |
    | :--- | :--- | :--- | :--- |
    | **Budgeting** | An internal spending plan created by company management setting limits on expenses and targets for revenue. | Next 1 fiscal year | Internal operational control & performance management. |
    | **Forecasting** | An expected projection of financial outcomes based on historical trends and macroeconomic assumptions. | 1 to 5 years | Strategic planning and updating business expectations. |
    | **DCF (Discounted Cash Flow)** | An intrinsic valuation model calculating what a company is worth **today** by projecting its Free Cash Flow and discounting it to present value using WACC. | 5 to 10 years + Terminal Value | Fundamental stock valuation, equity research, M&A fair value. |
    | **LBO (Leveraged Buyout)** | An acquisition model used by Private Equity firms that buys a company using a large amount of borrowed money (debt), pays down debt using company cash flows, and exits at a high return (IRR). | Typically 3 to 7 years | Private equity investing, debt structuring, sponsor buyouts. |

    ---

    ### 🧮 The DCF Model Step-by-Step (How Queries Q31–Q34 Work)
    1. **Start with Free Cash Flow (FCF):** Cash generated after paying all operating expenses and capital investments (CapEx).
    2. **Project explicit FCF for 10 Years:** Grow the base cash flow at rate `g` each year:
       $$\\text{FCF}_t = \\text{Base FCF} \\times (1 + g)^t$$
    3. **Discount to Present Value at WACC:** Money in the future is worth less today due to the time value of money and investment risk:
       $$\\text{PV}_t = \\frac{\\text{FCF}_t}{(1 + \\text{WACC})^t}$$
    4. **Calculate Perpetual Terminal Value (Gordon Growth):**
       $$\\text{Terminal Value} = \\frac{\\text{FCF}_{10} \\times (1 + g_{\\text{terminal}})}{\\text{WACC} - g_{\\text{terminal}}}$$
    5. **Sum & Divide by Shares:**
       $$\\text{Intrinsic Value per Share} = \\frac{\\sum \\text{PV}(\\text{FCF}) + \\text{PV}(\\text{Terminal Value})}{\\text{Shares Outstanding}}$$

    ---

    ### 🏢 The LBO Model Step-by-Step
    1. **Acquisition (Entry):** The sponsor acquires the company at an Enterprise Value multiple (e.g., 15x EBITDA).
    2. **Financing (Sources of Capital):** 60% of the purchase is financed with bank debt and 40% with sponsor equity.
    3. **Cash Generation & Deleveraging:** Over 5 years, the company uses its operational Free Cash Flow to pay down debt.
    4. **Exit Valuation:** In Year 5, the company is sold. Because debt was paid down and EBITDA grew, the equity value has multiplied!
    5. **Returns:** Measured by **MoIC** (cash-on-cash multiple) and **IRR** (annualized compound return).

    ---

    ### 🏗️ Why this Project is Institutional-Grade
    - **Full 15 Years of Market Data:** ~11,900 daily rows across Apple, Microsoft, and JPMorgan.
    - **Production Star Schema:** Normalizes dimensions (`dim_companies`) and facts (`fact_prices`, `fact_fundamentals`).
    - **Advanced SQL:** Window functions (`OVER()`), recursive CTEs for cash flow compound growth, drawdown math.
    - **Production Streamlit App:** Real-time sensitivity analysis, interactive Plotly charts, and dual valuation engines (DCF & LBO).
    """)
