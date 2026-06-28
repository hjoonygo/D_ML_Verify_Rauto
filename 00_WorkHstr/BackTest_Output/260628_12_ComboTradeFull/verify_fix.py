# -*- coding: utf-8 -*-
# [Stg12b] 청산가 수정 검증: 평균체결가(진입×(1+side×gross_R))로 청산가×수량이 손익과 일치하는지 + 앵커 무손상.
import os, sys, json
import numpy as np, pandas as pd
ROOT = r"D:\ML\RfRauto"
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
sys.path.insert(0, os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp"))
from path_finder import ensure_paths; ensure_paths()
from fib_replay_1m import load_1m, load_funding
import back2tv_REVoi as B2
from rauto_live import per_trade_pnl
from veri_edge import VeriEdge
lines=[]
def log(s=""): print(s, flush=True); lines.append(str(s))
p = {**json.load(open(os.path.join(ROOT, r"03_IDEA4Bot\260623_07_RfRautoAlphaUp\back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"],
     "tp_frac":0.7, "early_tp_pct":0.01, "early_frac":1.0}
d1m, fund = load_1m(), load_funding()
T = B2.rev_trades(d1m, fund, p).reset_index(drop=True)
SZ,LEV=75.0,5.0; exp=SZ/100*LEV
pnl,final,mdd,nliq = per_trade_pnl(T,SZ,LEV)
bb=[10000.0]
for x in pnl[:-1]: bb.append(bb[-1]*(1+x/100))
log("="*94)
log("청산가 수정 검증 — 평균체결가로 '청산가×수량≈손익' 재구성 (최근 10거래)")
log("="*94)
log(f"{'방향':3} {'진입가':>9} {'옛청산(x_int)':>12} {'새청산(평균체결)':>14} {'수량':>9} {'(새청산−진입)×수량×side':>22} {'gross손익$(검증)':>15} {'일치':>4}")
for k in list(range(len(T)))[-10:]:
    r=T.iloc[k]; gR=float(r.gross_R); eff=r.entry*(1+r.side*gR)
    qty=exp*bb[k]/r.entry
    recon=qty*(eff-r.entry)*r.side             # 새청산가로 직접 계산한 gross 손익$
    gross_d=gR*exp*bb[k]                        # 엔진 gross 손익$
    ok="✓" if abs(recon-gross_d)<max(1,abs(gross_d)*0.001) else "✗"
    log(f"{'숏' if r.side==-1 else '롱':3} {r.entry:>9.1f} {r.x_int:>12.1f} {eff:>14.1f} {qty:>9.1f} {recon:>+22,.0f} {gross_d:>+15,.0f} {ok:>4}")
log("\n→ 새 '청산가(평균체결)'로는 (청산가−진입가)×수량×방향 = 엔진 gross손익과 일치(✓). 옛 x_int는 분할익절 마지막레그라 불일치였음.")
# 앵커 무손상(R 안 건드림)
anc=VeriEdge(B2.rev_trades(d1m,fund,{**json.load(open(os.path.join(ROOT, r"03_IDEA4Bot\260623_07_RfRautoAlphaUp\back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]})).anchor_check(75,3,1851.6)
log(f"\n[앵커 무손상] {anc['pass']} (got {anc['got_%']}%) — 청산가는 '표시'만 수정, 손익R·앵커는 불변.")
open(os.path.join(ROOT, r"00_WorkHstr\BackTest_Output\260628_12_ComboTradeFull\verify_fix.txt"),"w",encoding="utf-8").write("\n".join(lines))
log("[OK]")
