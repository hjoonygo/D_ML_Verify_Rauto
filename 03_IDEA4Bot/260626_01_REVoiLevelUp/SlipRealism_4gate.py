# -*- coding: utf-8 -*-
# [SlipRealism_4gate.py] 세션 260626_01_REVoiLevelUp · Stg4 (체결현실성 슬립 재백테 + 4단 MDD 게이트)
# 목적: 청산세팅 확정 후보(이산R×2.0 / R+P(70%))에 현실 체결비용을 적용해 재백테.
#   ★슬립모델(§24 확정): 측정 청산갭슬립(스톱레벨 대비 1m갭=이미 R에 반영) + 스프레드 1bp 추가차감. (AI 과대모델 4.7bp 폐기.)
#   ★강제청산 = 캡틴 정의(2026-06-26): 손실=유지증거금(size%/100)만(수수료·슬립·펀딩 0).
#   ★MDD 4단 게이트(§26): M0 무제한 / M30 / M25 / M20 각 최고복리 + 강제청산 횟수.
#   ★검증엔진 무수정(§15.1): exit_upgrade·bt_full import 재사용. 레버·증거금 격자 스윕.
import os, sys, json
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
sys.path.insert(0, r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork\bots")
import numpy as np, pandas as pd
from fib_replay_1m import load_1m, load_funding
import bt_full as B
from blend_opt import rev_side
import exit_upgrade as EU

HERE = os.path.dirname(os.path.abspath(__file__))
REG = EU.REG
MMR_T1, MMR_T2, TIER, COST, SLIP = 0.004, 0.005, 50000.0, 0.0014, 0.0005
SPRD = 0.0001   # ★스프레드 1bp (§24 확정 현실비용)
LEVG = [2, 3, 4, 5, 6, 8, 10, 12, 15]
SZG = [50, 60, 70, 75, 80, 90, 100]
GATES = [("M0_무제한", None), ("M30", -30.0), ("M25", -25.0), ("M20", -20.0)]


def _p(*a): print(*a, flush=True)


def curve_real(R, MAE, FUND, MK, size, lev, sprd):
    """현실 체결복리: 정상청산 p=(R-sprd)*exp · 강제청산 캡틴캡(증거금만). 반환 (복리%,MDD%,단일최고월%,청산횟수)."""
    exp = size / 100.0 * lev; bal = 10000.0; peak = 10000.0; mdd = 0.0; nliq = 0; mfac = {}
    for i in range(len(R)):
        mmr = MMR_T2 if exp * bal > TIER else MMR_T1
        trig = 1.0 / lev - mmr
        if MAE[i] <= -trig:
            p = -exp * (1.0 / lev); nliq += 1                  # 강제청산 = 증거금만(캡틴)
        else:
            p = (R[i] - sprd) * exp                            # ★스프1bp 추가차감(현실)
        bal *= (1.0 + p)
        if bal > peak: peak = bal
        dd = bal / peak - 1.0
        if dd < mdd: mdd = dd
        mfac[MK[i]] = mfac.get(MK[i], 1.0) * (1.0 + p)
        if bal <= 0: return -100.0, -100.0, -100.0, nliq
    return (bal / 1e4 - 1) * 100.0, mdd * 100.0, (max(mfac.values()) - 1) * 100.0 if mfac else 0.0, nliq


def sweep4(R, MAE, FUND, MK, sprd):
    rows = [(lev, sz) + curve_real(R, MAE, FUND, MK, sz, lev, sprd) for lev in LEVG for sz in SZG]
    best = {}
    for gn, gm in GATES:
        cand = [r for r in rows if (gm is None or r[3] >= gm)]
        best[gn] = max(cand, key=lambda r: r[2]) if cand else None
    return best


def measure_slip(T):
    """청산 fibstop 슬리피지(스톱레벨 x_int 대비 1m체결 exit 갭, bp). 변동성별."""
    R = pd.read_parquet(REG); R["timestamp"] = pd.to_datetime(R["timestamp"], utc=True).dt.tz_localize(None)
    R = R.set_index("timestamp").sort_index()
    T = T.copy(); T["et"] = pd.to_datetime(T.et)
    pos = np.clip(np.searchsorted(R.index.values, T.et.values, "right") - 1, 0, len(R) - 1)
    T["atr60"] = R["atr60"].values[pos]
    T["slip_bp"] = np.where(T.side == 1, (T.x_int - T.exit) / T.entry, (T.exit - T.x_int) / T.entry) * 1e4
    return T


def report(nm, T):
    T = T.sort_values("et").reset_index(drop=True)
    R = T.R.values.astype(float); MAE = T.mae.values.astype(float); FUND = T.fund.values.astype(float)
    MK = pd.to_datetime(T.et).dt.to_period("M").astype(str).values
    Tm = measure_slip(T)
    _p("\n" + "=" * 92); _p(f"[{nm}] 거래 {len(T)}")
    _p(f"  측정 청산슬립(이미 R반영): 중앙 {Tm.slip_bp.median():.1f}bp·평균 {Tm.slip_bp.mean():.1f}bp·90%분위 {Tm.slip_bp.quantile(.9):.1f}bp·갭>1bp {100*(Tm.slip_bp>1).mean():.0f}%")
    for sprd, tag in [(0.0, "슬립0(상한)"), (SPRD, "현실(스프1bp)")]:
        best = sweep4(R, MAE, FUND, MK, sprd)
        _p(f"  [{tag}] 4단 MDD 게이트 (레버/증거금→복리%/MDD%/강제청산):")
        for gn, _g in GATES:
            b = best[gn]
            if b: _p(f"     {gn:<10} L{b[0]}/{b[1]}% → {b[2]:+.0f}% / MDD{b[3]:.0f}% / 청산{b[5]}")
    # 앵커 세팅(레버3/75) 슬립0 vs 현실
    a0 = curve_real(R, MAE, FUND, MK, 75, 3, 0.0); ar = curve_real(R, MAE, FUND, MK, 75, 3, SPRD)
    _p(f"  [레버3/75 고정] 슬립0 {a0[0]:+.0f}% → 현실(스프1bp) {ar[0]:+.0f}%  (MDD {ar[1]:.0f}%·청산{ar[3]})")
    return Tm


def main():
    p = json.load(open(os.path.join(r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    EU.T_TF = p["rev_tf"]
    d1m = load_1m(); fund = load_funding()
    _, side = rev_side(d1m, p["rev_tf"], p["q"], p["qwin"])

    def gen(scale, frac=0.0):
        return B.gen_trades(d1m, fund, p["rev_tf"], p["piv"], p["N"], (p["f1"], p["f2"], p["f3"]), p["iam"],
                            er_gate=0.0, ext_side=side, align_pivot=True, use_trend_flip=False,
                            arm_bars=p["arm"], fib_scale=scale, tp_frac=frac)

    _p("=" * 92)
    _p("[체결현실성 슬립 재백테 + 4단 MDD 게이트 — Stg4] 청산세팅 확정후보 (슬립0 vs 현실 스프1bp)")
    sc20, _ = EU.build_scale(d1m, p, 2.0)
    sc14, _ = EU.build_scale(d1m, p, 1.4)
    Tm1 = report("이산R ×2.0 (full본선)", gen(sc20, 0.0))
    Tm2 = report("R+P(70%) (held-out §9후보)", gen(sc14, 0.7))
    Tm1.to_csv(os.path.join(HERE, "SlipRealism_R20_slip.csv"), index=False, encoding="utf-8-sig")
    Tm2.to_csv(os.path.join(HERE, "SlipRealism_RP70_slip.csv"), index=False, encoding="utf-8-sig")
    _p("\n[저장] SlipRealism_R20_slip.csv · SlipRealism_RP70_slip.csv")
    _p("[정직 注] 슬립0=상한(이론) / 현실=측정청산갭(R반영)+스프1bp(§24). 다음=확정본 Back2TV(Pine·사례6선). 채택=held-out 별도(§5.7).")


if __name__ == "__main__":
    main()
