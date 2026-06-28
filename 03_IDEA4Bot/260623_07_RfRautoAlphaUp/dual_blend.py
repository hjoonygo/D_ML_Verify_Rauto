# -*- coding: utf-8 -*-
# [dual_blend.py] TS(추세+피보) + REV(회귀 combo+눌림목정렬+피보) 듀얼 블렌드 held-out 검증.
#   ★깨끗한 하니스(bt_full: 스톱캡·실펀딩·1m체결·현실수수료) 양쪽 다. 단짠배합으로 2025형 장세 메우는지.
#   판정: 학습23~24서 가중·노출 고정 → 25~26 held-out OOS 양수면 = 단일 못한 걸 배합이 해냄.
import os, sys, json, itertools
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import numpy as np, pandas as pd
import trendstack_signal_engine as TS
from fib_replay_1m import load_1m, load_funding
import bt_full as B

HERE = os.path.dirname(os.path.abspath(__file__)); TRAIN_END = pd.Timestamp("2024-12-31")


def _p(*a): print(*a, flush=True)
def zr(s): return s.rank(pct=True) - 0.5


def monthly(T):
    """거래 R → 월복리 수익률 시리즈(레버1)."""
    if len(T) == 0: return pd.Series(dtype=float)
    g = T.copy(); g["m"] = pd.to_datetime(g.et).dt.to_period("M")
    return g.groupby("m").R.apply(lambda x: (1 + x).prod() - 1)


def mstat(m):
    if len(m) == 0: return 0.0, 0.0, 0.0
    eq = np.cumprod(1 + m); tot = (eq[-1] - 1) * 100
    mdd = ((eq - np.maximum.accumulate(eq)) / np.maximum.accumulate(eq)).min() * 100
    return tot, mdd, ((1 + tot / 100) ** (12 / len(m)) - 1) * 100


def cpcv(port):
    g6 = np.array_split(np.arange(len(port)), 6); cg = []
    for c in itertools.combinations(range(6), 2):
        te = np.sort(np.concatenate([g6[k] for k in c])); cg.append(mstat(port[te])[2])
    return np.percentile(cg, 25), np.array(cg).min(), 100 * (np.array(cg) < 0).mean()


def main():
    d1m = load_1m(); fund = load_funding()
    bp = json.load(open(os.path.join(HERE, "best_params_full.json")))
    # ── TS 스트림(held-out 챔피언 config) ──
    _p("[TS] 추세+피보 생성…")
    TSt = B.gen_trades(d1m, fund, bp["sig_tf"], bp["pivot_tf"], bp["N"], (bp["fib1"], bp["fib2"], bp["fib3"]),
                       bp["init_atr_mult"], er_gate=bp["er_gate"])
    # ── REV 스트림: 8h combo(mom_24h+oi_z 역추세) → 눌림목 정렬 진입 + 피보청산(추세전환 off) ──
    _p("[REV] 회귀 combo 생성…")
    df8 = TS.resample_tf(d1m[["open", "high", "low", "close"]], 480)
    doi = pd.to_numeric(d1m["oi_zscore_24h"], errors="coerce")
    oi8 = doi.resample("480min", label="left", closed="left").last().reindex(df8.index).shift(1)
    mom = df8["open"].pct_change(3)
    combo = (-zr(mom)) * 0.048 + (-zr(oi8)) * 0.037
    hi = combo.quantile(0.67); lo = combo.quantile(0.33)
    side8 = np.where(combo >= hi, 1, np.where(combo <= lo, -1, 0))
    side8 = np.nan_to_num(side8, nan=0).astype(int)
    # ★TS에 적용한 피보 스텝업 설정 그대로 REV에 적용(pivot_tf·N·fib·초기손절 = TS와 동일)
    REVt = B.gen_trades(d1m, fund, 480, bp["pivot_tf"], bp["N"], (bp["fib1"], bp["fib2"], bp["fib3"]),
                        bp["init_atr_mult"], er_gate=0.0,
                        ext_side=side8, align_pivot=True, use_trend_flip=False, arm_bars=6)
    _p(f"  TS거래 {len(TSt)} | REV거래 {len(REVt)}")
    tsm = monthly(TSt); revm = monthly(REVt)
    allm = sorted(set(tsm.index) | set(revm.index))
    ts_s = tsm.reindex(allm, fill_value=0.0).values; rev_s = revm.reindex(allm, fill_value=0.0).values
    months = pd.PeriodIndex(allm, freq="M"); tr = months <= pd.Period("2024-12", "M"); te = ~tr
    corr = np.corrcoef(ts_s, rev_s)[0, 1]
    _p(f"\n[월상관 TS-REV] {corr:+.2f} (음수면 배합 좋음)")
    for nm, s in [("TS 단독", ts_s), ("REV 단독", rev_s)]:
        t, m, c = mstat(s); to, mo, co = mstat(s[te])
        _p(f"  {nm}: 전체 {t:+.0f}%/MDD{m:.0f}% | 검증OOS {to:+.0f}%/MDD{mo:.0f}%")
    # ── 가중·노출 스윕: 학습서 칼마최대 가중, 노출은 학습 MDD-20 맞춤 ──
    _p(f"\n[블렌드 가중 스윕] (학습23~24 기준 best, 노출=학습MDD-20)")
    _p(f"{'w_rev':>6}{'학습복리':>9}{'학습MDD':>8}{'검증복리':>9}{'검증MDD':>8}{'전체CPCVp25':>12}")
    best = None
    for w in np.round(np.arange(0.0, 1.01, 0.1), 1):
        port1 = (1 - w) * ts_s + w * rev_s
        _, mdd_tr, _ = mstat(port1[tr])
        e = min(2.0, max(0.3, 20.0 / abs(mdd_tr))) if mdd_tr < 0 else 1.0
        port = port1 * e
        tt, tm, _ = mstat(port[tr]); vt, vm, _ = mstat(port[te]); p25, _, _ = cpcv(port)
        _p(f"{w:>6.1f}{tt:>+9.0f}{tm:>+8.0f}{vt:>+9.0f}{vm:>+8.0f}{p25:>+12.1f}")
        cal = tt / abs(tm) if tm < 0 else tt
        if best is None or cal > best[0]: best = (cal, w, e, port)
    _, w, e, port = best
    tt, tm, tc = mstat(port[tr]); vt, vm, vc = mstat(port[te]); ft, fm, fc = mstat(port)
    p25, worst, neg = cpcv(port)
    _p("\n" + "=" * 64)
    _p(f"[채택 블렌드] w_rev={w:.1f} 노출={e:.2f} (학습 칼마최대)")
    _p(f"  학습(23~24)   복리 {tt:+.0f}% MDD {tm:.0f}% CAGR {tc:+.0f}%/yr")
    _p(f"  ★검증 OOS(25~26) 복리 {vt:+.0f}% MDD {vm:.0f}% CAGR {vc:+.0f}%/yr")
    _p(f"  전체          복리 {ft:+.0f}% MDD {fm:.0f}% CAGR {fc:+.0f}%/yr · CPCV p25 {p25:+.1f}%·음수폴드{neg:.0f}%")
    _p("[판정] 검증OOS 복리>0 AND CPCV p25>0 = 배합이 단일(OOS-2%) 넘어섬 = 진짜 진전. 미달이면 배합도 부족.")


if __name__ == "__main__":
    main()
