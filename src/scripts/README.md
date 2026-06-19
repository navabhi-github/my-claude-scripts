# 2026 Long-Horizon Blended-Edge Screener

## Why classic TA decayed
At a 6mo+ horizon, RSI/MACD/MA-cross signals are noise. The 2026 marginal
buyer is mechanical: passive inflows, factor-rotation models, vol-targeting.
This screener targets the edges that *persist* at that horizon.

## The five components
1. **Trend persistence** (35%) — 12m momentum, skip last 21d to dodge reversal.
2. **Flow/supply** (40%) — 6m relative strength vs benchmark + float-shrink (buybacks).
3. **Revision trend** (25%) — slope of trailing earnings/FCF.
4. **Positioning filter** — drop names >2.5σ stretched from 200d (crowded longs unwind).
5. **Regime gate** — no longs unless market > its own 200d line.

Score = weighted z-blend, gated by filter + regime.

## Honest backtest result (5 synthetic worlds, walk-forward, no lookahead)
| Strategy | n | Hit-rate (6m) | 95% CI | Mean ret |
|---|---|---|---|---|
| **Screener** | 1053 | **62.7%** | 59.7–65.5 | +10.8% |
| Random (in-regime) | 1141 | 58.5% | 55.7–61.4 | +7.0% |
| Universe avg | 10800 | 52.0% | 51.0–52.9 | +3.9% |

Real, statistically-significant edge over the universe. Edge over
random-in-the-same-regime is positive but modest — meaning much of the
raw outperformance is the regime gate (any long-only book benefits from
sitting out bear markets), not stock selection per se.

## Why there is NO 100% version
`overfit_demo.py` tunes parameters greedily on one world: in-sample hit
jumps to 73.4%, but the SAME params score 62.1% out-of-sample — an 11-pt
"overfit tax." Iterating toward 100% just inflates the in-sample number
while OOS performance flatlines or decays. A screener claiming certainty
is overfit by construction.

## To run on real data
Replace `load_prices()` in screener.py with your feed (yfinance, Polygon,
Norgate, Bloomberg) returning per-ticker DataFrames with columns
[close, eps_ttm, shares] plus a '__MKT__' benchmark. Everything downstream
is feed-agnostic. Then: `python3 backtest.py`.

## Files
- screener.py     — factor + scoring engine (the system)
- backtest.py     — walk-forward tester w/ Wilson CIs + baselines
- overfit_demo.py — proves the 100%-chase fails OOS

---

## Running on REAL data (yfinance — free, no API key)

```bash
pip install yfinance pandas numpy
python3 run_real.py
```

`run_real.py` swaps the synthetic loader for `load_prices_yfinance.py`,
then (1) prints TODAY's live screen for the universe and (2) runs a
walk-forward backtest on that real universe.

- Edit the `UNIVERSE` list at the top of `run_real.py` to your names.
- Fundamentals (eps_ttm, shares) come from yfinance quarterly statements,
  forward-filled to daily. Missing fundamentals neutralize those two
  factors for that name rather than crashing.
- yfinance is a scraper: a per-ticker sleep prevents rate-limit blocks.
  If you see "no price data" errors, raise `sleep` in load_prices().

### Honest expectations on real data
- Real hit-rates WILL differ from the synthetic 62.7%. Treat that number
  as a demo of the machinery, not a forecast.
- A 20-name universe gives WIDE confidence intervals. For numbers you'd
  trust, screen 100+ names so the CIs tighten.
- Still no 100%. See overfit_demo.py for why that target is a trap.

## File map
- screener.py              — factor + scoring engine
- backtest.py              — synthetic-world walk-forward + CIs
- overfit_demo.py          — proves the 100%-chase fails out-of-sample
- load_prices_yfinance.py  — REAL data loader (drop-in)
- run_real.py              — one-command real-data run (live screen + backtest)

---

## Running on the full S&P 500 (auto-pulled)

```bash
python3 run_sp500.py
```

Pulls the current ~503 S&P 500 names automatically from GitHub, then
prices+fundamentals from yfinance. Caches to `prices_cache.pkl` so
re-runs are instant (delete the cache to refresh data).

- Slow first run (20-45+ min for ~500 names with fundamentals).
- Set `TOP_N = 200` near the top to test only the largest 200 (faster).
- Some names will fail to load; the run skips them and continues.

### The survivorship-bias caveat (important)
`run_sp500.py` uses CURRENT index membership. Names dropped from the
index over the years (the losers) are NOT in the pool, so results still
carry a residual upward bias. This is a big improvement over a hand-
picked 20-name basket, but it is NOT a fully clean test.

For a clean test you need POINT-IN-TIME constituents (who was actually
in the index on each historical date). Source:
  https://github.com/fja05680/sp500  (historical components since 1996)
Wiring that in is a further upgrade if the current-500 result looks
promising enough to justify the effort.

### How to read the verdict
The screener has a REAL selection edge only if its hit-rate confidence
interval sits ABOVE the universe's interval (non-overlapping). If the
intervals overlap, the screener has not demonstrated stock-selection
skill on this universe — the method is no better than buying the whole
list. A higher MEAN return with a lower/equal HIT-RATE usually means a
few fat winners are carrying the average — concentration, not edge.

## File map
- screener.py              — factor + scoring engine
- backtest.py              — synthetic-world walk-forward + CIs
- overfit_demo.py          — proves the 100%-chase fails out-of-sample
- load_prices_yfinance.py  — real data loader (drop-in)
- run_real.py              — small custom-universe run
- run_sp500.py             — full S&P 500 auto-pull run (recommended)
