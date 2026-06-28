# -*- coding: utf-8 -*-
# [Stg9] 슬리피지 임계선(인내선) 스윕 — COMBO@ETF, held-out OOS 수익률이 0 되는 추가슬립 찾기.
#   현재 R엔 기본 8bp 비용 반영. 그 위에 시장청산(fibstop=전부 taker) 추가슬립 slip_bp를 빼고 OOS 수익 재계산.
#   veri_edge.VeriEdge.heldout_oos 사용(엔진 재활용).
import os, sys, json
import numpy as np, pandas as pd
ROOT = r"D:\ML\RfRauto"
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
sys.path.insert(0, os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp"))
from path_finder import ensure_paths; ensure_paths()
from fib_replay_1m import load_1m, load_funding
import back2tv_REVoi as B2
from veri_edge import VeriEdge
OUT = os.path.join(ROOT, r"00_WorkHstr\BackTest_Output\260628_09_SlipTolerance"); os.makedirs(OUT, exist_ok=True)
lines=[]
def log(s=""): print(s, flush=True); lines.append(str(s))
p = {**json.load(open(os.path.join(ROOT, r"03_IDEA4Bot\260623_07_RfRautoAlphaUp\back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"],
     "tp_frac":0.7, "early_tp_pct":0.01, "early_frac":1.0}
d1m, fund = load_1m(), load_funding()
led = B2.rev_trades(d1m, fund, p)   # COMBO@ETF 원장(전부 fibstop=시장청산)
log("="*72); log("슬리피지 인내선 스윕 — COMBO@ETF · held-out OOS(2025~26·lev3/sz75) 수익률(%)"); log("="*72)
log(f"{'추가슬립':>8s} | {'OOS test 수익%':>14s} {'MDD%':>7s} | 비고")
log("-"*60)
prev=None; cross=None
for sb in [0,5,10,15,20,30,50]:
    adj = led.copy(); adj["R"] = adj["R"] - sb/1e4     # 시장청산 추가슬립(왕복 한 번)
    oos = VeriEdge(adj).heldout_oos(size_pct=75, lev=3)["test_OOS"]
    note = "기준(현 모델)" if sb==0 else ""
    if prev is not None and prev>0 and oos["수익%"]<=0 and cross is None: cross=sb
    log(f"{sb:>6d}bp | {oos['수익%']:>+13,}% {oos['MDD%']:>6.1f}% | {note}")
    prev=oos["수익%"]
log("-"*60)
log(f"[인내선] OOS 수익이 양수→0 이하로 꺾이는 추가슬립 ≈ {cross if cross else '>50'}bp 부근")
log("★주의(메타인지): 이건 '평균 추가슬립' 임계선. flash-crash 꼬리(스톱 갭관통·유동성공백)는 어떤 평균슬립으로도 미반영 — 그건 슬립모델이 아니라 레버상한·서킷브레이커로만 방어.")
open(os.path.join(OUT,"260628_09_SlipTolerance_analysis.txt"),"w",encoding="utf-8").write("\n".join(lines))
log("[OK] -> "+OUT)
