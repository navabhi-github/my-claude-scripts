"""
Demonstrate WHY chasing 100% is self-defeating.
We let an 'optimizer' tune thresholds greedily on world seed=7 (in-sample),
then test the SAME tuned params on unseen worlds. Watch IS soar, OOS rot.
"""
import numpy as np, pandas as pd
from screener import load_prices, compute_factors, zscore
from backtest import fwd_return

def score_param(f, regime_on, thr, pen_k, w):
    s = pd.DataFrame(index=f.index)
    s['z_mom']=zscore(f['mom']); s['z_rs']=zscore(f['rs'])
    s['z_buyback']=zscore(f['buyback']); s['z_rev']=zscore(f['rev'])
    raw = sum(s[c]*w[c] for c in w)
    raw = raw + np.where(f['stretch'].abs()>pen_k, -1.5, 0)
    if not regime_on: raw -= 5
    out=f.copy(); out['score']=raw
    out['pass']=(out['score']>thr)&(f['stretch'].abs()<=pen_k)&regime_on
    return out

def evaluate(seed, thr, pen_k, w):
    tickers=[f'S{i:02d}' for i in range(60)]
    data=load_prices(tickers,'2015-01-01','2024-12-31',seed=seed)
    dates=data['__MKT__'].index
    rets=[]
    for asof in dates[252:-126:63]:
        f,reg=compute_factors(data,asof)
        if len(f)<10: continue
        r=score_param(f,reg,thr,pen_k,w)
        for tk in r[r['pass']].index:
            v=fwd_return(data,tk,asof)
            if not np.isnan(v): rets.append(v)
    a=np.array(rets)
    if len(a)==0: return 0.5,0,0
    return (a>0).mean(), a.mean(), len(a)

# greedy 'optimization' on seed=7 only
best=None
grid_thr=[0.3,0.5,0.8,1.2,1.6,2.0]
grid_pen=[1.5,2.0,2.5,3.0]
weight_sets=[
    {'z_mom':.35,'z_rs':.25,'z_buyback':.15,'z_rev':.25},
    {'z_mom':.7,'z_rs':.1,'z_buyback':.1,'z_rev':.1},
    {'z_mom':.1,'z_rs':.1,'z_buyback':.7,'z_rev':.1},
    {'z_mom':.25,'z_rs':.25,'z_buyback':.25,'z_rev':.25},
    {'z_mom':.9,'z_rs':.05,'z_buyback':.0,'z_rev':.05},
]
for thr in grid_thr:
  for pen in grid_pen:
    for w in weight_sets:
      hit,mean,n=evaluate(7,thr,pen,w)
      if n>=15 and (best is None or hit>best[0]):
        best=(hit,mean,n,thr,pen,w)
print("BEST PARAMS FOUND BY TUNING ON SEED=7 (in-sample):")
print(f"  in-sample hit={best[0]:.1%} mean={best[1]:+.2%} n={best[2]} "
      f"thr={best[3]} pen={best[4]}\n  weights={best[5]}")
print("\nNOW APPLY THOSE EXACT PARAMS TO UNSEEN WORLDS (out-of-sample):")
oos=[]
for sd in [13,21,42,99]:
    hit,mean,n=evaluate(sd,best[3],best[4],best[5])
    oos.append((hit,mean,n))
    print(f"  seed={sd}: hit={hit:.1%} mean={mean:+.2%} n={n}")
import numpy as np
oh=np.mean([x[0] for x in oos])
print(f"\n  --> IS hit {best[0]:.1%}  vs  OOS hit {oh:.1%}   "
      f"(the gap = overfit tax)")
