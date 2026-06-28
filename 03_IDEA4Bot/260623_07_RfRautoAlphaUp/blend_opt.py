# -*- coding: utf-8 -*-
# [blend_opt.py] TS+REV 듀얼 블렌드 held-out 최적화 (캡틴 지시 2026-06-24: TF부터 재최적화·1m환각차단·정직화).
#   ★REV 신호 정직화: 롤링z(과거 qwin봉)·롤링분위 → full표본 룩어헤드 제거(이게 진짜/가짜 가름).
#   ★1m 체결검증: gen_trades 내장(스톱터치·갭=불리). ★스톱캡·실펀딩·현실수수료.
#   ★피보 스텝업: TS·REV 공유 설정(캡틴 "TS피보를 REV에"). 워크포워드: 학습≤2024 최적→25~26 held-out.
#   목적: 학습 CPCV p25 최대(robust), 노출=학습MDD-20 해석적. 출력 best_blend.json.
import os, sys, json, itertools
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import numpy as np, pandas as pd
try:
    import optuna
except Exception:
    optuna = None
import trendstack_signal_engine as TS
from fib_replay_1m import load_1m, load_funding
import bt_full as B
if optuna is not None:
    optuna.logging.set_verbosity(optuna.logging.WARNING)
HERE = os.path.dirname(os.path.abspath(__file__)); TRAIN = pd.Period("2024-12", "M")


def _p(*a): print(*a, flush=True)


def rev_side(d1m, rev_tf, q, qwin):
    """REV 신호 = 롤링z(mom·oi) 합성 → 롤링분위 임계(전부 과거만, 룩어헤드0)."""
    df = TS.resample_tf(d1m[["open", "high", "low", "close"]], rev_tf)
    oi = pd.to_numeric(d1m["oi_zscore_24h"], errors="coerce").resample(f"{rev_tf}min", label="left", closed="left").last().reindex(df.index).shift(1)
    mom = df["open"].pct_change(3)
    zm = (mom - mom.rolling(qwin).mean()) / (mom.rolling(qwin).std() + 1e-9)
    zo = (oi - oi.rolling(qwin).mean()) / (oi.rolling(qwin).std() + 1e-9)
    combo = (-zm) * 0.048 + (-zo) * 0.037
    hiq = combo.rolling(qwin).quantile(1 - q); loq = combo.rolling(qwin).quantile(q)
    side = np.where(combo >= hiq, 1, np.where(combo <= loq, -1, 0))
    return df, np.nan_to_num(side, nan=0).astype(int)


def monthly(T):
    if len(T) == 0: return pd.Series(dtype=float)
    g = T.copy(); g["m"] = pd.to_datetime(g.et).dt.to_period("M")
    return g.groupby("m").R.apply(lambda x: (1 + x).prod() - 1)


def mstat(m):
    if len(m) < 2: return 0.0, 0.0
    eq = np.cumprod(1 + m); return (eq[-1] - 1) * 100, ((eq - np.maximum.accumulate(eq)) / np.maximum.accumulate(eq)).min() * 100


def cpcv_p25(port):
    if len(port) < 12: return -9.0
    g6 = np.array_split(np.arange(len(port)), 6); cg = []
    for c in itertools.combinations(range(6), 2):
        te = np.sort(np.concatenate([g6[k] for k in c])); m = port[te]
        eq = np.cumprod(1 + m); tot = (eq[-1] - 1) * 100
        cg.append(((1 + tot / 100) ** (12 / len(m)) - 1) * 100)
    return float(np.percentile(cg, 25))


def blend_series(d1m, fund, p):
    TSt = B.gen_trades(d1m, fund, p["ts_tf"], p["piv"], p["N"], (p["f1"], p["f2"], p["f3"]), p["iam"], er_gate=p["erg"])
    df, side = rev_side(d1m, p["rev_tf"], p["q"], p["qwin"])
    REVt = B.gen_trades(d1m, fund, p["rev_tf"], p["piv"], p["N"], (p["f1"], p["f2"], p["f3"]), p["iam"],
                        er_gate=0.0, ext_side=side, align_pivot=True, use_trend_flip=False, arm_bars=p["arm"])
    tsm = monthly(TSt); revm = monthly(REVt)
    allm = sorted(set(tsm.index) | set(revm.index))
    if len(allm) < 12: return None, None, None
    ts_s = tsm.reindex(allm, fill_value=0.0).values; rev_s = revm.reindex(allm, fill_value=0.0).values
    months = pd.PeriodIndex(allm, freq="M")
    return (1 - p["w"]) * ts_s + p["w"] * rev_s, months, (len(TSt), len(REVt))


def main():
    d1m = load_1m(); fund = load_funding()
    nt = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    _p(f"[blend 최적화 {nt} trials] 학습≤2024→25~26 held-out · REV 롤링정직 · 1m검증")

    def obj(t):
        p = dict(ts_tf=t.suggest_categorical("ts_tf", [240, 420, 480, 720]),
                 rev_tf=t.suggest_categorical("rev_tf", [240, 480, 720]),
                 piv=t.suggest_categorical("piv", [20, 60, 240]),
                 N=t.suggest_int("N", 2, 8), f1=t.suggest_float("f1", 0.15, 0.45),
                 f2=t.suggest_float("f2", 0.45, 0.65), f3=t.suggest_float("f3", 0.65, 0.92),
                 iam=t.suggest_float("iam", 0.5, 3.0), erg=t.suggest_float("erg", 0.0, 0.4),
                 q=t.suggest_float("q", 0.2, 0.4), qwin=t.suggest_int("qwin", 20, 80),
                 arm=t.suggest_int("arm", 2, 12), w=t.suggest_float("w", 0.4, 0.95))
        try:
            port1, months, _ = blend_series(d1m, fund, p)
            if port1 is None: return -9.0
            tr = months <= TRAIN
            if tr.sum() < 8 or (~tr).sum() < 4: return -9.0
            return cpcv_p25(port1[tr])    # ★학습 CPCV p25(robust) 최대 — held-out 25~26은 안봄
        except Exception:
            return -9.0

    st = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=7))
    st.optimize(obj, n_trials=nt, show_progress_bar=False)
    bp = st.best_params
    p = dict(ts_tf=bp["ts_tf"], rev_tf=bp["rev_tf"], piv=bp["piv"], N=bp["N"], f1=bp["f1"], f2=bp["f2"], f3=bp["f3"],
             iam=bp["iam"], erg=bp["erg"], q=bp["q"], qwin=bp["qwin"], arm=bp["arm"], w=bp["w"])
    port1, months, (nts, nrev) = blend_series(d1m, fund, p)
    tr = months <= TRAIN; te = ~tr
    _, mdd_tr = mstat(port1[tr]); e = min(2.0, max(0.3, 20.0 / abs(mdd_tr))) if mdd_tr < 0 else 1.0
    p["expo"] = e; port = port1 * e
    tt, tm = mstat(port[tr]); vt, vm = mstat(port[te]); ft, fm = mstat(port)
    _p("\n" + "=" * 64)
    _p(f"[최적 blend] TS_TF={p['ts_tf']} REV_TF={p['rev_tf']} 눌림목={p['piv']} N={p['N']} 피보=({p['f1']:.2f},{p['f2']:.2f},{p['f3']:.2f}) ATR×{p['iam']:.2f}")
    _p(f"            REV 분위{p['q']:.2f}/롤링{p['qwin']} arm{p['arm']} | w_rev={p['w']:.2f} 노출={e:.2f} | TS{nts}·REV{nrev}거래")
    _p(f"  학습(23~24)     복리 {tt:+.0f}% MDD {tm:.0f}%")
    _p(f"  ★검증 OOS(25~26) 복리 {vt:+.0f}% MDD {vm:.0f}%   ← 롤링정직·held-out 진짜값")
    _p(f"  전체 CPCV p25 {cpcv_p25(port):+.1f}% | 학습 CPCV p25 {cpcv_p25(port[tr]):+.1f}%")
    json.dump(p, open(os.path.join(HERE, "best_blend.json"), "w"), indent=2)
    _p("[저장] best_blend.json")
    _p("[판정] 검증 OOS 복리>0 = 롤링정직(룩어헤드제거)에도 살아남음 = 진짜 알파. 음수면 = full표본 분위가 부풀린 것.")


if __name__ == "__main__":
    main()
