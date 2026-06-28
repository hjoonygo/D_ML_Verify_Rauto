# -*- coding: utf-8 -*-
# [Stg11] 지시2: 현 Rauto 챔피언 COMBO(lev5/sz75)의 최근 10거래 진입·청산·진입수량·수익을 계산식까지 검증.
#   검증엔진 per_trade_pnl(rauto_live) 그대로 사용 → 잔고궤적 복원 → 거래별 명목·수량·손익 분해.
import os, sys, json
import numpy as np, pandas as pd
ROOT = r"D:\ML\RfRauto"
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
sys.path.insert(0, os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp"))
from path_finder import ensure_paths; ensure_paths()
from fib_replay_1m import load_1m, load_funding
import back2tv_REVoi as B2
from rauto_live import per_trade_pnl
OUT = os.path.join(ROOT, r"00_WorkHstr\BackTest_Output\260628_11_ComboTradeAudit"); os.makedirs(OUT, exist_ok=True)
lines=[]
def log(s=""): print(s, flush=True); lines.append(str(s))
SZ, LEV = 75.0, 5.0   # ★현 Rauto 챔피언 COMBO 등록값
combo_p = {**json.load(open(os.path.join(ROOT, r"03_IDEA4Bot\260623_07_RfRautoAlphaUp\back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"],
           "tp_frac":0.7, "early_tp_pct":0.01, "early_frac":1.0}
d1m, fund = load_1m(), load_funding()
T = B2.rev_trades(d1m, fund, combo_p).reset_index(drop=True)
T["et"]=pd.to_datetime(T["et"]); T["xt"]=pd.to_datetime(T["xt"])
pnl, final, mdd, nliq = per_trade_pnl(T, SZ, LEV)   # 검증엔진 손익(% per trade)
exp = SZ/100.0*LEV
# 잔고 궤적 복원: bal_after_i = 10000 * prod(1+pnl[:i+1]/100)
bal_before = [10000.0]
for p in pnl[:-1]:
    bal_before.append(bal_before[-1]*(1+p/100.0))
log("="*92)
log(f"COMBO(조기익절1%) 최근 10거래 검증 — 사이징 lev{LEV}/증거금{SZ}% (노출 exp={exp})  · 시작 $10,000 복리")
log("="*92)
log(f"[전체] {len(T)}거래 · 최종잔고 ${final:,.0f} · MDD {mdd:.1f}% · 강제청산 {nliq}회")
log(f"★주의: lev5는 36개월 전체(in-sample) 누적이라 수치가 천문학적 = '천장'(실전아님). 인증값=REVoi@ETF OOS 월복리12.29%.")
log("")
log("계산식: 노출 exp = 증거금%/100 × 레버 = 0.75×5 = 3.75")
log("        명목 = exp × 잔고 ;  진입수량 = 명목 / 진입가 ;  거래손익% p = R_net(비용후) × exp ;  손익$ = p × 잔고")
log("")
idx = list(range(len(T)))[-10:]
hdr = f"{'#':>3} {'진입일시':16} {'롱숏':4} {'진입가':>10} {'청산가':>10} {'R(무사이징)':>11} {'진입잔고$':>14} {'명목$':>16} {'수량BTC':>10} {'손익%':>8} {'손익$':>16} {'청산잔고$':>16}"
log(hdr); log("-"*len(hdr))
for k in idx:
    r=T.iloc[k]; bb=bal_before[k]; p=pnl[k]
    side="롱" if r.side==1 else "숏"
    notion=exp*bb; qty=notion/r.entry if r.entry else 0; pnl_d=p/100.0*bb; ba=bb*(1+p/100.0)
    log(f"{k:>3} {r.et.strftime('%Y-%m-%d %H:%M'):16} {side:4} {r.entry:>10.1f} {r.exit:>10.1f} {r.R*100:>+10.2f}% {bb:>14,.0f} {notion:>16,.0f} {qty:>10.3f} {p:>+7.2f}% {pnl_d:>+16,.0f} {ba:>16,.0f}")
log("-"*len(hdr))
log("\n[한 거래 상세 계산식 예시 — 마지막 거래]")
k=idx[-1]; r=T.iloc[k]; bb=bal_before[k]; p=pnl[k]
log(f"  진입 {r.et:%Y-%m-%d %H:%M} {'롱' if r.side==1 else '숏'} @ {r.entry:,.1f} → 청산 {r.xt:%Y-%m-%d %H:%M} @ {r.exit:,.1f}")
log(f"  ① 무사이징 가격수익 R = side×(청산−진입)/진입 = {int(r.side)}×({r.exit:,.1f}−{r.entry:,.1f})/{r.entry:,.1f} = {r.side*(r.exit/r.entry-1)*100:+.3f}% (원장R={r.R*100:+.3f}%=비용·펀딩 차감후)")
log(f"  ② 노출 exp = 0.75×5 = 3.75")
log(f"  ③ 진입잔고 = ${bb:,.2f}")
log(f"  ④ 명목(포지션크기) = exp×잔고 = 3.75×{bb:,.0f} = ${exp*bb:,.0f}")
log(f"  ⑤ 진입수량 = 명목/진입가 = {exp*bb:,.0f}/{r.entry:,.1f} = {exp*bb/r.entry:.4f} BTC")
log(f"  ⑥ 계좌손익% = R_net×exp = {p:+.3f}%  (검증엔진 비용·격리마진 반영)")
log(f"  ⑦ 손익$ = 손익%×잔고 = {p/100:+.4f}×{bb:,.0f} = ${p/100*bb:+,.0f}")
log(f"  ⑧ 청산잔고 = {bb:,.0f}×(1{p/100:+.4f}) = ${bb*(1+p/100):,.0f}")
open(os.path.join(OUT,"260628_11_ComboTradeAudit_analysis.txt"),"w",encoding="utf-8").write("\n".join(lines))
log("\n[OK]")
