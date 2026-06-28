# -*- coding: utf-8 -*-
# [PressureAxes_exit.py] 세션 260626_01_REVoiLevelUp · Stg3 (다른 압력축 → 청산 스텝업 검증)
# 목적: LP(레버리지) 2연속 기각 후, 캡틴 지시 "다른 압력축 시도 다시 검증후 청산세팅확정".
#   Trend Pressure(|ret_24h| 추세강도) · Execution Pressure(|CVD|)을 같은 청산연결+CPCV 틀로 이산R과 비교.
#   ★플래그(§10): Trend는 REV 진입(mom_24h)에 내재=중복위험 — '청산 시 추세강도'로만 해석.
#   ★고변동(atr Q80↑) 불간섭(§20) · 검증엔진 무수정(§15.1) exit_upgrade/bt_full import 재사용 · 레버3/75 고정.
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


def _p(*a): print(*a, flush=True)
def _z(x):
    x = np.asarray(x, float); return np.nan_to_num((x - np.nanmean(x)) / (np.nanstd(x) + 1e-9), nan=0.0)


def build_axis_scale(d1m, p, factor, axis, mode="cont"):
    """압력축 기반 fib_scale. axis='lev'/'exec'/'trend'. ★고변동(atr Q80↑) 불간섭(§20). 반환 (scale, 타이트봉비중)."""
    Rg = pd.read_parquet(REG); Rg["timestamp"] = pd.to_datetime(Rg["timestamp"], utc=True).dt.tz_localize(None)
    Rg = Rg.set_index("timestamp").sort_index()
    dfx = B.TS.resample_tf(d1m[["open", "high", "low", "close"]], p["rev_tf"]); idx = dfx.index
    pos = np.clip(np.searchsorted(Rg.index.values, idx.values, "right") - 1, 0, len(Rg) - 1)
    atr = Rg["atr60"].values[pos]
    if axis == "lev":
        P = _z(np.abs(Rg["oiz_s"].values[pos])) + _z(np.abs(Rg["fund_s"].values[pos])) + _z(np.abs(Rg["ls_s"].values[pos])) + (-_z(atr))
    elif axis == "exec":
        P = _z(np.abs(Rg["cvd_s"].values[pos]))                 # 체결압력 강도(CVD)
    elif axis == "trend":
        k = max(1, int(round(1440.0 / p["rev_tf"])))            # 24시간 = k봉
        ret = dfx["close"].pct_change(k).values
        P = _z(np.abs(ret))                                     # 추세 강도(|24h수익률|) — REV 역행위험
    else:
        raise ValueError(axis)
    if mode == "thr":
        scale = np.where(P > np.nanquantile(P, 0.60), factor, 1.0)
    else:
        lp = np.clip(P, 0.0, None); mx = np.nanmax(lp) or 1.0
        scale = 1.0 + (factor - 1.0) * (lp / mx)
    scale = np.where(atr >= np.nanquantile(atr, 0.8), 1.0, scale)  # ★고변동 보호
    return scale.astype(float), float(np.mean(scale > 1.0001))


def main():
    p = json.load(open(os.path.join(r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    EU.T_TF = p["rev_tf"]
    d1m = load_1m(); fund = load_funding()
    _, side = rev_side(d1m, p["rev_tf"], p["q"], p["qwin"])

    def gen(scale):
        return B.gen_trades(d1m, fund, p["rev_tf"], p["piv"], p["N"], (p["f1"], p["f2"], p["f3"]), p["iam"],
                            er_gate=0.0, ext_side=side, align_pivot=True, use_trend_flip=False, arm_bars=p["arm"], fib_scale=scale)

    _p("=" * 96)
    _p("[다른 압력축 → 청산 스텝업 — Stg3] 레버3/75 고정 · Trend(추세강도)·Exec(CVD) vs 기존 이산R · CPCV 표준6")
    base = EU.curve(gen(None)); mo, rt = EU.monthly_liq(gen(None)); cpb = EU.cpcv_std6(mo, rt)
    _p(f"[관문0 앵커 OFF] +{base['tot']:.0f}% · MDD {base['mdd']:.1f}% · 청산 {base['nliq']} · CPCV p25{cpb['p25']:+.0f}%·위반{cpb['mdd_viol']:.0f}%")

    configs = []
    for f in [1.4, 2.0]:
        sc_old, fo = EU.build_scale(d1m, p, f)
        sc_tr, ft = build_axis_scale(d1m, p, f, "trend", "cont")
        sc_ex, fe = build_axis_scale(d1m, p, f, "exec", "cont")
        configs += [(f"이산R ×{f} ({fo*100:.0f}%)", sc_old),
                    (f"Trend연속 ×{f} ({ft*100:.0f}%)", sc_tr),
                    (f"Exec연속 ×{f} ({fe*100:.0f}%)", sc_ex)]

    rows = []
    _p(f"\n{'설정':<22}{'full복리%':>10}{'MDD%':>8}{'CPCV_p25':>10}{'중앙':>8}{'음수폴드%':>9}{'MDD-20위반%':>11}")
    for nm, sc in configs:
        T = gen(sc); c = EU.curve(T); mo, rt = EU.monthly_liq(T); cp = EU.cpcv_std6(mo, rt)
        rows.append(dict(설정=nm, full복리=round(c["tot"]), MDD=round(c["mdd"], 1), CPCV_p25=round(cp["p25"], 1),
                         음수폴드=round(cp["neg"]), MDD20위반=round(cp["mdd_viol"])))
        _p(f"{nm:<22}{c['tot']:>10.0f}{c['mdd']:>8.1f}{cp['p25']:>10.1f}{cp['median']:>8.1f}{cp['neg']:>9.0f}{cp['mdd_viol']:>11.0f}")

    df = pd.DataFrame(rows); df.to_csv(os.path.join(HERE, "PressureAxes_compare_CPCV.csv"), index=False, encoding="utf-8-sig")
    passed = df[(df.CPCV_p25 > 0) & (df.MDD20위반 == 0)]
    _p("\n[본선 §5.7] p25>0 AND MDD-20위반0:")
    for _, r in passed.sort_values("CPCV_p25", ascending=False).iterrows():
        _p(f"   ✅ {r.설정}: full+{r.full복리:.0f}%·p25{r.CPCV_p25:+.1f}%·위반0%")
    if not len(passed): _p("   (이번 격자 본선 통과 없음)")
    _p("\n[저장] PressureAxes_compare_CPCV.csv")
    _p("[정직 注] Trend는 REV진입 내재=중복위험(§10). 어느 압력축도 이산R 못이기면 미시구조 청산연결=종결, 청산세팅(이산R/R+P) held-out 확정으로.")


if __name__ == "__main__":
    main()
