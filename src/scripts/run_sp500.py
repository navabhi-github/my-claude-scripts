"""
Run the screener on the CURRENT S&P 500 (auto-pulled, ~500 names).

    python3 run_sp500.py

Fixes the tiny-universe problem from the 20-name run. Pulls the live
constituent list from GitHub, then prices+fundamentals from yfinance.

IMPORTANT CAVEATS (read these before trusting the numbers):
- This is CURRENT membership, not point-in-time. Names that were dropped
  from the index over the years (the losers) aren't here, so a residual
  survivorship bias remains. It's far better than 20 hand-picked names,
  but it still flatters results somewhat. For a fully clean test you'd
  need point-in-time constituents (see README).
- ~500 names with fundamentals on yfinance is SLOW (20-45+ min) and some
  names will fail to load. The code skips failures and continues.
- yfinance may rate-limit a 500-name pull. If you see many failures,
  raise `sleep` or run in two halves.

Tip: run once, it caches prices to disk (prices_cache.pkl), so re-runs
of the analysis are instant. Delete the cache to refresh data.
"""
import os, pickle, urllib.request, csv, time
import numpy as np, pandas as pd

import screener
from load_prices_yfinance import load_prices as real_load
screener.load_prices = real_load
from screener import compute_factors, score
from backtest import fwd_return, wilson

SP500_URL = "https://raw.githubusercontent.com/Ate329/top-us-stock-tickers/main/tickers/sp500.csv"
CACHE = "prices_cache.pkl"
START, END = "2015-01-01", "2025-12-31"
TOP_N = None   # set to e.g. 200 to test only the largest 200 (faster)

def get_sp500():
    with urllib.request.urlopen(SP500_URL, timeout=30) as r:
        rows = list(csv.DictReader(line.decode("utf-8") for line in r))
    syms = [x["symbol"].replace(".", "-") for x in rows]  # yfinance uses BRK-B
    return syms[:TOP_N] if TOP_N else syms

def get_data(tickers):
    if os.path.exists(CACHE):
        print(f"Loading cached data from {CACHE} (delete it to refresh)...")
        with open(CACHE, "rb") as f:
            return pickle.load(f)
    print(f"Pulling {len(tickers)} names from yfinance. This takes a while.\n")
    data = real_load(tickers, START, END)
    with open(CACHE, "wb") as f:
        pickle.dump(data, f)
    print(f"\nCached to {CACHE} for fast re-runs.")
    return data

def main():
    tickers = get_sp500()
    print(f"Universe: {len(tickers)} current S&P 500 names\n")
    data = get_data(tickers)
    loaded = [k for k in data if k != "__MKT__"]
    print(f"\nSuccessfully loaded {len(loaded)} names + benchmark.\n")

    # ---- live screen as of latest date ----
    latest = data["__MKT__"].index.max()
    f, regime_on = compute_factors(data, latest)
    ranked = score(f, regime_on)
    passing = ranked[ranked["pass"]]
    print("="*70)
    print(f"LIVE SCREEN as of {latest.date()}  "
          f"(regime: {'RISK-ON' if regime_on else 'RISK-OFF'})")
    print("="*70)
    print(f"{len(passing)} of {len(f)} names pass.\n")
    print("Top 20 by score:")
    cols = ["score","mom","rs","buyback","rev","stretch","pass"]
    with pd.option_context("display.float_format", lambda x: f"{x:+.3f}"):
        print(ranked[cols].head(20).to_string())

    # ---- walk-forward backtest ----
    print("\nRunning walk-forward backtest...\n")
    dates = data["__MKT__"].index
    pts = dates[252:-126:63]
    pr, ur = [], []
    for asof in pts:
        f, reg = compute_factors(data, asof)
        if len(f) < 20: continue
        r = score(f, reg)
        for tk in r[r["pass"]].index:
            v = fwd_return(data, tk, asof)
            if not np.isnan(v): pr.append(v)
        for tk in f.index:
            v = fwd_return(data, tk, asof)
            if not np.isnan(v): ur.append(v)

    def summ(name, a):
        a = np.array(a)
        if not len(a): print(f"{name}: no trades"); return None
        w=(a>0).sum(); lo,hi=wilson(w,len(a))
        print(f"{name:10s} n={len(a):5d} hit={w/len(a):5.1%} "
              f"[{lo:.1%}-{hi:.1%}] mean={a.mean():+.2%} med={np.median(a):+.2%}")
        return (w/len(a), lo, hi, a.mean())

    print("="*70)
    s = summ("SCREENER", pr)
    u = summ("universe", ur)
    print("="*70)
    if s and u:
        edge = s[0]-u[0]
        sep = "NON-overlapping" if s[1] > u[2] or s[2] < u[1] else "OVERLAPPING"
        print(f"\nHit-rate edge: {edge:+.1%}  | CIs are {sep}")
        print("Edge is real ONLY if the screener CI sits ABOVE the universe CI.")
        print("Overlapping intervals = no demonstrated selection edge.")
    print("\nStill not 100%, and that's correct. See overfit_demo.py.")

if __name__ == "__main__":
    main()
