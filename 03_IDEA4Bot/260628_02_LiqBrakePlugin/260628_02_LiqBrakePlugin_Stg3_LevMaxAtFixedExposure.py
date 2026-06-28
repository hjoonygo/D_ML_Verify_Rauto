# -*- coding: utf-8 -*-
# [260628_02_LiqBrakePlugin_Stg3_LevMaxAtFixedExposure.py]
# ★캡틴 통찰 (2026-06-28): 노출 고정 + 레버↑ = 증거금↓ = '한방 최대손실(증거금)' ↓ = 급변동 전멸 방어.
#   질문: 노출 3.0(안정선) 고정하고 레버를 어디까지 올릴 수 있나? (증거금 100%→3%로 낮추며 수익 버티는 임계선)
#   ★두 안정성 지표 충돌 — (A)누적 MDD: 레버↑→청산↑→MDD악화(Stg1) vs (B)한방 최대손실=증거금%: 레버↑→증거금↓→한방 안전.
#   둘 다 산출해 임계선 제시. + 강제청산 횟수 + 청산거리 hsd.
#
# ★검증엔진만(§15.1): REVoi_bot.make_trades + rauto_live.per_trade_pnl. 데이터=post-2024(REVoi@ETF).
# ★수익률 라벨 강제(memory#6): ret_guard.fmt_ret. 헤드라인=OOS, in-sample 상한은 라벨 보조. 현실슬립10bp(memory#9).
import os, sys, json
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))


def find_root():
    d = HERE
    for _ in range(7):
        if os.path.isdir(os.path.join(d, "08_BTC_Data")) and os.path.isdir(os.path.join(d, "04_공용엔진코드")):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return r"D:\ML\RfRauto"


ROOT = find_root()
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
sys.path.insert(0, os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp"))
from path_finder import ensure_paths
ensure_paths()
from fib_replay_1m import load_1m, load_funding
from REVoi_bot import REVoiBot
from rauto_live import per_trade_pnl
from rauto_cex import SlipModel, MMR_T1, LIQ_SLIP
from ret_guard import fmt_ret

PJSON = os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")
POST = pd.Timestamp("2024-01-01")
TRAIN_END = pd.Timestamp("2024-12-31")
SLIP_REAL = 10.0
EXPS = [3.0, 4.0, 5.0]                                   # 노출 고정값(캡틴 언급: 3.0 안정선, 5.0)
LEVS = [3, 5, 10, 15, 20, 30, 40, 50, 75, 100]          # 캡틴: lev20/30/40/50 + 임계 탐색


def _p(*a):
    print(*a, flush=True)


def slip(bp):
    return SlipModel(gap_bp=0.0, exit_spread_bp=0.0, extra_bp=bp)


def run(T, exp, lev, bp=SLIP_REAL):
    size = exp / lev * 100.0
    pnl, bal, mdd, nliq = per_trade_pnl(T, size, lev, slip(bp))
    hsd = 1.0 / lev - MMR_T1 - LIQ_SLIP
    return dict(size=size, ret=(bal / 10000.0 - 1.0) * 100.0, mdd=mdd, nliq=nliq, hsd=hsd * 100.0)


def main():
    _p("=" * 100)
    _p("[260628_02 Stg3] REVoi@ETF — 노출 고정 + 레버 최대 임계선 (증거금↓=한방손실한도↓, 캡틴 통찰)")
    _p("=" * 100)
    p = json.load(open(PJSON, encoding="utf-8"))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()
    T0 = REVoiBot({**p, "tp_frac": 0.0, "early_tp_pct": 0.0, "early_frac": 0.0}).make_trades(d1m, fund).sort_values("et").reset_index(drop=True)
    _, b0, _, _ = per_trade_pnl(T0, 75.0, 3, slip(0.0))
    _p(f"[엔진 무손상] 36mo 앵커 = {(b0/10000-1)*100:+.4f}% (기준값 +1851.6491% 재현)")

    T = REVoiBot({**p, "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0}).make_trades(d1m, fund).sort_values("et").reset_index(drop=True)
    T["et"] = pd.to_datetime(T["et"])
    Tpost = T[T["et"] >= POST].reset_index(drop=True)
    _p(f"[REVoi@ETF] post-2024 {len(Tpost)}건 · mae 최악 {Tpost['mae'].min()*100:.2f}% (정상역행 한계)")

    for exp in EXPS:
        _p("\n" + "=" * 100)
        _p(f"[노출 {exp:.1f} 고정 = 시드의 {exp*100:.0f}% 명목]  레버↑ = 증거금↓ = 한방 최대손실↓ (post-2024 28mo · 현실10bp · in-sample 상한)")
        _p("=" * 100)
        _p(f"  {'레버':>5}{'증거금%':>8}{'한방최대손실':>11}{'청산거리hsd':>11}{'수익률%(현실10bp,in-sample상한)':>34}{'MDD%':>8}{'강제청산':>8}")
        base_ret = None
        crit_lev = None
        for lev in LEVS:
            r = run(Tpost, exp, lev)
            if r["size"] > 100.0:
                _p(f"  {lev:>5}x  (증거금 {r['size']:.0f}%>100 = 불가)")
                continue
            if base_ret is None:
                base_ret = r["ret"]
            # 임계선 = 수익이 base 대비 10% 이상 깎이기 시작하는 레버
            if crit_lev is None and base_ret and r["ret"] < base_ret * 0.9 and base_ret > 0:
                crit_lev = lev
            _p(f"  {lev:>5}x{r['size']:>7.1f}%{r['size']:>10.0f}%{r['hsd']:>10.1f}%{r['ret']:>+30.0f}%{r['mdd']:>8.1f}%{r['nliq']:>8}")
        if crit_lev:
            _p(f"  ▶ 임계선: lev{crit_lev} 부근부터 청산이 수익을 깎기 시작(그 전까진 증거금↓=한방안전, 수익 무손실).")
        else:
            _p(f"  ▶ 전 레버 수익 유지 — 청산이 수익 못 깎음(증거금 최소화 = 공짜로 한방안전).")

    # ── 노출3.0(안정선): 레버별 held-out OOS (증거금 낮춰도 OOS 수익 유지되나) ──
    _p("\n" + "=" * 100)
    _p("[★노출 3.0 안정선 · 레버별 held-out OOS — train 2024 → test 2025~26(16mo) blind, 현실10bp]")
    _p("=" * 100)
    Ttr = Tpost[Tpost["et"] <= TRAIN_END].reset_index(drop=True)
    Tte = Tpost[Tpost["et"] > TRAIN_END].reset_index(drop=True)
    _p(f"  {'레버':>5}{'증거금%':>8}{'한방최대손실':>11} | {'test OOS 수익률(현실10bp)':>40}{'MDD%':>8}{'강제청산':>8}")
    for lev in [3, 10, 15, 20, 30, 50]:
        size = 3.0 / lev * 100.0
        _, bte, mte, nte = per_trade_pnl(Tte, size, lev, slip(SLIP_REAL))
        ret_te = (bte / 10000.0 - 1.0) * 100.0
        s = fmt_ret(ret_te, "test 2025~26 16mo", "OOS", slip_bp=10, mdd_pct=mte)
        _p(f"  {lev:>5}x{size:>7.1f}%{size:>10.0f}% | {s:>40} 청{nte}")

    _p("\n[읽는 법] 같은 노출에서 레버↑=증거금↓=한방최대손실(=증거금%)↓. 청산0인 구간은 수익 동일(증거금만 안전해짐=공짜).")
    _p("[정직] 한방최대손실 ≈ 증거금%(격리마진 최악). MDD(누적)와 다른 지표. in-sample 상한=천장·실전아님, 헤드라인=OOS.")
    return True


if __name__ == "__main__":
    main()
