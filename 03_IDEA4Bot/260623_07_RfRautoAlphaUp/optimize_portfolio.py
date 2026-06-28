# -*- coding: utf-8 -*-
# [optimize_portfolio.py] ML(베이지안 TPE) 최적화 — REV 피보청산/진입정렬 파라미터 + 블렌드가중 + 노출.
#   ★과적합 방지(RfRauto 존재이유): 학습 2023~2024서만 최적화 → 검증 2025~2026 OOS 정직판정 + 전체 CPCV.
#   ★TS는 §9 확정 챔피언이라 고정(재최적화=§9 위반). REV+블렌드만 최적화.
#   ★탐색은 빠른 7h틱체결, 최종 채택 config만 1m 실체결 재검증(캡틴 1m검증 규칙은 '확정수치'에 적용).
#   실펀딩 조인·진입정렬(눌림목)·동치앵커·순차는 fib_replay_1m 그대로.
import sys, os, itertools
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import numpy as np, pandas as pd, optuna
import trendstack_signal_engine as TS
import vol_sizing_compare as V
from fib_replay_1m import load_1m, load_funding, fib_loop, sized, mstat, cpcv_p25, COST

optuna.logging.set_verbosity(optuna.logging.WARNING)
HERE = os.path.dirname(os.path.abspath(__file__))
TRAIN_END = pd.Period("2024-12", "M")   # 학습 2023-05~2024-12 / 검증 2025-01~2026-04


def zr(s): return s.rank(pct=True) - 0.5


def main():
    d1m = load_1m(); fund = load_funding()
    doi = pd.to_numeric(d1m["oi_zscore_24h"], errors="coerce")
    # TS 고정(챔피언) — 1회 생성
    df7h = TS.resample_tf(d1m[["open", "high", "low", "close"]], 420); sig7 = TS.compute_signals(df7h)
    oi7 = doi.reindex(df7h.index, method="ffill").values
    TSr = fib_loop(df7h, sig7, d1m, ext_side=None, use_trend_flip=True, fill_1m=False,
                   lev=1.0, cost=COST, er=sig7["er"], er_gate=0.40, tf_min=420, oi_arr=oi7, fund_pref=fund)
    _, tsm = sized(TSr)
    # REV 신호 재료(combo) — 1회
    df8h = TS.resample_tf(d1m[["open", "high", "low", "close"]], 480); sig8 = TS.compute_signals(df8h)
    _, S, _ = V.build(V.find_data())
    sidx = S.index.tz_localize(None)
    combo8 = pd.Series(S["combo"].values, index=sidx).reindex(df8h.index)
    oi8 = pd.Series(S["oi_z"].values, index=sidx).reindex(df8h.index).values
    print(f"[준비] TS거래 {len(TSr)} | df8h {len(df8h)} | 학습≤{TRAIN_END} / 검증>")

    def build_rev(q, fib, atrm, arm):
        hi = combo8.quantile(1 - q); lo = combo8.quantile(q)
        side8 = np.where(combo8 >= hi, 1, np.where(combo8 <= lo, -1, 0))
        side8 = np.nan_to_num(side8, nan=0).astype(int)
        R = fib_loop(df8h, sig8, d1m, ext_side=side8, use_trend_flip=False, fill_1m=False,
                     lev=1.0, cost=COST, tf_min=480, oi_arr=oi8, fund_pref=fund,
                     init_atr_mult=atrm, fib=fib, align_pivot=True, arm_bars=arm)
        return R

    def blend_series(revm, w, e):
        allm = sorted(set(tsm.index) | set(revm.index))
        ts_s = tsm.reindex(allm, fill_value=0.0).values; rev_s = revm.reindex(allm, fill_value=0.0).values
        port = (0.2 if False else (1 - w)) * ts_s + w * rev_s
        return np.array([str(x) for x in allm]), port * e

    def exp_star(port_unlev, mask):
        """학습 MDD를 -20%에 맞추는 노출(해석적, MDD~노출 선형). 캡=2.0."""
        _, mdd1, _ = mstat(port_unlev[mask])
        if mdd1 >= -1e-9: return 2.0
        return float(min(2.0, max(0.3, 20.0 / abs(mdd1))))

    def objective(trial):
        q = trial.suggest_float("rev_q", 0.20, 0.40)
        f1 = trial.suggest_float("fib1", 0.15, 0.45)
        f2 = trial.suggest_float("fib2", 0.45, 0.65)
        f3 = trial.suggest_float("fib3", 0.65, 0.90)
        atrm = trial.suggest_float("init_atr_mult", 0.5, 3.0)
        arm = trial.suggest_int("arm_bars", 2, 14)
        w = trial.suggest_float("w_rev", 0.5, 0.95)
        try:
            R = build_rev(q, (f1, f2, f3), atrm, arm)
            if len(R) < 30: return -10.0
            _, revm = sized(R)
            months, port1 = blend_series(revm, w, 1.0)   # 노출1.0(무배율)
            yrs = pd.PeriodIndex(months, freq="M"); tr = yrs <= TRAIN_END
            if tr.sum() < 8: return -10.0
            tot, mdd, cagr = mstat(port1[tr])
            if mdd >= -1e-9: return -10.0
            calmar = cagr / abs(mdd)         # 노출무관 위험조정 — 이걸 최적화
            return calmar
        except Exception:
            return -10.0

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=7))
    study.optimize(objective, n_trials=160, show_progress_bar=False)
    bp = study.best_params
    print(f"\n[최적 params (학습기준)] {bp}")

    # ── 최종 채택 config을 1m 실체결로 재검증 + 학습/검증/전체/CPCV ──
    R = build_rev(bp["rev_q"], (bp["fib1"], bp["fib2"], bp["fib3"]), bp["init_atr_mult"], bp["arm_bars"])
    R1 = fib_loop(df8h, sig8, d1m,
                  ext_side=np.nan_to_num(np.where(combo8 >= combo8.quantile(1 - bp["rev_q"]), 1,
                           np.where(combo8 <= combo8.quantile(bp["rev_q"]), -1, 0)), nan=0).astype(int),
                  use_trend_flip=False, fill_1m=True, lev=1.0, cost=COST, tf_min=480, oi_arr=oi8,
                  fund_pref=fund, init_atr_mult=bp["init_atr_mult"], fib=(bp["fib1"], bp["fib2"], bp["fib3"]),
                  align_pivot=True, arm_bars=bp["arm_bars"])
    _, revm = sized(R1)
    months, port1 = blend_series(revm, bp["w_rev"], 1.0)
    yrs = pd.PeriodIndex(months, freq="M"); tr = yrs <= TRAIN_END; te = ~tr
    e_star = exp_star(port1, tr)            # 학습 MDD-20 맞춘 노출(검증엔 그대로 적용=OOS 정직)
    port = port1 * e_star
    print(f"[노출] 학습 MDD-20% 맞춘 노출 e*={e_star:.2f} (검증/전체에 동일적용)")
    print("\n" + "=" * 78)
    print("최적 config 정직판정 (REV 1m 실체결·실펀딩·진입정렬·피보 스텝업)")
    print("=" * 78)
    for nm, msk in [("학습(23~24)", tr), ("검증 OOS(25~26)", te), ("전체", np.ones(len(port), bool))]:
        tot, mdd, cagr = mstat(port[msk])
        print(f"  {nm:<16} 복리 {tot:>+7.0f}%  MDD {mdd:>+6.1f}%  CAGR {cagr:>+6.1f}%/yr")
    p25, worst, neg = cpcv_p25(port)
    tot, mdd, cagr = mstat(port)
    print(f"  전체 CPCV 표준6: p25 CAGR {p25:+.1f}% · 최악 {worst:+.1f}% · 음수폴드 {neg:.0f}%")
    print(f"  REV 거래 {len(R1)} 승률 {100*(R1.R>0).mean():.0f}% | 연도별:")
    R1["y"] = pd.to_datetime(R1.et).dt.year
    print("   " + "  ".join(f"{y}:{((1+g.R).prod()-1)*100:+.0f}%({len(g)})" for y, g in R1.groupby("y")))
    print("\n[판정] 검증 OOS CAGR>0 AND 전체 CPCV p25>0 AND MDD>-20 = 진짜 채택. 미달=과적합/미완 명시.")
    R1.to_csv(os.path.join(HERE, "ledger_rev_opt_1m.csv"), index=False, encoding="utf-8-sig")
    import json
    json.dump(bp, open(os.path.join(HERE, "best_params.json"), "w"), indent=2)
    print("[저장] ledger_rev_opt_1m.csv · best_params.json")


if __name__ == "__main__":
    main()
