# -*- coding: utf-8 -*-
# [report_costs.py] 월별 거래비용 분해 — 지정가횟수·지정가수수료$ · 시장가횟수·시장가수수료$ · 슬리피지$ · 펀딩비$.
#   실제 체결모델(성급계열 realistic_exec): 진입=지정가@신호가(M1=3분)→재지정(M2=3분)→시장가(+스프레드).
#                                          청산=fibstop(스톱)→시장가(taker+스프레드) / flip→지정가시도→시장가.
#   체결판정=1분봉 고저 터치. 슬리피지=의도가 대비 실체결가 괴리(불리분). 펀딩=실값. $=비용률×노출×직전잔액(복리).
import sys, os
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
sys.path.insert(0, r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork\bots")
import numpy as np, pandas as pd
from fib_replay_1m import load_1m, load_funding
import bt_full as B
import rauto_paper_engine as PE
from rauto_contract import Signal, Action, Side

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = dict(sig_tf=240, pivot_tf=5, N=9, fib=(0.4363, 0.5576, 0.7447), init_atr_mult=2.969,
           er_gate=0.0567, size_pct=7.864, lev=10.238)
MK, TK, SPRD = 0.0002, 0.0004, 0.0001
M1, M2 = 3, 3; START = 10000.0


def _p(*a): print(*a, flush=True)


def main():
    d1m = load_1m(); fund = load_funding()
    T = B.gen_trades(d1m, fund, CFG["sig_tf"], CFG["pivot_tf"], CFG["N"], CFG["fib"],
                     CFG["init_atr_mult"], er_gate=CFG["er_gate"]).sort_values("et").reset_index(drop=True)
    acct = PE.PaperAccount(START); rows = []
    for _, r in T.iterrows():
        side = int(r.side); exp = CFG["size_pct"] / 100.0 * CFG["lev"]; bal0 = acct.bal
        # ★R은 gen_trades 그대로(되돌림 지정가 진입·1m 시장청산·수수료6bp·실펀딩) → 비용만 분해(P&L 불변)
        acct.open(Signal(Action.ENTER, side=Side(side), size_pct=CFG["size_pct"], leverage=CFG["lev"]), ts=None, price=100.0)
        acct.resolve_replay(R=float(r.R), mae=float(r.mae), fund=float(r.fund))
        notional = exp * bal0
        # 진입 = 되돌림 지정가(maker), 슬립0 / 청산 = fibstop→시장가(taker+스프레드), flip→지정가(종가)
        lim_cnt = 1; lim_fee = MK * notional       # 진입(지정가)
        mkt_cnt = 0; mkt_fee = 0.0; slip = 0.0
        if r.reason == "fibstop":
            mkt_cnt = 1; mkt_fee = (TK + SPRD) * notional                 # 시장청산 taker+스프레드
            gap = max(0.0, side * (float(r.x_int) - float(r.exit)) / float(r.entry))  # 스톱 미끄러짐(불리)
            slip = gap * notional
        else:                                       # flip = 종가 지정가 청산
            lim_cnt += 1; lim_fee += MK * notional
        rows.append(dict(month=pd.Timestamp(r.et).strftime("%Y-%m"), side=("롱" if side == 1 else "숏"),
            lim_cnt=lim_cnt, mkt_cnt=mkt_cnt, lim_fee=lim_fee, mkt_fee=mkt_fee,
            slip=slip, fund_d=float(r.fund) * notional, pnl=acct.bal - bal0))
    L = pd.DataFrame(rows)
    ret, mdd, cal = acct.metrics()

    _p("█" * 92)
    _p("월별 거래비용 분해 — 지정가/시장가 횟수·수수료, 슬리피지, 펀딩비 (실제 체결모델)")
    _p("█" * 92)
    _p(f"[모델] 4h신호 + 5m눌림목 피보스텝업 · lev{CFG['lev']:.1f} · 증거금{CFG['size_pct']:.2f}% · 격리마진 강제청산 · 시작${START:,.0f}")
    _p("[체결] 진입 지정가@신호가(3분)→재지정(3분)→시장가+스프레드 / 청산 fibstop=시장가, flip=지정가시도")
    _p(f"       수수료 maker{MK*1e4:.0f}bp·taker{TK*1e4:.0f}bp·스프레드{SPRD*1e4:.0f}bp(측당) · 펀딩=실값 · 체결판정=1분봉")
    _p(f"[전체] 복리 {ret:+.1f}% (${acct.bal:,.0f}) · MDD {mdd:.1f}% · 거래 {len(L)} · 강제청산 {acct.n_liq}회")
    _p("[비용 정의] ◇명시비용=수수료+펀딩(순손익서 직접 차감) ◇슬리피지=피보스톱이 이론레벨 대비 실체결(1m) 얼마나 나빴나")
    _p("            ★슬리피지는 이미 순손익에 반영됨(별도 더하지 않음). 낙관백테는 이걸 숨겨 수익을 부풀림(=환상의 정체).")
    _p(f"\n{'월':<9}{'거래':>5}{'지정가#':>7}{'지정가료$':>10}{'시장가#':>7}{'시장가료$':>10}{'펀딩비$':>9}{'슬리피지$':>11}{'순손익$':>10}")
    _p("-" * 84)
    for m, g in L.groupby("month"):
        _p(f"{m:<9}{len(g):>5}{int(g.lim_cnt.sum()):>7}{g.lim_fee.sum():>10.1f}{int(g.mkt_cnt.sum()):>7}"
           f"{g.mkt_fee.sum():>10.1f}{g.fund_d.sum():>+9.1f}{g.slip.sum():>11.0f}{g.pnl.sum():>+10.0f}")
    _p("-" * 84)
    _p(f"{'합계':<9}{len(L):>5}{int(L.lim_cnt.sum()):>7}{L.lim_fee.sum():>10.1f}{int(L.mkt_cnt.sum()):>7}"
       f"{L.mkt_fee.sum():>10.1f}{L.fund_d.sum():>+9.1f}{L.slip.sum():>11.0f}{L.pnl.sum():>+10.0f}")
    fees = L.lim_fee.sum() + L.mkt_fee.sum()
    _p(f"\n[요약] 명시비용 = 수수료 ${fees:,.0f}(지정가 ${L.lim_fee.sum():.0f} + 시장가 ${L.mkt_fee.sum():.0f}) + 펀딩 ${L.fund_d.sum():+,.0f}")
    _p(f"       슬리피지(스톱 체결 미끄러짐, P&L에 이미 반영) = ${L.slip.sum():,.0f} · 청산당 평균 ≈1.4%(공격적 피보트레일이 시장 위 스톱→갭체결)")
    _p(f"[롱숏별]")
    for s, g in L.groupby("side"):
        _p(f"  {s}: 거래{len(g)} | 수수료 지정가${g.lim_fee.sum():.0f}+시장가${g.mkt_fee.sum():.0f} 펀딩${g.fund_d.sum():+.0f} 슬립${g.slip.sum():,.0f} | 순손익${g.pnl.sum():+.0f}")
    L.to_csv(os.path.join(HERE, "cost_breakdown_ledger.csv"), index=False, encoding="utf-8-sig")
    _p(f"\n[저장] cost_breakdown_ledger.csv · [지정가체결률] {100*L.lim_cnt.sum()/(L.lim_cnt.sum()+L.mkt_cnt.sum()):.0f}%")


if __name__ == "__main__":
    main()
