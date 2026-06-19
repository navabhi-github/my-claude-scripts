"""
2026 Long-Horizon (6mo+) Blended-Edge Stock Screener
=====================================================
Thesis: classic TA (RSI/MACD/MA-crosses) has decayed because the marginal
buyer in 2026 is mechanical (passive flows, model-driven factor rotation,
systematic vol-targeting) rather than a human reading a chart. At a 6mo+
horizon the edges that persist are STRUCTURAL, not tactical:

  1. TREND PERSISTENCE   - 6-12m momentum, the single most-robust anomaly,
                           but de-noised (skip most-recent month to dodge
                           short-term reversal).
  2. FLOW / SUPPLY       - share-count trend (buybacks shrink float) +
                           relative-strength vs benchmark (proxy for net
                           passive demand into the name).
  3. REVISION TREND      - direction & stability of fundamentals (here:
                           trailing earnings/FCF slope). Real money front-
                           runs estimate revisions.
  4. POSITIONING EXTREME - mean-reversion guardrail: don't buy names that
                           are 3-sigma stretched; crowded longs unwind over
                           months. This is a FILTER, not a signal.
  5. REGIME GATE         - only take longs when the broad market is above
                           its own 200d line (risk-on). Long-horizon
                           momentum gets killed in bear regimes.

Score = weighted z-score blend, gated by regime + positioning filter.
Confidence is reported as out-of-sample hit-rate with confidence INTERVALS,
never as a point claim of certainty.
"""
import numpy as np
import pandas as pd

# ----------------------------------------------------------------------
# DATA LAYER  --  swap this one function for your real feed (yf, Polygon,
# Norgate, Bloomberg). Everything downstream is feed-agnostic.
# ----------------------------------------------------------------------
def load_prices(tickers, start, end, seed=7):
    """Synthetic regime-switching daily prices + crude fundamentals.
    Replace with: yf.download(...) -> returns dict of DataFrames."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, end)
    n = len(dates)
    out = {}
    # market regime path (shared) : 0=bull,1=bear, persistent
    regime = np.zeros(n, dtype=int)
    p_switch = 0.004
    for t in range(1, n):
        regime[t] = regime[t-1]
        if rng.random() < p_switch:
            regime[t] = 1 - regime[t-1]
    mkt_drift = np.where(regime == 0, 0.0006, -0.0009)
    mkt_vol   = np.where(regime == 0, 0.008, 0.018)
    mkt_ret = mkt_drift + mkt_vol * rng.standard_normal(n)
    mkt = 100 * np.exp(np.cumsum(mkt_ret))

    for tk in tickers:
        beta = rng.uniform(0.6, 1.6)
        alpha = rng.normal(0.0002, 0.0004)   # persistent quality/drift
        idio_vol = rng.uniform(0.010, 0.022)
        r = alpha + beta * mkt_ret + idio_vol * rng.standard_normal(n)
        px = 50 * np.exp(np.cumsum(r))
        # fundamentals: slow earnings path correlated w/ alpha + share count
        eps = np.cumsum(rng.normal(alpha*50, 0.02, n)) + 5
        shares = 1e9 * np.exp(-np.cumsum(rng.normal(0.00005 if alpha>0 else -0.00002, 0.0001, n)))
        out[tk] = pd.DataFrame({'close': px, 'eps_ttm': eps, 'shares': shares}, index=dates)
    out['__MKT__'] = pd.DataFrame({'close': mkt}, index=dates)
    return out

# ----------------------------------------------------------------------
# FACTOR LAYER
# ----------------------------------------------------------------------
def zscore(s):
    return (s - s.mean()) / (s.std(ddof=0) + 1e-9)

def compute_factors(data, asof):
    mkt = data['__MKT__']['close']
    rows = []
    for tk, df in data.items():
        if tk == '__MKT__': continue
        if asof not in df.index: continue
        i = df.index.get_loc(asof)
        if i < 252: continue
        px = df['close']
        # 1. trend persistence: 12m mom skipping last 21d
        mom = px.iloc[i-21] / px.iloc[i-252] - 1
        # 2a. relative strength vs market, 6m
        rs = (px.iloc[i]/px.iloc[i-126]) / (mkt.iloc[i]/mkt.iloc[i-126]) - 1
        # 2b. float shrink (buyback) over 6m  (negative share growth = good)
        shr = -(df['shares'].iloc[i] / df['shares'].iloc[i-126] - 1)
        # 3. revision/earnings slope, 6m, normalized
        eps = df['eps_ttm']
        rev = (eps.iloc[i] - eps.iloc[i-126]) / (abs(eps.iloc[i-126]) + 1e-9)
        # 4. positioning extreme: distance from 200d in vol units
        ma200 = px.iloc[i-200:i].mean()
        sd = px.iloc[i-200:i].std(ddof=0)
        stretch = (px.iloc[i] - ma200) / (sd + 1e-9)
        rows.append({'ticker': tk, 'mom': mom, 'rs': rs, 'buyback': shr,
                     'rev': rev, 'stretch': stretch, 'px': px.iloc[i]})
    f = pd.DataFrame(rows).set_index('ticker')
    # regime gate
    mi = mkt.index.get_loc(asof)
    regime_on = mkt.iloc[mi] > mkt.iloc[mi-200:mi].mean()
    return f, regime_on

def score(f, regime_on):
    s = pd.DataFrame(index=f.index)
    s['z_mom']     = zscore(f['mom'])
    s['z_rs']      = zscore(f['rs'])
    s['z_buyback'] = zscore(f['buyback'])
    s['z_rev']     = zscore(f['rev'])
    w = {'z_mom':0.35,'z_rs':0.25,'z_buyback':0.15,'z_rev':0.25}
    raw = sum(s[c]*wt for c,wt in w.items())
    # positioning filter: penalize 3-sigma stretched names hard
    pen = np.where(f['stretch'].abs() > 2.5, -1.5, 0.0)
    raw = raw + pen
    # regime gate: if risk-off, no long signal passes
    if not regime_on:
        raw = raw - 5.0
    out = f.copy()
    out['score'] = raw
    out['pass'] = (out['score'] > 0.5) & (f['stretch'].abs() <= 2.5) & regime_on
    return out.sort_values('score', ascending=False)
