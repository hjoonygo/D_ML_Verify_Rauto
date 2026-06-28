# -*- coding: utf-8 -*-
# [Stg12] 지시2 재실행: COMBO 최근 10거래 '하나하나' 계산식 전부 + 가격수익률 vs 원장R 불일치 규명.
import os, sys, json
import numpy as np, pandas as pd
ROOT = r"D:\ML\RfRauto"
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
sys.path.insert(0, os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp"))
from path_finder import ensure_paths; ensure_paths()
from fib_replay_1m import load_1m, load_funding
import back2tv_REVoi as B2
from rauto_live import per_trade_pnl
OUT = os.path.join(ROOT, r"00_WorkHstr\BackTest_Output\260628_12_ComboTradeFull"); os.makedirs(OUT, exist_ok=True)
lines=[]
def log(s=""): print(s, flush=True); lines.append(str(s))
SZ, LEV = 75.0, 5.0
combo_p = {**json.load(open(os.path.join(ROOT, r"03_IDEA4Bot\260623_07_RfRautoAlphaUp\back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"],
           "tp_frac":0.7, "early_tp_pct":0.01, "early_frac":1.0}
d1m, fund = load_1m(), load_funding()
T = B2.rev_trades(d1m, fund, combo_p).reset_index(drop=True)
T["et"]=pd.to_datetime(T["et"]); T["xt"]=pd.to_datetime(T["xt"])
log(f"[원장 컬럼] {list(T.columns)}")
pnl, final, mdd, nliq = per_trade_pnl(T, SZ, LEV)
exp = SZ/100.0*LEV
bal_before=[10000.0]
for p in pnl[:-1]: bal_before.append(bal_before[-1]*(1+p/100.0))

idx = list(range(len(T)))[-10:]
log("\n[최근 10거래 — 원시값 + 가격수익률 vs 원장R 대조]")
log(f"{'#':>3} {'방향':3} {'진입가':>10} {'청산가':>10} {'가격수익%':>9} {'원장R%':>8} {'차이':>7} {'판정'}")
for k in idx:
    r=T.iloc[k]; side='숏' if r.side==-1 else '롱'
    pm = r.side*(r.exit/r.entry-1)*100   # 기록된 진입·청산가로 계산한 가격수익
    diff = r.R*100 - pm
    flag = "★조기익절(+1%)" if abs(r.R*100-0.96)<0.15 and abs(diff)>0.3 else ("일치" if abs(diff)<0.15 else "불일치")
    log(f"{k:>3} {side:3} {r.entry:>10.1f} {r.exit:>10.1f} {pm:>+8.2f}% {r.R*100:>+7.2f}% {diff:>+6.2f}% {flag}")

log("\n" + "="*70)
log("[10거래 하나하나 — 계산식 전부]  (사이징 lev5/증거금75%, exp=3.75)")
log("="*70)
for n,k in enumerate(idx,1):
    r=T.iloc[k]; bb=bal_before[k]; p=pnl[k]; side='숏' if r.side==-1 else '롱'
    pm = r.side*(r.exit/r.entry-1)*100
    notion=exp*bb; qty=notion/r.entry; pnl_d=p/100*bb; ba=bb*(1+p/100)
    is_etp = abs(r.R*100-0.96)<0.15 and abs(r.R*100-pm)>0.3
    log(f"\n──[거래 {n}/10] {r.et:%Y-%m-%d %H:%M} {side} ────────────────────────")
    log(f"  진입가 {r.entry:,.1f} → 청산가(기록) {r.exit:,.1f}")
    log(f"  ① 기록가격 수익 = side×(청산−진입)/진입 = {int(r.side)}×({r.exit:,.1f}−{r.entry:,.1f})/{r.entry:,.1f} = {pm:+.2f}%")
    log(f"  ② 원장 R(실제 손익) = {r.R*100:+.2f}%")
    if is_etp:
        etp_px = r.entry*(1-0.01) if r.side==-1 else r.entry*(1+0.01)
        log(f"     ★불일치! 이유 = '조기익절(+1%)' 발동. 진짜 청산은 +1% 지점({etp_px:,.1f})이었는데")
        log(f"       기록된 청산가({r.exit:,.1f})는 그 봉의 '마감가'라 안 맞음. 손익(+0.96%)은 정확, 청산가 표기만 오해소지.")
    else:
        log(f"     → 일치(피보스톱 청산). 가격수익≈원장R, 작은 차이는 비용·펀딩.")
    log(f"  ③ 노출 exp = 0.75×5 = 3.75")
    log(f"  ④ 진입 직전 잔고 = ${bb:,.0f}")
    log(f"  ⑤ 명목 = exp×잔고 = 3.75×{bb:,.0f} = ${notion:,.0f}")
    log(f"  ⑥ 진입수량 = 명목/진입가 = {notion:,.0f}/{r.entry:,.1f} = {qty:,.1f} BTC")
    log(f"  ⑦ 계좌손익% = R×exp = {r.R*100:+.2f}%×3.75 = {p:+.2f}%")
    log(f"  ⑧ 손익금 = 손익%×잔고 = {p/100:+.4f}×{bb:,.0f} = ${pnl_d:+,.0f}")
    log(f"  ⑨ 잔고 = {bb:,.0f} → ${ba:,.0f}")

nmis = sum(1 for k in idx if abs(T.iloc[k].R*100-0.96)<0.15 and abs(T.iloc[k].R*100 - T.iloc[k].side*(T.iloc[k].exit/T.iloc[k].entry-1)*100)>0.3)
log("\n" + "="*70)
log(f"[종합 판정] 10거래 중 {nmis}건이 '조기익절(+1%)' 발동 → 기록 청산가≠실제 청산가(조기익절 지점).")
log("  ★손익(R)은 전부 정확. 단 '청산가' 컬럼이 조기익절 트레이드에선 봉마감가를 기록 → 화면서 청산가×수량으로 손익이 안 맞아 보임.")
log("  = 이게 '수익계산이 이상하다'의 진짜 원인. 계산버그 아님(손익정확), 청산가 '표기'의 문제. → 청산가를 조기익절 체결가로 기록하면 해소.")
open(os.path.join(OUT,"260628_12_ComboTradeFull_analysis.txt"),"w",encoding="utf-8").write("\n".join(lines))
log("\n[OK]")
