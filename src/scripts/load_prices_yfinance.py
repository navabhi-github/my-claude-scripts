"""
Real-data loader for the 2026 screener — drop-in replacement for the
synthetic load_prices() in screener.py.

Pulls from yfinance (free, no API key). Returns the EXACT structure the
rest of the pipeline expects:
    dict[ticker -> DataFrame(index=dates, cols=[close, eps_ttm, shares])]
    plus '__MKT__' -> DataFrame(cols=[close])

Fundamentals (eps_ttm, shares) are quarterly and forward-filled to daily.
Designed to degrade gracefully: if a name's fundamentals are missing,
those factors get neutralized (NaN) rather than crashing the run.

USAGE
-----
    from load_prices_yfinance import load_prices
    # then run backtest.py exactly as before — it imports load_prices
    # from screener. Easiest: in screener.py replace the synthetic
    # load_prices with `from load_prices_yfinance import load_prices`.

INSTALL
-------
    pip install yfinance pandas numpy

NOTES
-----
- yfinance is a scraper. If you screen a large universe, the per-ticker
  sleep below prevents rate-limit blocks. Bump it up if you see errors.
- Data is delayed ~15-20m intraday; irrelevant for a 6mo+ screen.
"""
import time
import warnings
import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    raise SystemExit("Run: pip install yfinance")

warnings.filterwarnings("ignore")


def _retry(fn, tries=3, pause=1.5):
    """Call fn() with simple retry/backoff for yfinance flakiness."""
    last = None
    for i in range(tries):
        try:
            r = fn()
            if r is not None and (not hasattr(r, "empty") or not r.empty):
                return r
        except Exception as e:
            last = e
        time.sleep(pause * (i + 1))
    if last:
        print(f"   (gave up after {tries} tries: {last})")
    return None


def _get_fundamentals(tk_obj, idx):
    """Return (eps_ttm_series, shares_series) aligned to daily index `idx`.
    Falls back to NaN series if data is unavailable, which neutralizes
    the revision/buyback factors for that name instead of crashing."""
    nan = pd.Series(np.nan, index=idx)

    # --- shares outstanding (for float-shrink / buyback factor) ---
    shares = nan.copy()
    try:
        sh = tk_obj.get_shares_full(start=idx.min(), end=idx.max())
        if sh is not None and len(sh):
            sh = sh[~sh.index.duplicated(keep="last")]
            sh.index = pd.to_datetime(sh.index).tz_localize(None)
            shares = sh.reindex(idx.union(sh.index)).sort_index().ffill().reindex(idx)
    except Exception:
        pass
    # fallback: single static sharesOutstanding from .info
    if shares.isna().all():
        try:
            so = tk_obj.info.get("sharesOutstanding")
            if so:
                shares = pd.Series(float(so), index=idx)
        except Exception:
            pass

    # --- TTM EPS (for earnings-revision factor) ---
    eps = nan.copy()
    try:
        qf = tk_obj.quarterly_income_stmt
        if qf is not None and "Diluted EPS" in qf.index:
            q = qf.loc["Diluted EPS"].dropna()
            q.index = pd.to_datetime(q.index).tz_localize(None)
            q = q.sort_index()
            ttm = q.rolling(4).sum()  # trailing-twelve-month
            eps = ttm.reindex(idx.union(ttm.index)).sort_index().ffill().reindex(idx)
    except Exception:
        pass
    if eps.isna().all():
        try:
            t = tk_obj.info.get("trailingEps")
            if t:
                eps = pd.Series(float(t), index=idx)
        except Exception:
            pass

    return eps, shares


def load_prices(tickers, start, end, benchmark="SPY", sleep=0.7, verbose=True):
    out = {}
    universe = list(tickers) + [benchmark]
    for n, tk in enumerate(universe, 1):
        is_mkt = tk == benchmark
        if verbose:
            print(f"[{n}/{len(universe)}] {tk} ...", flush=True)
        obj = yf.Ticker(tk)
        hist = _retry(lambda: obj.history(start=start, end=end, auto_adjust=True))
        if hist is None or hist.empty:
            print(f"   no price data for {tk}, skipping")
            time.sleep(sleep)
            continue
        hist.index = pd.to_datetime(hist.index).tz_localize(None)
        close = hist["Close"]

        if is_mkt:
            out["__MKT__"] = pd.DataFrame({"close": close})
        else:
            eps, shares = _get_fundamentals(obj, close.index)
            out[tk] = pd.DataFrame(
                {"close": close, "eps_ttm": eps, "shares": shares}
            )
        time.sleep(sleep)  # be polite to avoid rate-limit blocks
    if "__MKT__" not in out:
        raise RuntimeError(f"Benchmark {benchmark} failed to load — cannot run.")
    return out


if __name__ == "__main__":
    # quick smoke test
    data = load_prices(["AAPL", "MSFT", "NVDA"], "2015-01-01", "2024-12-31")
    for k, v in data.items():
        cols = list(v.columns)
        eps_ok = "eps_ttm" in v and v["eps_ttm"].notna().any()
        shr_ok = "shares" in v and v["shares"].notna().any()
        print(f"{k:8s} rows={len(v):5d} cols={cols} "
              f"eps={'Y' if eps_ok else 'n'} shares={'Y' if shr_ok else 'n'}")
