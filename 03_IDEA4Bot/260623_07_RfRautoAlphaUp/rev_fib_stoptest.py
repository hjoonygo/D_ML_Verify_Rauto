# -*- coding: utf-8 -*-
# [rev_fib_stoptest.py] 확인 — REV(reversion)에 피보 스텝업이 '초기손절만 안 조이면' 알파를 내는가?(캡틴 주장 검증)
#   가설: 내 REV붕괴(+12%/-30%)는 엔진 초기손절 1%(7h용)를 8h에 그대로 써서 churn. 초기손절 넓히면 Fib가 산다?
#   거친 확인(펀딩 실값·현실체결 정밀화 前, 비용 8bp 평. 1m 청산체결·순차·동치앵커는 유지).
import os, sys, numpy as np, pandas as pd
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import trendstack_signal_engine as TS
import vol_sizing_compare as V
from fib_replay_1m import load_1m, fib_loop, sized, mstat, cpcv_p25

d1m = load_1m()
df8h = TS.resample_tf(d1m[["open", "high", "low", "close"]], 480); sig8 = TS.compute_signals(df8h)
_, S, _ = V.build(V.find_data())
sidx = S.index.tz_localize(None)
side8 = pd.Series(S["side"].values, index=sidx).reindex(df8h.index, fill_value=0).values.astype(int)
oi8 = pd.Series(S["oi_z"].values, index=sidx).reindex(df8h.index).values

print("=" * 84)
print("REV 피보스텝업 초기손절 민감도 — '진입만 하면 Fib가 알파' 주장 확인 (8h, 1m청산, 8bp)")
print("=" * 84)
print(f"{'초기손절':<16}{'거래':>6}{'승률':>6}{'거래평균%':>9}{'월복리%':>9}{'MDD%':>8}{'CPCVp25':>9}")
print("-" * 84)
configs = [("고정 1%(엔진)", dict(init_sl_pct=1.0)),
           ("고정 2%", dict(init_sl_pct=2.0)),
           ("고정 3%", dict(init_sl_pct=3.0)),
           ("고정 5%", dict(init_sl_pct=5.0)),
           ("ATR×1.5", dict(init_atr_mult=1.5)),
           ("ATR×2.5", dict(init_atr_mult=2.5))]
for nm, kw in configs:
    T = fib_loop(df8h, sig8, d1m, ext_side=side8, use_trend_flip=False, fill_1m=True,
                 lev=1.0, cost=0.0008, tf_min=480, oi_arr=oi8, **kw)
    if len(T) < 10:
        print(f"{nm:<16} 거래 {len(T)} 부족"); continue
    Ts, mser = sized(T)
    allm = mser.index
    tot, mdd, _ = mstat(mser.values)
    p25, worst, neg = cpcv_p25(mser.values)
    print(f"{nm:<16}{len(T):>6}{100*(T.R>0).mean():>5.0f}%{T.R.mean()*100:>+9.3f}{tot:>+9.0f}{mdd:>+8.1f}{p25:>+9.1f}")
print("-" * 84)
print("[참고] 옛 REV(2%SL+3%트레일+maxhold, 회귀용): +127%/MDD-21.5%/CPCV거래Sharpe p25+0.35.")
print("[판정] Fib가 어느 초기손절서 옛 회귀청산(+127%)에 필적/초과하면 = 캡틴 주장(Fib 보편우월) 성립.")
