# -*- coding: utf-8 -*-
# [260628_02_LiqBrakePlugin_Stg4_LiqZeroMaxLev.py]
# ★캡틴 지시 (2026-06-28): 전체 데이터 돌려 '강제청산 0인 레버리지 최대값'을 뽑아라.
#   ★데이터 한계(정직): 검증본 Merged_Data.csv = 36개월(2023-05~2026-04). 38개월(2026-05~06)은
#     12일갭 + oi_zscore 재구축 미완(오염위험)이라 REVoi 신호 생성 불가 → 36개월(2023 고변동 포함=보수)로 산출.
#
# ★강제청산0 최대레버 원리: 청산조건 mae<=-hsd, hsd=1/lev-mmr-slip. 모든 거래 청산0 = hsd>|worst mae|.
#   → 최대레버 = 1/(|worst mae| + mmr + slip) 미만 최대 정수. mmr=T1(0.004,저잔고)/T2(0.005,고잔고>$50k노출).
#   보수답 = MMR_T2(0.005) 기준(잔고 커지면 T2). 엔진 per_trade_pnl로 실제 nliq도 교차검증.
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
from rauto_cex import SlipModel, MMR_T1, MMR_T2, LIQ_SLIP
from ret_guard import fmt_ret

PJSON = os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")
POST = pd.Timestamp("2024-01-01")
TRAIN_END = pd.Timestamp("2024-12-31")
SLIP_REAL = 10.0


def _p(*a):
    print(*a, flush=True)


def max_lev_liqzero(mae_min, mmr):
    """worst mae(음수 분율)에서 청산0 최대 정수레버 (hsd=1/lev-mmr-LIQ_SLIP > |mae_min|)."""
    thr = abs(mae_min) + mmr + LIQ_SLIP
    lev = int(np.floor(1.0 / thr - 1e-9))
    # 검산: 그 lev에서 hsd>|mae_min| 보장되게 한 칸 내림 안전
    while (1.0 / lev - mmr - LIQ_SLIP) <= abs(mae_min):
        lev -= 1
    return lev


def main():
    _p("=" * 96)
    _p("[260628_02 Stg4] REVoi@ETF — 강제청산 0 최대 레버리지 (검증 36개월 전체)")
    _p("=" * 96)
    _p("★데이터: Merged_Data.csv 36개월(2023-05~2026-04). 38개월은 갭+oi_zscore 미완으로 불가(정직).")
    p = json.load(open(PJSON, encoding="utf-8"))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()
    T0 = REVoiBot({**p, "tp_frac": 0.0, "early_tp_pct": 0.0, "early_frac": 0.0}).make_trades(d1m, fund).sort_values("et").reset_index(drop=True)
    _, b0, _, _ = per_trade_pnl(T0, 75.0, 3, SlipModel(0, 0))
    _p(f"[엔진 무손상] 36mo 앵커 = {(b0/10000-1)*100:+.4f}% (기준값 +1851.6491% 재현)")

    T = REVoiBot({**p, "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0}).make_trades(d1m, fund).sort_values("et").reset_index(drop=True)
    T["et"] = pd.to_datetime(T["et"])
    mae = T["mae"].values.astype(float)
    worst = mae.min()
    wi = int(np.argmin(mae))
    _p(f"\n[COMBO 36개월 거래원장] {len(T)}건")
    _p(f"  ★최악 역행(worst mae) = {worst*100:.4f}%  (발생 {pd.Timestamp(T['et'].iloc[wi]).date()}, side={int(T['side'].iloc[wi])})")
    _p(f"  mae 분위: 0.5%={np.percentile(mae,0.5)*100:.2f}% · 1%={np.percentile(mae,1)*100:.2f}% · 5%={np.percentile(mae,5)*100:.2f}%")

    _p("\n[강제청산 0 최대 레버리지 (청산문턱 hsd=1/lev-mmr-slip > |worst mae|)]")
    ml_t1 = max_lev_liqzero(worst, MMR_T1)
    ml_t2 = max_lev_liqzero(worst, MMR_T2)
    _p(f"  · MMR_T1(0.004, 저잔고<$50k노출) 기준 → 최대 레버 = {ml_t1}배 (hsd {(1/ml_t1-MMR_T1-LIQ_SLIP)*100:.2f}% > {abs(worst)*100:.2f}%)")
    _p(f"  · MMR_T2(0.005, 고잔고>$50k노출) 기준 → 최대 레버 = {ml_t2}배 (hsd {(1/ml_t2-MMR_T2-LIQ_SLIP)*100:.2f}% > {abs(worst)*100:.2f}%)")
    _p(f"  ★보수 답(잔고 커지면 T2 적용) = 레버 {ml_t2}배 까지 강제청산 0 보장.")

    _p("\n[엔진 per_trade_pnl 교차검증 — 레버별 실제 강제청산 횟수 (노출3.0 사이징)]")
    _p(f"  {'레버':>5}{'hsd%':>8}{'강제청산':>10}")
    first_liq = None
    for lev in range(10, 25):
        size = 3.0 / lev * 100.0
        if size > 100:
            size = 100.0
        _, _, _, nliq = per_trade_pnl(T, size, lev, SlipModel(0, 0, SLIP_REAL))
        hsd = 1.0 / lev - (MMR_T2 if (size/100*lev) > 0 else MMR_T1) - LIQ_SLIP
        mark = ""
        if nliq > 0 and first_liq is None:
            first_liq = lev; mark = " ← 첫 강제청산 발생"
        _p(f"  {lev:>5}x{hsd*100:>7.2f}%{nliq:>9}{mark}")
    if first_liq:
        _p(f"  ▶ 엔진 실측: 레버 {first_liq-1}배까지 강제청산 0, {first_liq}배부터 청산 발생.")

    # 채택 레버(보수 청산0)의 수익률 — post-2024 in-sample 상한 + held-out OOS
    L = ml_t2
    T["et"] = pd.to_datetime(T["et"])
    Tpost = T[T["et"] >= POST].reset_index(drop=True)
    Tte = Tpost[Tpost["et"] > TRAIN_END].reset_index(drop=True)
    _p(f"\n[강제청산0 최대레버 {L}배의 수익률] 노출3.0 → 증거금 {3.0/L*100:.1f}% · 한방최대손실 {3.0/L*100:.0f}%")
    size = 3.0 / L * 100.0
    _, balp, mddp, nlp = per_trade_pnl(Tpost, size, L, SlipModel(0, 0, SLIP_REAL))
    _, balt, mddt, nlt = per_trade_pnl(Tte, size, L, SlipModel(0, 0, SLIP_REAL))
    _p("  post-2024 28mo: " + fmt_ret((balp/10000-1)*100, "post-2024 28mo", "in-sample 상한", slip_bp=10, mdd_pct=mddp) + f" · 강제청산 {nlp}")
    _p("  ★헤드라인 OOS : " + fmt_ret((balt/10000-1)*100, "test 2025~26 16mo", "OOS", slip_bp=10, mdd_pct=mddt) + f" · 강제청산 {nlt}")

    _p("\n[정직] 36개월(2023 고변동 포함) 기준 = 보수적. 38개월(2026-05~06 불리장세)은 더 깊은 역행 가능 → 청산0 레버가")
    _p("       더 낮아질 수 있음. 38개월 산출엔 데이터 갭메움+oi_zscore 재구축+무손상 검증 선행 필요(별도 Stg·승인).")
    return True


if __name__ == "__main__":
    main()
