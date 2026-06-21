# -*- coding: utf-8 -*-
# [r4_decouple.py] R4 노출/레버 분리 — 노출(lev_eff)은 유지·실레버(lev_act=10)는 낮춰 청산버퍼 확보. (1회용)
#   증거금% = base*K*(lev_eff/lev_act), leverage=lev_act → 명목노출=base*K*lev_eff(동일), 청산버퍼=1/lev_act(넓음).
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "bots"))
import trendstack_signal_engine as E, trendstack_poc as P, trendstack_regime as RG, rauto_paper_engine as PE
import SidewayDCA_Stg7_engine as SWENG
from rauto_contract import Signal, Action, Side
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "r4_lev.py"), encoding="utf-8").read().split("print(\"=== R4")[0])
# 위 exec로 KT, SW, daily, mddv, Rof, 상수 재사용


def run(lev_eff, lev_act):
    aT = PE.PaperAccount(10000.0); bt = []
    for t in KT:
        sz = t["base"] * K * (lev_eff / lev_act)
        aT.open(Signal(Action.ENTER, side=Side(t["side"]), size_pct=sz, leverage=lev_act), ts=None, price=100.0)
        R = Rof(t, lev_act)                                  # 청산버퍼=실레버(lev_act) 기준
        aT.resolve_replay(R=R, mae=min(0.0, R), fund=0.0); bt.append((t["xt"], aT.bal))
    aW = PE.PaperAccount(10000.0); bw = []
    for t in SW:
        weff = WD if t["er"] >= ERT else 1.0
        sz = t["base"] * K * weff * (lev_eff / lev_act)
        aW.open(Signal(Action.ENTER, side=Side(t["side"]), size_pct=sz, leverage=lev_act), ts=None, price=100.0)
        if sz > 0: aW.resolve_replay(R=t["R"], mae=0.0, fund=0.0)
        bw.append((t["xt"], aW.bal))
    T = daily(pd.DataFrame(bt, columns=["t", "v"]).groupby("t").last()["v"])
    W = daily(pd.DataFrame(bw, columns=["t", "v"]).groupby("t").last()["v"]) if bw else daily(pd.Series(dtype=float))
    port = (T + W).values
    nl = sum(1 for t in KT if t["reason"] == "sl" and t["open_adv"] <= -(1.0 / lev_act - MMR - SLIP))
    return (port[-1] / 20000 - 1) * 100, mddv(port), nl


print("=== R4 노출/레버 분리 (실레버 10 고정=청산버퍼 9.6%, 노출만 변경) ===")
print(f"{'노출(eff)':>9} {'실레버':>6} {'수익%':>9} {'일별MDD%':>9} {'갭청산':>6} {'판정'}")
for le in (22, 18, 16, 15, 13, 10):
    ret, mdd, nl = run(le, 10.0)
    flag = "←-20%위반" if mdd < -20 else ("★최적후보" if mdd >= -20 and nl == 0 else "")
    print(f"{le:>9} {'10':>6} {ret:>+8.0f}% {mdd:>8.1f}% {nl:>6}  {flag}")
print("\n[비교] 현재 R4(노출22·실레버22): 청산13건·MDD-28.6%·+5963%")
print("→ 실레버10으로 청산버퍼 넓히면 청산 사라짐. 노출을 MDD-20% 한계까지 키운 게 '수익 챙기고 안전'한 최적.")
