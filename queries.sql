-- Financial Analytics Platform — 30 Analytical Queries
-- Database: finance_platform | Tickers: AAPL, MSFT, JPM
USE finance_platform;
-- Q1: How much price data do we have for each company?
SELECT c.ticker,
       COUNT(*) AS trading_days,
       MIN(p.trade_date) AS first_day,
       MAX(p.trade_date) AS last_day
FROM fact_prices p
JOIN dim_companies c ON c.company_id = p.company_id
GROUP BY c.ticker;

-- Q2: First vs latest closing price (how far each stock has come)
WITH bounds AS (
  SELECT p.company_id,
         MIN(p.trade_date) AS first_day,
         MAX(p.trade_date) AS last_day
  FROM fact_prices p
  GROUP BY p.company_id
)
SELECT c.ticker,
       first.close_price AS first_close,
       last.close_price AS latest_close,
       ROUND((last.close_price / first.close_price - 1) * 100, 0) AS total_return_pct
FROM bounds b
JOIN fact_prices first ON first.company_id = b.company_id AND first.trade_date = b.first_day
JOIN fact_prices last  ON last.company_id  = b.company_id AND last.trade_date  = b.last_day
JOIN dim_companies c ON c.company_id = b.company_id;

-- Q3: Average daily trading volume per stock
SELECT c.ticker,
       ROUND(AVG(p.volume) / 1000000, 1) AS avg_daily_volume_millions
FROM fact_prices p
JOIN dim_companies c ON c.company_id = p.company_id
GROUP BY c.ticker;

-- Q4: Biggest single-day gain and biggest single-day drop
WITH daily AS (
  SELECT c.ticker, p.trade_date,
         p.close_price / LAG(p.close_price) OVER (PARTITION BY p.company_id ORDER BY p.trade_date) - 1 AS day_return
  FROM fact_prices p
  JOIN dim_companies c ON c.company_id = p.company_id
)
SELECT ticker,
       ROUND(MAX(day_return) * 100, 1) AS best_day_pct,
       ROUND(MIN(day_return) * 100, 1) AS worst_day_pct
FROM daily
GROUP BY ticker;

-- Q5: Companies and their fundamentals coverage
SELECT c.ticker, c.company_name, c.sector, c.exchange,
       (SELECT COUNT(*) FROM fact_fundamentals f WHERE f.company_id = c.company_id) AS years_of_fundamentals
FROM dim_companies c;
-- Q6: Revenue for the latest fiscal year side-by-side
SELECT c.ticker,
       f.fiscal_year,
       f.revenue / 1000 AS revenue_billions
FROM fact_fundamentals f
JOIN dim_companies c ON c.company_id = f.company_id
WHERE f.fiscal_year = (SELECT MAX(fiscal_year) FROM fact_fundamentals)
ORDER BY revenue_billions DESC;

-- Q7: Revenue growth rate year-over-year
WITH rev AS (
  SELECT c.ticker, f.fiscal_year, f.revenue,
         LAG(f.revenue) OVER (PARTITION BY f.company_id ORDER BY f.fiscal_year) AS prev_revenue
  FROM fact_fundamentals f
  JOIN dim_companies c ON c.company_id = f.company_id
)
SELECT ticker, fiscal_year,
       ROUND((revenue / prev_revenue - 1) * 100, 1) AS revenue_growth_pct
FROM rev
WHERE prev_revenue IS NOT NULL
ORDER BY ticker, fiscal_year;

-- Q8: Net profit margin (net income / revenue)
SELECT c.ticker,
       f.fiscal_year,
       ROUND(f.net_income / f.revenue * 100, 1) AS net_margin_pct
FROM fact_fundamentals f
JOIN dim_companies c ON c.company_id = f.company_id
ORDER BY c.ticker, f.fiscal_year;

-- Q9: Free cash flow compared to net income (cash quality of earnings)
SELECT c.ticker,
       f.fiscal_year,
       f.free_cash_flow / 1000 AS fcf_billions,
       f.net_income / 1000 AS net_income_billions,
       ROUND(f.free_cash_flow / f.net_income * 100, 0) AS fcf_vs_income_pct
FROM fact_fundamentals f
JOIN dim_companies c ON c.company_id = f.company_id
ORDER BY c.ticker, f.fiscal_year;

-- Q10: 5-year revenue CAGR (Compound Annual Growth Rate)
WITH first_last AS (
  SELECT company_id,
         MIN(fiscal_year) AS first_year,
         MAX(fiscal_year) AS last_year
  FROM fact_fundamentals
  GROUP BY company_id
)
SELECT c.ticker,
       f1.revenue / 1000 AS earliest_revenue_billions,
       f2.revenue / 1000 AS latest_revenue_billions,
       ROUND((POW(f2.revenue / f1.revenue, 1.0 / (fl.last_year - fl.first_year)) - 1) * 100, 1) AS cagr_pct
FROM first_last fl
JOIN fact_fundamentals f1 ON f1.company_id = fl.company_id AND f1.fiscal_year = fl.first_year
JOIN fact_fundamentals f2 ON f2.company_id = fl.company_id AND f2.fiscal_year = fl.last_year
JOIN dim_companies c ON c.company_id = fl.company_id;
-- Q11: Annualized volatility (risk) — how wildly each stock swings
WITH daily AS (
  SELECT p.company_id, p.trade_date,
         p.close_price / LAG(p.close_price) OVER (PARTITION BY p.company_id ORDER BY p.trade_date) - 1 AS day_return
  FROM fact_prices p
)
SELECT c.ticker,
       ROUND(STDDEV_POP(day_return) * SQRT(252) * 100, 1) AS annual_volatility_pct
FROM daily d
JOIN dim_companies c ON c.company_id = d.company_id
WHERE d.day_return IS NOT NULL
GROUP BY c.ticker;

-- Q12: Best and worst calendar year performance for each stock
WITH yearly AS (
  SELECT company_id, YEAR(trade_date) AS yr,
         MIN(close_price) AS yr_close
  FROM fact_prices
  GROUP BY company_id, YEAR(trade_date)
),
returns AS (
  SELECT company_id, yr,
         yr_close / LAG(yr_close) OVER (PARTITION BY company_id ORDER BY yr) - 1 AS yr_return
  FROM yearly
)
SELECT c.ticker,
       ROUND(MAX(yr_return) * 100, 1) AS best_year_pct,
       ROUND(MIN(yr_return) * 100, 1) AS worst_year_pct
FROM returns r
JOIN dim_companies c ON c.company_id = r.company_id
WHERE r.yr_return IS NOT NULL
GROUP BY c.ticker;

-- Q13: 50-day vs 200-day moving average (the "Golden Cross" indicator)
WITH ma AS (
  SELECT p.company_id, p.trade_date, p.close_price,
         AVG(p.close_price) OVER (PARTITION BY p.company_id ORDER BY p.trade_date
                                  ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) AS ma50,
         AVG(p.close_price) OVER (PARTITION BY p.company_id ORDER BY p.trade_date
                                  ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) AS ma200
  FROM fact_prices p
)
SELECT c.ticker,
       ROUND(latest.ma50, 2) AS ma50,
       ROUND(latest.ma200, 2) AS ma200,
       CASE WHEN latest.ma50 > latest.ma200 THEN 'BULLISH (golden cross)' ELSE 'BEARISH (death cross)' END AS signal
FROM (
  SELECT m.*, ROW_NUMBER() OVER (PARTITION BY m.company_id ORDER BY m.trade_date DESC) AS rn
  FROM ma m
) latest
JOIN dim_companies c ON c.company_id = latest.company_id
WHERE latest.rn = 1;

-- Q14: Maximum drawdown — biggest peak-to-trough loss (worst pain a holder would feel)
WITH running AS (
  SELECT p.company_id, p.trade_date, p.close_price,
         MAX(p.close_price) OVER (PARTITION BY p.company_id ORDER BY p.trade_date) AS peak_so_far
  FROM fact_prices p
)
SELECT c.ticker,
       ROUND(MIN(close_price / peak_so_far - 1) * 100, 1) AS max_drawdown_pct
FROM running r
JOIN dim_companies c ON c.company_id = r.company_id
GROUP BY c.ticker;

-- Q15: Sharpe ratio — return earned per unit of risk (risk-free rate = 4%)
WITH daily AS (
  SELECT p.company_id, p.trade_date,
         p.close_price / LAG(p.close_price) OVER (PARTITION BY p.company_id ORDER BY p.trade_date) - 1 AS day_return
  FROM fact_prices p
)
SELECT c.ticker,
       ROUND(AVG(d.day_return) * 252 * 100, 1) AS annual_return_pct,
       ROUND((AVG(d.day_return) * 252 - 0.04) / (STDDEV_POP(d.day_return) * SQRT(252)), 2) AS sharpe_ratio
FROM daily d
JOIN dim_companies c ON c.company_id = d.company_id
WHERE d.day_return IS NOT NULL
GROUP BY c.ticker;
-- Q16: Average monthly return for each stock (seasonality check)
WITH daily AS (
  SELECT p.company_id, p.trade_date,
         p.close_price / LAG(p.close_price) OVER (PARTITION BY p.company_id ORDER BY p.trade_date) - 1 AS day_return
  FROM fact_prices p
),
monthly AS (
  SELECT company_id, YEAR(trade_date) AS yr, MONTH(trade_date) AS mnth,
         SUM(day_return) AS month_return
  FROM daily
  WHERE day_return IS NOT NULL
  GROUP BY company_id, YEAR(trade_date), MONTH(trade_date)
)
SELECT c.ticker, mnth AS month_number,
       ROUND(AVG(month_return) * 100, 2) AS avg_monthly_return_pct
FROM monthly m
JOIN dim_companies c ON c.company_id = m.company_id
GROUP BY c.ticker, mnth
ORDER BY c.ticker, mnth;

-- Q17: Month-over-month closing price change
WITH month_end AS (
  SELECT company_id, DATE_FORMAT(trade_date, '%Y-%m') AS yr_month,
         close_price,
         ROW_NUMBER() OVER (PARTITION BY company_id, DATE_FORMAT(trade_date, '%Y-%m')
                           ORDER BY trade_date DESC) AS rn
  FROM fact_prices
)
SELECT c.ticker, yr_month, close_price AS month_end_close,
       ROUND(close_price / LAG(close_price) OVER (PARTITION BY company_id ORDER BY yr_month) - 1, 4) AS mom_change
FROM month_end me
JOIN dim_companies c ON c.company_id = me.company_id
WHERE rn = 1
ORDER BY c.ticker, yr_month;

-- Q18: Highest and lowest trading volume days ever
SELECT c.ticker, p.trade_date, p.volume,
       CASE WHEN p.volume = MAX(p.volume) OVER (PARTITION BY p.company_id) THEN 'HIGHEST' ELSE 'LOWEST' END AS label
FROM (
  SELECT company_id, trade_date, volume,
         ROW_NUMBER() OVER (PARTITION BY company_id ORDER BY volume DESC) AS hi_rn,
         ROW_NUMBER() OVER (PARTITION BY company_id ORDER BY volume ASC)  AS lo_rn
  FROM fact_prices
) ranked
JOIN dim_companies c ON c.company_id = ranked.company_id
WHERE (hi_rn = 1 OR lo_rn = 1);

-- Q19: Days when volume spiked 3x above the average (big market events)
WITH avg_vol AS (
  SELECT company_id, AVG(volume) AS avg_volume
  FROM fact_prices
  GROUP BY company_id
)
SELECT c.ticker, p.trade_date, p.volume, ROUND(p.volume / a.avg_volume, 1) AS multiple_of_avg
FROM fact_prices p
JOIN avg_vol a ON a.company_id = p.company_id
JOIN dim_companies c ON c.company_id = p.company_id
WHERE p.volume > 3 * a.avg_volume
ORDER BY c.ticker, p.trade_date;

-- Q20: Intraday range volatility (high minus low, as % of close)
SELECT c.ticker,
       ROUND(AVG((p.high_price - p.low_price) / p.close_price) * 100, 2) AS avg_intraday_range_pct,
       ROUND(MAX((p.high_price - p.low_price) / p.close_price) * 100, 2) AS max_intraday_range_pct
FROM fact_prices p
JOIN dim_companies c ON c.company_id = p.company_id
GROUP BY c.ticker;

-- Q21: Price performance on the top 10 highest-volume days vs normal days
WITH ranked AS (
  SELECT p.*, c.ticker,
         ROW_NUMBER() OVER (PARTITION BY p.company_id ORDER BY p.volume DESC) AS vol_rank,
         COUNT(*) OVER (PARTITION BY p.company_id) AS total_days
  FROM fact_prices p
  JOIN dim_companies c ON c.company_id = p.company_id
),
labeled AS (
  SELECT r.*,
         r.close_price / LAG(r.close_price) OVER (PARTITION BY r.company_id ORDER BY r.trade_date) - 1 AS day_return,
         CASE WHEN r.vol_rank <= ROUND(r.total_days * 0.10) THEN 'high_volume' ELSE 'normal' END AS vol_group
  FROM ranked r
)
SELECT ticker, vol_group,
       ROUND(AVG(day_return) * 100, 2) AS avg_daily_return_pct
FROM labeled
WHERE day_return IS NOT NULL
GROUP BY ticker, vol_group;

-- Q22: Rolling 3-month average volume trend (is trading activity rising or falling?)
WITH monthly_vol AS (
  SELECT company_id, DATE_FORMAT(trade_date, '%Y-%m') AS yr_month,
         SUM(volume) AS month_volume
  FROM fact_prices
  GROUP BY company_id, DATE_FORMAT(trade_date, '%Y-%m')
)
SELECT c.ticker, yr_month, month_volume,
       ROUND(AVG(month_volume) OVER (PARTITION BY company_id ORDER BY yr_month
              ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) / 1000000, 1) AS rolling_3m_avg_millions
FROM monthly_vol mv
JOIN dim_companies c ON c.company_id = mv.company_id
ORDER BY c.ticker, yr_month;
-- Q23: Valuation check — market cap using latest close price
-- (assumes share counts: AAPL 15,000M, MSFT 7,430M, JPM 2,800M — illustrative)
WITH latest AS (
  SELECT company_id, close_price
  FROM fact_prices p
  WHERE trade_date = (SELECT MAX(trade_date) FROM fact_prices WHERE company_id = p.company_id)
)
SELECT c.ticker, l.close_price,
       ROUND(l.close_price * CASE c.ticker WHEN 'AAPL' THEN 15000 WHEN 'MSFT' THEN 7430 WHEN 'JPM' THEN 2800 END / 1000, 0) AS market_cap_billions
FROM latest l
JOIN dim_companies c ON c.company_id = l.company_id;

-- Q24: Price-to-earnings ratio (P/E) — price vs per-share earnings
-- (EPS = net income / shares outstanding, both in same units)
WITH latest AS (
  SELECT company_id, close_price
  FROM fact_prices p
  WHERE trade_date = (SELECT MAX(trade_date) FROM fact_prices WHERE company_id = p.company_id)
),
earnings AS (
  SELECT company_id, net_income
  FROM fact_fundamentals
  WHERE fiscal_year = (SELECT MAX(fiscal_year) FROM fact_fundamentals)
)
SELECT c.ticker, l.close_price,
       e.net_income,
       ROUND(l.close_price / (e.net_income / CASE c.ticker WHEN 'AAPL' THEN 15000 WHEN 'MSFT' THEN 7430 WHEN 'JPM' THEN 2800 END), 1) AS pe_ratio
FROM latest l
JOIN earnings e ON e.company_id = l.company_id
JOIN dim_companies c ON c.company_id = l.company_id;

-- Q25: Earnings growth — net income year-over-year change
WITH ni AS (
  SELECT c.ticker, f.fiscal_year, f.net_income,
         LAG(f.net_income) OVER (PARTITION BY f.company_id ORDER BY f.fiscal_year) AS prev_ni
  FROM fact_fundamentals f
  JOIN dim_companies c ON c.company_id = f.company_id
)
SELECT ticker, fiscal_year,
       ROUND((net_income / prev_ni - 1) * 100, 1) AS net_income_growth_pct
FROM ni
WHERE prev_ni IS NOT NULL
ORDER BY ticker, fiscal_year;

-- Q26: Do rising earnings line up with rising stock prices? (price vs fundamentals, per year)
WITH yearly_close AS (
  SELECT company_id, YEAR(trade_date) AS yr, AVG(close_price) AS avg_close
  FROM fact_prices
  GROUP BY company_id, YEAR(trade_date)
)
SELECT c.ticker, f.fiscal_year,
       ROUND(y.avg_close, 2) AS avg_stock_price,
       f.revenue / 1000 AS revenue_billions,
       f.net_income / 1000 AS net_income_billions
FROM fact_fundamentals f
JOIN yearly_close y ON y.company_id = f.company_id AND y.yr = f.fiscal_year
JOIN dim_companies c ON c.company_id = f.company_id
ORDER BY c.ticker, f.fiscal_year;

-- Q27: Price-to-revenue growth comparison — is the stock outpacing the business?
WITH yearly AS (
  SELECT company_id, YEAR(trade_date) AS yr,
         MAX(close_price) / MIN(close_price) - 1 AS price_change
  FROM fact_prices
  GROUP BY company_id, YEAR(trade_date)
),
rev_growth AS (
  SELECT company_id, fiscal_year,
         revenue / LAG(revenue) OVER (PARTITION BY company_id ORDER BY fiscal_year) - 1 AS rev_change
  FROM fact_fundamentals
)
SELECT c.ticker, y.yr,
       ROUND(y.price_change * 100, 1) AS stock_price_change_pct,
       ROUND(r.rev_change * 100, 1) AS revenue_growth_pct,
       CASE WHEN y.price_change > r.rev_change THEN 'Price ahead of business' ELSE 'Business ahead of price' END AS verdict
FROM yearly y
JOIN rev_growth r ON r.company_id = y.company_id AND r.fiscal_year = y.yr
JOIN dim_companies c ON c.company_id = y.company_id
WHERE r.rev_change IS NOT NULL
ORDER BY c.ticker, y.yr;

-- Q28: Correlation between stock daily returns (do AAPL, MSFT, JPM move together?)
WITH returns AS (
  SELECT c.ticker, p.trade_date,
         p.close_price / LAG(p.close_price) OVER (PARTITION BY p.company_id ORDER BY p.trade_date) - 1 AS day_return
  FROM fact_prices p
  JOIN dim_companies c ON c.company_id = p.company_id
)
SELECT a.ticker AS stock_1, b.ticker AS stock_2,
       ROUND(AVG(a.day_return * b.day_return) / (STDDEV_POP(a.day_return) * STDDEV_POP(b.day_return)), 2) AS correlation
FROM returns a
JOIN returns b ON b.trade_date = a.trade_date AND b.ticker > a.ticker
WHERE a.day_return IS NOT NULL AND b.day_return IS NOT NULL
GROUP BY a.ticker, b.ticker;

-- Q29: Risk-return summary dashboard (one row per stock — the executive view)
WITH daily AS (
  SELECT p.company_id, p.trade_date,
         p.close_price / LAG(p.close_price) OVER (PARTITION BY p.company_id ORDER BY p.trade_date) - 1 AS day_return
  FROM fact_prices p
)
SELECT c.ticker,
       ROUND(AVG(d.day_return) * 252 * 100, 1) AS annual_return_pct,
       ROUND(STDDEV_POP(d.day_return) * SQRT(252) * 100, 1) AS annual_risk_pct,
       ROUND(AVG(d.day_return) * 252 / (STDDEV_POP(d.day_return) * SQRT(252)), 2) AS return_per_unit_risk
FROM daily d
JOIN dim_companies c ON c.company_id = d.company_id
WHERE d.day_return IS NOT NULL
GROUP BY c.ticker;

-- Q30: THE GRAND FINALE — full company scorecard (prices + fundamentals in one view)
WITH latest_price AS (
  SELECT company_id, close_price
  FROM fact_prices p
  WHERE trade_date = (SELECT MAX(trade_date) FROM fact_prices WHERE company_id = p.company_id)
),
latest_fund AS (
  SELECT company_id, revenue, net_income, free_cash_flow
  FROM fact_fundamentals
  WHERE fiscal_year = (SELECT MAX(fiscal_year) FROM fact_fundamentals)
),
first_fund AS (
  SELECT company_id, revenue
  FROM fact_fundamentals
  WHERE fiscal_year = (SELECT MIN(fiscal_year) FROM fact_fundamentals)
),
metrics AS (
  SELECT p.company_id,
         p.close_price,
         f.net_income / f.revenue * 100 AS net_margin_pct,
         f.free_cash_flow / f.revenue * 100 AS fcf_margin_pct,
         (POW(f.revenue / ff.revenue, 1.0 / 9) - 1) * 100 AS rev_cagr_pct
  FROM latest_price p
  JOIN latest_fund f ON f.company_id = p.company_id
  JOIN first_fund ff ON ff.company_id = p.company_id
)
SELECT c.ticker,
       c.company_name,
       c.sector,
       m.close_price AS latest_price,
       ROUND(m.net_margin_pct, 1) AS net_margin_pct,
       ROUND(m.fcf_margin_pct, 1) AS fcf_margin_pct,
       ROUND(m.rev_cagr_pct, 1) AS revenue_cagr_pct
FROM metrics m
JOIN dim_companies c ON c.company_id = m.company_id
ORDER BY m.net_margin_pct DESC;
