# -*- coding: utf-8 -*-
# [Stg5b] 청산을 '가격기준'으로 재분류: early_tp 익절(+1% 목표 도달=지정가 메이커 가능) vs fibstop 손절/되돌림(시장가 테이커).
import os, sys, json
import numpy as np, pandas as pd
ROOT = r"D:\ML\RfRauto"
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
sys.path.insert(0, os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp"))
from path_finder import ensure_paths; ensure_paths()
from fib_replay_1m import load_1m, load_funding
import back2tv_REVoi as B2
OUT = os.path.join(ROOT, r"00_WorkHstr\BackTest_Output\260628_05_LimitCostQuant")
PJSON = os.path.join(ROOT, r"03_IDEA4Bot\260623_07_RfRautoAlphaUp\back2tv_rev_winners.json")
START = pd.Timestamp("2024-01-01"); MK, TK, SPRD = 0.0002, 0.0005, 0.0001
lines=[]
def log(s=""): print(s, flush=True); lines.append(str(s))
p_base = json.load(open(PJSON))["REV_MDD25_36mo"]["p"]
combo_p = {**p_base, "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0}
d1m = load_1m(); fund = load_funding()
T = B2.rev_trades(d1m, fund, combo_p)
Tp = T[pd.to_datetime(T["et"]) >= START].copy()
# 가격기준 청산수익률 (side 반영, 무비용 방향)
Tp["xret"] = Tp["side"] * (Tp["exit"]/Tp["entry"] - 1.0)
# early_tp 도달 = xret이 +1%(0.01) 근처 = 익절 지정가(메이커 가능). 그 외 = 손절/되돌림 fibstop(테이커).
Tp["is_earlytp"] = (Tp["xret"] >= 0.0095) & (Tp["xret"] <= 0.0115)
n=len(Tp); n_tp=int(Tp["is_earlytp"].sum())
log("="*78); log("COMBO 청산 가격기준 재분류 (post-2024)  early_tp익절(메이커가능) vs fibstop(테이커)"); log("="*78)
log(f"거래 {n} · early_tp 익절도달(+1%) = {n_tp} ({n_tp/n*100:.0f}%) · 나머지 fibstop = {n-n_tp} ({(n-n_tp)/n*100:.0f}%)")
log(f"  익절도달 거래 평균 xret = {Tp.loc[Tp.is_earlytp,'xret'].mean()*1e4:.0f}bp · 나머지 평균 xret = {Tp.loc[~Tp.is_earlytp,'xret'].mean()*1e4:.0f}bp")
# 비용: 진입 메이커2 + 청산(현재엔진=전부 테이커) vs 개선(early_tp만 메이커)
def cost(scn):
    c=0.0
    for tp in Tp["is_earlytp"]:
        entry=MK
        if scn=="now": x=TK+SPRD                       # 현재 엔진: 전부 fibstop=테이커
        elif scn=="improved": x=(MK if tp else TK+SPRD) # 개선: early_tp만 메이커 지정가
        c+=entry+x
    return c/n*1e4
now=cost("now"); imp=cost("improved")
log(f"\n[평균 왕복비용 bp] 현재엔진(청산 전부 테이커)={now:.2f} · 개선(early_tp 메이커 라우팅)={imp:.2f} · 절감={now-imp:.2f}bp/왕복")
log(f"  → 즉 ★실제 절감여지 = early_tp 익절 {n_tp/n*100:.0f}%를 지정가로 = {now-imp:.2f}bp/왕복 (3bp×익절비율)")
mean_abs=np.abs(Tp["R"].values).mean()*1e4
log(f"  → 거래당 |R|평균 {mean_abs:.0f}bp 대비 절감 {now-imp:.2f}bp = 손익의 {(now-imp)/mean_abs*100:.1f}%")
log(f"\n[정직 경고] early_tp 메이커 청산엔 ⒜미체결(가격이 +1% 못닿고 되돌림→이익반납) ⒝역선택(−0.3~0.8bp, Albers2025 Binance실측) 리스크.")
log(f"  순절감은 위 {now-imp:.2f}bp보다 작아짐. 손절(fibstop {(n-n_tp)/n*100:.0f}%)은 갭리스크로 지정가 불가=영구 테이커.")
open(os.path.join(OUT,"260628_05_LimitCostQuant2_analysis.txt"),"w",encoding="utf-8").write("\n".join(lines))
log("[OK]")
