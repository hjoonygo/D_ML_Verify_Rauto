# -*- coding: utf-8 -*-
# [260625_01_RautoSysReform2_REVoi_ReturnsCost.py] ★REVoi 수익률·비용 리포트 (§19 헤드라인=수익률, 세션 260625_01_RautoSysReform2).
#   헤드라인 = 36개월 수익률(무비용상한/슬립0/현실) → 분기별 수익률+롱/숏 → 비용분해(지정가maker/시장가taker/슬리피지/펀딩).
#   ★RautoCEX(우리 단일 비용엔진)가 항목별 비용을 직접 계산. 롱/숏 분해는 cex 부품으로 동일 루프 복제 후 총합 일치 교차검증.
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
from path_finder import ensure_paths  # noqa: E402
ensure_paths()
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from fib_replay_1m import load_1m, load_funding  # noqa: E402
from REVoi_bot import REVoiBot  # noqa: E402
from rauto_cex import RautoCEX, SlipModel, FeeModel, MK, TK  # noqa: E402

LOG = os.path.join(HERE, "260625_01_RautoSysReform2_REVoi_ReturnsCost_run.log")


def _p(*a):
    print(*a, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(" ".join(str(x) for x in a) + "\n")


def _q(ym):  # '2023-05' → '2023-Q2'
    y, m = ym.split("-")
    return f"{y}-Q{(int(m) - 1) // 3 + 1}"


def replicate_side_quarter(cex, T):
    """cex 부품으로 RautoCEX.run 루프를 복제 → (분기,side)별 $ 기여. 총합이 cex.run과 일치해야 신뢰."""
    R = T["R"].values.astype(float); MAE = T["mae"].values.astype(float)
    FUND = T["fund"].values.astype(float); REASON = T["reason"].values
    SIDE = T["side"].values.astype(int); YM = T["_ym"].values
    bal = 10000.0; by_qs = {}; slip_mkt = cex.slip.market_exit_slip()
    for i in range(len(R)):
        gR = cex._gross_R(R[i], FUND[i])
        ec = cex.fee.entry_cost(cex.leg1_taker); xc = cex.fee.exit_cost(REASON[i])
        is_mkt = REASON[i] != "tp"
        R_net = gR - ec - xc - FUND[i] - (slip_mkt if is_mkt else 0.0)
        bal0 = bal
        p, _ = cex.margin.step(bal, R_net, MAE[i], FUND[i]); bal *= (1.0 + p)
        key = (_q(YM[i]), "롱" if SIDE[i] == 1 else "숏")
        by_qs[key] = by_qs.get(key, 0.0) + (bal - bal0)
    return by_qs, (bal / 10000.0 - 1.0) * 100.0


def main():
    p = json.load(open(os.path.join(ensure_paths(), "03_IDEA4Bot", "260623_07_RfRautoAlphaUp",
                                     "back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()
    bot = REVoiBot(p)
    T = bot.make_trades(d1m, fund).sort_values("et").reset_index(drop=True)
    T["_ym"] = pd.to_datetime(T["et"]).dt.to_period("M").astype(str)
    SIDE = T["side"].values.astype(int)
    nlong = int((SIDE == 1).sum()); nshort = int((SIDE == -1).sum())

    # 세 가지 비용 시나리오
    gross = RautoCEX(75.0, 3.0, fee=FeeModel(mk=0.0, tk=0.0), slip=SlipModel(0, 0)).run(T.copy())   # 무비용 상한
    slip0 = RautoCEX(75.0, 3.0, slip=SlipModel(0.0, 0.0)).run(T.copy())                              # 수수료+펀딩, 슬립0
    cexR = RautoCEX(75.0, 3.0, slip=SlipModel(0.0, 1.0))                                             # 현실(청산 스프1bp)
    real = cexR.run(T.copy())

    _p("=" * 70)
    _p(f"[REVoi 36개월 수익률 — $10k 복리 · 레버3/증거금75% · 거래 {len(T)}(롱{nlong}/숏{nshort})]")
    _p(f"  ① 무비용 상한(손익금, 달성불가)   : {gross['tot']:+,.1f}%   (${gross['final']:,.0f})")
    _p(f"  ② 슬립0(수수료+펀딩만)            : {slip0['tot']:+,.1f}%   (${slip0['final']:,.0f})   ← 낙관(청산슬립0)")
    _p(f"  ★③ 현실(+청산 스프1bp)=순손익금   : {real['tot']:+,.1f}%   (${real['final']:,.0f})   ← 진실(채택)")
    _p(f"     MDD {real['mdd']:.1f}% · 강제청산 {real['nliq']}건")

    # ── 분기별 수익률 + 롱/숏 $ (현실 기준) ──
    by_qs, chk = replicate_side_quarter(cexR, T)
    assert abs(chk - real['tot']) < 1e-6, f"복제 불일치 {chk} vs {real['tot']}"   # 교차검증
    mon = real["monthly"]
    yms = sorted(mon.keys())
    bal = 10000.0; q_start = {}; q_end = {}
    for ym in yms:
        q = _q(ym)
        if q not in q_start:
            q_start[q] = bal
        bal += mon[ym]
        q_end[q] = bal
    _p("")
    _p("[분기별 수익률(현실) + 롱/숏 수익금($)]  (수익률=그 분기 복리, 롱/숏=그 분기 $기여)")
    _p(f"  {'분기':<9}{'분기수익률':>10}{'롱 $':>12}{'숏 $':>12}{'분기말 잔고$':>14}")
    for q in sorted(q_start.keys()):
        qret = (q_end[q] / q_start[q] - 1.0) * 100.0
        lo = by_qs.get((q, "롱"), 0.0); sh = by_qs.get((q, "숏"), 0.0)
        _p(f"  {q:<9}{qret:>+9.1f}%{lo:>12,.0f}{sh:>12,.0f}{q_end[q]:>14,.0f}")

    # ── 비용 분해 (현실 기준, $) ──
    c = real["cost"]
    tot_cost = gross['final'] - real['final']
    _p("")
    _p("[비용 분해 — 현실 기준 ($, 36개월 누적)]")
    _p(f"  지정가 수수료(maker, 진입 되돌림)   : ${c['maker']:>12,.0f}   (요율 {MK*1e4:.0f}bp)")
    _p(f"  시장가 수수료(taker, 청산 fibstop)  : ${c['taker']:>12,.0f}   (요율 {TK*1e4:.0f}bp)")
    _p(f"  슬리피지(청산 시장가, 스프1bp)      : ${c['slip']:>12,.0f}")
    _p(f"  펀딩비(실펀딩 8h)                   : ${c['fund']:>12,.0f}")
    _p(f"  ───────────────────────────────")
    _p(f"  총비용(=무비용상한 − 순손익)        : ${tot_cost:>12,.0f}   (상한 대비 {100*tot_cost/gross['final']:.1f}% 잠식)")
    _p(f"  체결 구조: 진입=지정가(maker, 3분할), 청산=시장가(taker, fibstop {real['nliq']==0 and '강제청산0' or ''})")
    _p("")
    _p("=" * 70)
    _p("[정직] ③현실(+1483%)이 채택수치. 단 청산 시장가 슬립이 1m재현상 0bp 기반(스프1bp만)이라 여전히 낙관 여지 — 틱실측 보정(안전장치7)이 남음.")


if __name__ == "__main__":
    main()
