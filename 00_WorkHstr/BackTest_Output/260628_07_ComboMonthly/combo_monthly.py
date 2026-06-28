# -*- coding: utf-8 -*-
# [Stg7] 새 규칙 데모: COMBO 종합 + post-2024(ETF후) 매월통계(수익률). lev3/size75 고정(exp=2.25).
import os, sys, json
import numpy as np, pandas as pd
ROOT = r"D:\ML\RfRauto"
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
sys.path.insert(0, os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp"))
from path_finder import ensure_paths; ensure_paths()
from fib_replay_1m import load_1m, load_funding
import back2tv_REVoi as B2
OUT = os.path.join(ROOT, r"00_WorkHstr\BackTest_Output\260628_07_ComboMonthly"); os.makedirs(OUT, exist_ok=True)
PJSON = os.path.join(ROOT, r"03_IDEA4Bot\260623_07_RfRautoAlphaUp\back2tv_rev_winners.json")
EXP = 0.75*3.0   # size75 x lev3
lines=[]
def log(s=""): print(s, flush=True); lines.append(str(s))
p = {**json.load(open(PJSON))["REV_MDD25_36mo"]["p"], "tp_frac":0.7, "early_tp_pct":0.01, "early_frac":1.0}
d1m=load_1m(); fund=load_funding()
T = B2.rev_trades(d1m, fund, p)
T["et"]=pd.to_datetime(T["et"]); T=T.sort_values("et").reset_index(drop=True)
Tp = T[T["et"]>=pd.Timestamp("2024-01-01")].copy()
Tp["m"]=Tp["et"].dt.strftime("%Y-%m"); Tp["sz"]=1+EXP*Tp["R"]

log("="*70); log("COMBO (early_tp1.0%) — 종합 + post-2024 매월통계 [lev3/size75, in-sample]"); log("="*70)
# 종합(post-2024)
tot = (Tp["sz"].prod()-1)*100; wr=(Tp["R"]>0).mean()*100
L=Tp[Tp.side==1]; S=Tp[Tp.side==-1]
log(f"\n[종합 post-2024] 거래 {len(Tp)} · 승률 {wr:.0f}% · 복리수익 {tot:+,.0f}% · 롱 {len(L)}건/숏 {len(S)}건")
# 매월
log(f"\n[post-2024 매월통계]")
log(f"{'년월':8s} {'거래':>4s} {'월수익%':>9s} {'누적%':>11s} {'롱수익%':>8s} {'숏수익%':>8s} {'양수?':>5s}")
log("-"*60)
eq=1.0
for m,g in Tp.groupby("m"):
    mret=(g["sz"].prod()-1)*100
    lg=g[g.side==1]; sg=g[g.side==-1]
    lret=(lg["sz"].prod()-1)*100 if len(lg) else 0.0
    sret=(sg["sz"].prod()-1)*100 if len(sg) else 0.0
    eq*=g["sz"].prod(); cum=(eq-1)*100
    log(f"{m:8s} {len(g):>4d} {mret:>+8.1f}% {cum:>+10,.0f}% {lret:>+7.1f}% {sret:>+7.1f}% {'O' if mret>0 else 'X':>5s}")
pos=sum((Tp.groupby('m').apply(lambda x:(x['sz'].prod()-1)>0, include_groups=False)))
nm=Tp["m"].nunique()
log("-"*60)
log(f"[매월 양수 점검] {nm}개월 중 양수 {pos}개월 ({pos/nm*100:.0f}%) — §0 '매월 양수' 목표")
log(f"\n★in-sample 월별(lev3). OOS 헤드라인=held-out test +1,522%(§ Stg6). live<백테.")
open(os.path.join(OUT,"260628_07_ComboMonthly_analysis.txt"),"w",encoding="utf-8").write("\n".join(lines))
log("[OK]")
