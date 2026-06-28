# -*- coding: utf-8 -*-
# [bt2pine.py] ★백테 → 곧장 Pine 시스템. config 넣으면 전체거래 백테 + 요약(PF·수익률·MDD·롱숏) + TradingView Pine 즉시 생성.
#   사용:
#     python bt2pine.py                         # best_params_full.json 사용
#     python bt2pine.py cfg.json                # JSON 설정파일
#     python bt2pine.py 240 5 9 0.44 0.56 0.74 2.97 0.057 7.86 10.2   # 직접: sig_tf pivot_tf N f1 f2 f3 atrm er_gate size lev
#   결과: rauto_trades_tv.pine (BINANCE:BTCUSDT.P·UTC·4h에 붙여넣기) + 콘솔 요약.
import os, sys, json
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
sys.path.insert(0, r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork\bots")
import numpy as np, pandas as pd
from fib_replay_1m import load_1m, load_funding
import bt_full as B
import make_pine as MP
import rauto_paper_engine as PE
from rauto_contract import Signal, Action, Side

HERE = os.path.dirname(os.path.abspath(__file__))
KEYS = ["sig_tf", "pivot_tf", "N", "fib1", "fib2", "fib3", "init_atr_mult", "er_gate", "size_pct", "lev"]


def _p(*a): print(*a, flush=True)


def parse_cfg(argv):
    if len(argv) >= 11:                                  # 직접 10인자
        v = argv[1:11]
        return dict(sig_tf=int(v[0]), pivot_tf=int(v[1]), N=int(v[2]), fib1=float(v[3]), fib2=float(v[4]),
                    fib3=float(v[5]), init_atr_mult=float(v[6]), er_gate=float(v[7]), size_pct=float(v[8]), lev=float(v[9]))
    if len(argv) == 2 and argv[1].endswith(".json"):     # JSON 파일
        return json.load(open(argv[1]))
    return json.load(open(os.path.join(HERE, "best_params_full.json")))   # 기본


def summary(T, cfg):
    """PaperAccount(격리마진·강제청산)로 $손익·PF·MDD·롱숏 요약."""
    acct = PE.PaperAccount(10000.0); rows = []
    for r in T.sort_values("et").itertuples():
        b0 = acct.bal
        acct.open(Signal(Action.ENTER, side=Side(int(r.side)), size_pct=cfg["size_pct"], leverage=cfg["lev"]), ts=None, price=100.0)
        acct.resolve_replay(R=float(r.R), mae=float(r.mae), fund=float(r.fund))
        rows.append(dict(side=("롱" if r.side == 1 else "숏"), pnl=acct.bal - b0, R=float(r.R)))
    L = pd.DataFrame(rows); ret, mdd, cal = acct.metrics()

    def pf(s): g = s[s > 0].sum(); b = -s[s < 0].sum(); return g / b if b > 0 else float("inf")
    return acct, L, ret, mdd, cal, pf


def main():
    cfg = parse_cfg(sys.argv)
    _p(f"[config] " + " ".join(f"{k}={cfg[k]}" for k in KEYS))
    d1m = load_1m(); fund = load_funding()
    _p("[백테] 전체 거래 생성 중(현실비용·실펀딩·1m체결·강제청산)…")
    T = B.gen_trades(d1m, fund, cfg["sig_tf"], cfg["pivot_tf"], cfg["N"],
                     (cfg["fib1"], cfg["fib2"], cfg["fib3"]), cfg["init_atr_mult"],
                     er_gate=cfg["er_gate"], capture_fills=True)
    expo = cfg["size_pct"] / 100.0 * cfg["lev"]
    acct, L, ret, mdd, cal, pf = summary(T, cfg)
    # Pine 생성
    nT, nF, mp = MP.build_pine(T, expo)
    _p("\n" + "=" * 60)
    _p(f"[요약] 거래 {len(L)} · 승률 {100*(L.pnl>0).mean():.0f}% · PF {pf(L.pnl):.2f}")
    _p(f"       복리 {ret:+.1f}% (${acct.bal:,.0f}) · MDD {mdd:.1f}% · Calmar {cal:.1f} · 강제청산 {acct.n_liq}회")
    for s, g in L.groupby("side"):
        _p(f"       {s}: {len(g)}건 · 승률 {100*(g.pnl>0).mean():.0f}% · PF {pf(g.pnl):.2f} · 손익 ${g.pnl.sum():+.0f}")
    _p("=" * 60)
    _p(f"[Pine] {MP.OUT}")
    _p(f"       전체 {nT}거래·체결점 {nF} 임베드 · 창위치 0~{mp} 슬라이드(81거래씩)")
    _p("[열기] TradingView → BINANCE:BTCUSDT.P · 시간대 UTC · 4h → Pine편집기 붙여넣기 → 차트추가")
    _p("       ⚙설정의 '창 위치 슬라이드'로 81거래씩 이동.")


if __name__ == "__main__":
    main()
