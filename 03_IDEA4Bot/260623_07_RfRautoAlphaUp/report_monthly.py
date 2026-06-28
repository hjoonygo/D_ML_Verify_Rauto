# -*- coding: utf-8 -*-
# [report_monthly.py] 백테 결과 월별×롱숏 분해표 — PF·수익금$·거래수·승률·손익비·누적수익금$.
#   모델·조건을 표머리에 명시. PaperAccount(격리마진·강제청산) 순차복리로 거래별 $손익 산출.
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
# ── 강건 config (bt_full opt 강건목적·CPCV p25+0.49, opt_run2) ──
CFG = dict(sig_tf=240, pivot_tf=5, N=9, fib=(0.4363, 0.5576, 0.7447), init_atr_mult=2.969,
           er_gate=0.0567, size_pct=7.864, lev=10.238)
START = 10000.0


def _p(*a): print(*a, flush=True)


def run_ledger(d1m, fund):
    T = B.gen_trades(d1m, fund, CFG["sig_tf"], CFG["pivot_tf"], CFG["N"], CFG["fib"],
                     CFG["init_atr_mult"], er_gate=CFG["er_gate"]).sort_values("et").reset_index(drop=True)
    acct = PE.PaperAccount(START); rows = []
    for _, r in T.iterrows():
        b0 = acct.bal
        acct.open(Signal(Action.ENTER, side=Side(int(r.side)), size_pct=CFG["size_pct"], leverage=CFG["lev"]), ts=None, price=100.0)
        acct.resolve_replay(R=float(r.R), mae=float(r.mae), fund=float(r.fund))
        tr = acct.trades[-1]
        rows.append(dict(month=pd.Timestamp(r.et).strftime("%Y-%m"), side=("롱" if r.side == 1 else "숏"),
                         pnl=acct.bal - b0, liq=tr["liq"]))
    return pd.DataFrame(rows), acct


def block(df, title):
    _p(f"\n{'='*86}\n{title}\n{'='*86}")
    _p(f"{'월':<9}{'거래':>5}{'승률%':>7}{'PF':>7}{'손익비':>7}{'수익금$':>12}{'누적$':>13}")
    _p("-" * 86)
    cum = 0.0
    for m, g in df.groupby("month"):
        n = len(g); wins = g[g.pnl > 0].pnl; loss = g[g.pnl < 0].pnl
        wr = 100 * (len(wins) / n) if n else 0
        pf = wins.sum() / abs(loss.sum()) if loss.sum() != 0 else float("inf")
        pr = (wins.mean() / abs(loss.mean())) if (len(wins) and len(loss)) else float("nan")
        s = g.pnl.sum(); cum += s
        pfs = f"{pf:>7.2f}" if np.isfinite(pf) else f"{'∞':>7}"
        prs = f"{pr:>7.2f}" if np.isfinite(pr) else f"{'-':>7}"
        _p(f"{m:<9}{n:>5}{wr:>7.0f}{pfs}{prs}{s:>+12.0f}{cum:>+13.0f}")
    # 합계행
    n = len(df); wins = df[df.pnl > 0].pnl; loss = df[df.pnl < 0].pnl
    wr = 100 * (len(wins) / n) if n else 0
    pf = wins.sum() / abs(loss.sum()) if loss.sum() != 0 else float("inf")
    pr = (wins.mean() / abs(loss.mean())) if (len(wins) and len(loss)) else float("nan")
    _p("-" * 86)
    _p(f"{'합계':<9}{n:>5}{wr:>7.0f}{pf:>7.2f}{pr:>7.2f}{df.pnl.sum():>+12.0f}{'':>13}")


def main():
    d1m = load_1m(); fund = load_funding()
    led, acct = run_ledger(d1m, fund)
    ret, mdd, cal = acct.metrics()
    _p("█" * 86)
    _p("백테 결과 — 월별 × 롱/숏 분해표")
    _p("█" * 86)
    _p("[모델] 진입신호 = TrendStack 챔피언 엔진(pivot-supertrend Trend+피봇, §8 해시락) on 4h(sig_tf=240)")
    _p("       청산 = 피보나치 스텝업(눌림목 5m·N9봉, 비율 0.44/0.56/0.74) + 추세전환, 초기손절 ATR×2.97")
    _p("[조건] · 실거래비용: 진입 지정가 maker 2bp → 청산 시장가 taker 4bp + 스프레드 1bp")
    _p("       · 슬리피지: 청산 1분봉 실체결(갭=불리쪽 open), 환각방지")
    _p(f"       · 실펀딩: BTCUSDT_funding_history_8h {len(fund[0])}건 구간합 차감(추정0.0001 아님)")
    _p("       · 강제청산: 격리마진(isolated) PaperAccount — MMR티어(T1 0.4%/T2 0.5%·경계$50k),")
    _p(f"         하드스탑 hsd=1/lev−mmr−slip, 포지션 MAE≤−hsd면 청산. 강제청산 {acct.n_liq}회")
    _p(f"       · 레버리지 {CFG['lev']:.1f}x · 진입수량(증거금) {CFG['size_pct']:.2f}% · 시작자본 ${START:,.0f} 복리")
    _p(f"[전체] 복리 {ret:+.1f}% (${acct.bal:,.0f}) · MDD {mdd:.1f}% · Calmar {cal:.1f} · 거래 {len(led)} · 승률 {100*(led.pnl>0).mean():.0f}%")
    _p("[정직] 이 config는 강건목적(전구간 CPCV p25+0.49) 최적화본. ★깨끗한 held-out(학습23-24만→25-26 미사용)에선 OOS −2%·2025 −12% = 단독 강건 OOS엣지 미확정. 아래 표는 그 전제하에 '구조 진단용'.")
    block(led[led.side == "롱"], "① 롱 (LONG) 월별")
    block(led[led.side == "숏"], "② 숏 (SHORT) 월별")
    block(led, "③ 전체(롱+숏) 월별")
    led.to_csv(os.path.join(HERE, "monthly_report_ledger.csv"), index=False, encoding="utf-8-sig")
    _p(f"\n[저장] monthly_report_ledger.csv (거래별 월·롱숏·손익$)")


if __name__ == "__main__":
    main()
