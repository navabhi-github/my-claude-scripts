"""
One-file entry point to run the screener on REAL yfinance data.
Run:  python3 run_real.py

This bypasses the need to edit screener.py — it monkeypatches the real
loader in, then runs both the backtest and prints TODAY's live screen.
"""
import screener
from load_prices_yfinance import load_prices as real_load

# swap synthetic loader for the real one across the whole pipeline
screener.load_prices = real_load

import numpy as np, pandas as pd
from screener import compute_factors, score

# ----- EDIT THIS UNIVERSE -----
UNIVERSE = ["AAPL","MSFT","NVDA","META","GOOGL","AMZN","DOCU","NOW",
            "CRM","ADBE","AMD","AVGO","ORCL","PLTR","SNOW","NET",
            "DDOG","CRWD","PANW","UBER"]
START, END = "2015-01-01", "2025-12-31"
# ------------------------------

print("Loading real data (this takes a few minutes — fundamentals are slow)...\n")
data = real_load(UNIVERSE, START, END)

# ---- live screen: score every name as of the most recent date ----
latest = data["__MKT__"].index.max()
f, regime_on = compute_factors(data, latest)
ranked = score(f, regime_on)

print("\n" + "="*70)
print(f"LIVE SCREEN as of {latest.date()}  (market regime: "
      f"{'RISK-ON' if regime_on else 'RISK-OFF — no longs pass'})")
print("="*70)
cols = ["score","mom","rs","buyback","rev","stretch","pass"]
with pd.option_context("display.float_format", lambda x: f"{x:+.3f}"):
    print(ranked[cols].to_string())

passing = ranked[ranked["pass"]].index.tolist()
print(f"\nNames passing the screen: {passing if passing else 'NONE'}")

# ---- optional: run the historical backtest on this real universe ----
print("\nRunning walk-forward backtest on the real universe...\n")
import backtest
# backtest.run() builds its own synthetic tickers; for real data we
# inline a minimal walk-forward here instead:
from backtest import fwd_return, wilson
dates = data["__MKT__"].index
pts = dates[252:-126:63]
pr, ur = [], []
for asof in pts:
    f, reg = compute_factors(data, asof)
    if len(f) < 5: continue
    r = score(f, reg)
    for tk in r[r["pass"]].index:
        v = fwd_return(data, tk, asof)
        if not np.isnan(v): pr.append(v)
    for tk in f.index:
        v = fwd_return(data, tk, asof)
        if not np.isnan(v): ur.append(v)

def summ(name, a):
    a = np.array(a)
    if not len(a): print(f"{name}: no trades"); return
    w = (a>0).sum(); lo,hi = wilson(w,len(a))
    print(f"{name:10s} n={len(a):4d} hit={w/len(a):5.1%} "
          f"[{lo:.1%}-{hi:.1%}] mean={a.mean():+.2%}")

print("="*70)
summ("SCREENER", pr)
summ("universe", ur)
print("="*70)
print("\nReminder: real hit-rates will differ from the synthetic 62.7%.")
print("A small universe = wide confidence intervals. Widen UNIVERSE for")
print("tighter, more trustworthy numbers.")
