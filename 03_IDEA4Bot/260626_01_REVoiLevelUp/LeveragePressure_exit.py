# -*- coding: utf-8 -*-
# [LeveragePressure_exit.py] 세션 260626_01_REVoiLevelUp · Stg2 (LP → 청산 스텝업 연결)
# 목적: exit_upgrade.build_scale의 '이산 레짐판정'(저변동Q1·극단쏠림)을 'LP 연속 과열압력'으로 교체.
#   불리봉 이진 ON/OFF → LP 과열↑일수록 피보스톱 비례 타이트(빠른 탈출). ★고변동(atr Q80↑)은 불간섭(§20).
#   비교: 기존 이산R vs LP이산R vs LP연속R — full복리·MDD + CPCV 표준6(p25>0·MDD-20위반0).
#   ★검증엔진 무수정(§15.1): exit_upgrade·bt_full을 import 재사용, fib_scale 배열만 LP로 생성. 레버3/75 고정 1차.
import os, sys, json
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
sys.path.insert(0, r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork\bots")
import numpy as np, pandas as pd
from fib_replay_1m import load_1m, load_funding
import bt_full as B
from blend_opt import rev_side
import exit_upgrade as EU   # build_scale·curve·monthly_liq·cpcv_std6 재사용

HERE = os.path.dirname(os.path.abspath(__file__))
REG = EU.REG


def _p(*a): print(*a, flush=True)


def _z(x):
    x = np.asarray(x, float)
    return np.nan_to_num((x - np.nanmean(x)) / (np.nanstd(x) + 1e-9), nan=0.0)


def build_scale_LP(d1m, p, factor, mode="cont", q=0.60):
    """LP 과열압력 기반 fib_scale 배열(sig_tf 봉별). mode='thr'(이산 상위q) / 'cont'(연속 비례).
       ★고변동(atr60 Q80↑)은 scale=1.0 강제(§20 경계). 반환 (scale배열, 타이트봉비중)."""
    Rg = pd.read_parquet(REG); Rg["timestamp"] = pd.to_datetime(Rg["timestamp"], utc=True).dt.tz_localize(None)
    Rg = Rg.set_index("timestamp").sort_index()
    dfx = B.TS.resample_tf(d1m[["open", "high", "low", "close"]], p["rev_tf"]); idx = dfx.index
    pos = np.clip(np.searchsorted(Rg.index.values, idx.values, "right") - 1, 0, len(Rg) - 1)
    atr = Rg["atr60"].values[pos]
    oiz = np.abs(Rg["oiz_s"].values[pos]); fund = np.abs(Rg["fund_s"].values[pos]); ls = np.abs(Rg["ls_s"].values[pos])
    LP = _z(oiz) + _z(fund) + _z(ls) + (-_z(atr))   # 레버리지 과열 + 저변동(휩소 표적). 고변동=LP낮음(보호됨)
    if mode == "thr":
        adv = LP > np.nanquantile(LP, q)
        scale = np.where(adv, factor, 1.0)
    else:  # 연속: 양압력(LP>0)을 0~(factor-1)로 선형 매핑
        lp_pos = np.clip(LP, 0.0, None); mx = np.nanmax(lp_pos) or 1.0
        scale = 1.0 + (factor - 1.0) * (lp_pos / mx)
    hi = atr >= np.nanquantile(atr, 0.8)            # ★고변동 보호(§20)
    scale = np.where(hi, 1.0, scale)
    return scale.astype(float), float(np.mean(scale > 1.0001))


def main():
    EU.T_TF = None
    p = json.load(open(os.path.join(r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    EU.T_TF = p["rev_tf"]
    d1m = load_1m(); fund = load_funding()
    _, side = rev_side(d1m, p["rev_tf"], p["q"], p["qwin"])

    def gen(scale):
        return B.gen_trades(d1m, fund, p["rev_tf"], p["piv"], p["N"], (p["f1"], p["f2"], p["f3"]), p["iam"],
                            er_gate=0.0, ext_side=side, align_pivot=True, use_trend_flip=False,
                            arm_bars=p["arm"], fib_scale=scale)

    _p("=" * 92)
    _p("[LP → 청산 스텝업 연결 — Stg2] 레버3/증거금75 고정 · 이산 레짐 vs LP(이산/연속) · CPCV 표준6 본선")
    # 앵커 무손상
    base = EU.curve(gen(None)); mo, rt = EU.monthly_liq(gen(None)); cpb = EU.cpcv_std6(mo, rt)
    _p(f"[관문0 앵커 OFF] 복리 {base['tot']:+.0f}% · MDD {base['mdd']:.1f}% · 청산 {base['nliq']} (앵커 +1852%/MDD-25)")

    configs = [("기준 OFF", None)]
    for f in [1.4, 2.0]:
        sc_old, fr_old = EU.build_scale(d1m, p, f)
        sc_thr, fr_thr = build_scale_LP(d1m, p, f, mode="thr", q=0.60)
        sc_con, fr_con = build_scale_LP(d1m, p, f, mode="cont")
        configs += [(f"이산R ×{f} (비중{fr_old*100:.0f}%)", sc_old),
                    (f"LP이산 ×{f} (비중{fr_thr*100:.0f}%)", sc_thr),
                    (f"LP연속 ×{f} (비중{fr_con*100:.0f}%)", sc_con)]

    rows = []
    _p(f"\n{'설정':<24}{'full복리%':>10}{'MDD%':>8}{'청산':>5}{'CPCV_p25':>10}{'중앙':>8}{'음수폴드%':>9}{'MDD-20위반%':>11}")
    for nm, sc in configs:
        T = gen(sc); c = EU.curve(T); mo, rt = EU.monthly_liq(T); cp = EU.cpcv_std6(mo, rt)
        rows.append(dict(설정=nm, full복리=round(c["tot"], 0), MDD=round(c["mdd"], 1), 청산=c["nliq"],
                         CPCV_p25=round(cp["p25"], 1), CPCV_중앙=round(cp["median"], 1),
                         음수폴드pct=round(cp["neg"], 0), MDD20위반pct=round(cp["mdd_viol"], 0),
                         폴드MDD최악=round(cp["mdd_worst"], 1)))
        _p(f"{nm:<24}{c['tot']:>10.0f}{c['mdd']:>8.1f}{c['nliq']:>5}{cp['p25']:>10.1f}{cp['median']:>8.1f}{cp['neg']:>9.0f}{cp['mdd_viol']:>11.0f}")

    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "LP_exit_compare_CPCV.csv"), index=False, encoding="utf-8-sig")
    # 본선 통과(p25>0 & MDD-20위반0) 후보
    passed = df[(df.CPCV_p25 > 0) & (df.MDD20위반pct == 0)]
    _p("\n[본선 판정 §5.7] p25>0 AND MDD-20위반0:")
    if len(passed):
        for _, r in passed.sort_values("CPCV_p25", ascending=False).iterrows():
            _p(f"   ✅ {r.설정}: full{r.full복리:+.0f}%·p25{r.CPCV_p25:+.1f}%·위반{r.MDD20위반pct:.0f}%")
    else:
        _p("   ⚠️ 본선 통과 없음(이번 격자).")
    _p("\n[저장] LP_exit_compare_CPCV.csv")
    _p("[정직 注] 레버3/75 고정 1차. 통과 후보는 held-out 재확인 + 4단 MDD 게이트(§26) 확장=Stg3. full표본은 참고(과적합 상한).")


if __name__ == "__main__":
    main()
