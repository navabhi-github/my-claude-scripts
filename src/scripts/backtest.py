"""
Honest walk-forward backtest. Key anti-overfitting discipline:
  - Signal computed at time T using ONLY data up to T.
  - Forward return measured T -> T+126 bdays (~6 months), never peeked.
  - Report hit-rate WITH Wilson 95% confidence interval + base rate.
  - Compare screener picks vs (a) the universe average, (b) random picks.
  - No parameter is re-tuned to the test set. The numbers are what they are.
"""
import numpy as np, pandas as pd
from screener import load_prices, compute_factors, score

def wilson(k, n, z=1.96):
    if n == 0: return (0,0)
    p = k/n
    d = 1 + z*z/n
    c = p + z*z/(2*n)
    m = z*np.sqrt(p*(1-p)/n + z*z/(4*n*n))
    return ((c-m)/d, (c+m)/d)

def fwd_return(data, tk, asof, h=126):
    df = data[tk]; i = df.index.get_loc(asof)
    if i+h >= len(df): return np.nan
    return df['close'].iloc[i+h]/df['close'].iloc[i] - 1

def run(seed=7, n_tickers=60):
    tickers = [f'S{i:02d}' for i in range(n_tickers)]
    data = load_prices(tickers, '2015-01-01', '2024-12-31', seed=seed)
    dates = data['__MKT__'].index
    # rebalance points: every ~63 bdays, need 252 lookback + 126 forward
    pts = dates[252:-126:63]
    pick_rets, univ_rets, rand_rets = [], [], []
    n_pass_total, n_periods_riskon = 0, 0
    rng = np.random.default_rng(seed)
    for asof in pts:
        f, regime_on = compute_factors(data, asof)
        if len(f) < 10: continue
        ranked = score(f, regime_on)
        picks = ranked[ranked['pass']].index.tolist()
        if regime_on: n_periods_riskon += 1
        # universe & random baselines (same regime conditions for fairness)
        all_tk = f.index.tolist()
        for tk in picks:
            r = fwd_return(data, tk, asof)
            if not np.isnan(r): pick_rets.append(r)
        n_pass_total += len(picks)
        for tk in all_tk:
            r = fwd_return(data, tk, asof)
            if not np.isnan(r): univ_rets.append(r)
        for tk in rng.choice(all_tk, size=min(len(picks) if picks else 1,len(all_tk)), replace=False):
            r = fwd_return(data, tk, asof)
            if not np.isnan(r): rand_rets.append(r)
    return pick_rets, univ_rets, rand_rets, n_pass_total, len(pts), n_periods_riskon

def summarize(name, rets):
    a = np.array(rets)
    if len(a)==0:
        print(f"{name}: no trades"); return
    win = (a>0).sum()
    lo,hi = wilson(win, len(a))
    print(f"{name:16s} n={len(a):4d} | hit={win/len(a):5.1%} "
          f"[95% CI {lo:4.1%}-{hi:4.1%}] | mean={a.mean():+6.2%} "
          f"med={np.median(a):+6.2%} | sharpe~={a.mean()/(a.std()+1e-9):.2f}")

if __name__ == '__main__':
    print("="*78)
    print("WALK-FORWARD BACKTEST  (6-month forward returns, no lookahead)")
    print("="*78)
    allp, allu, allr = [], [], []
    for sd in [7, 13, 21, 42, 99]:   # 5 independent synthetic worlds
        p,u,r,npass,nper,nrisk = run(seed=sd)
        allp += p; allu += u; allr += r
        print(f"\n-- world seed={sd}: {npass} picks over {nper} rebalances "
              f"({nrisk} risk-on) --")
        summarize("  SCREENER", p)
        summarize("  universe", u)
        summarize("  random", r)
    print("\n" + "="*78)
    print("POOLED ACROSS ALL 5 WORLDS (the honest aggregate)")
    print("="*78)
    summarize("SCREENER", allp)
    summarize("universe", allu)
    summarize("random",   allr)
