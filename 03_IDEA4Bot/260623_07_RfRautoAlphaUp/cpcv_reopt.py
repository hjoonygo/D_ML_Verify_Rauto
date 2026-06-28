# -*- coding: utf-8 -*-
# [cpcv_reopt.py] ★진짜 CPCV (폴드마다 재선택·purge·테스트 OOS) — 36개월 전부 정직하게 (캡틴 지시 2026-06-24, §5.7 본선).
#   설계: 후보 N개를 한 번 계산(가장 비쌈) → 각 폴드는 '자기 학습구간 Calmar'로만 후보 선택(커닝0) → 보류 테스트 구간 채점.
#   누수차단: test 인접 1개월 purge/embargo. 노출=각 폴드 학습 MDD-20 해석적(테스트에 동일적용).
#   모드: year4(연도4그룹 leave-one-out=4폴드, 참고) + std6(6등분 choose-2=15경로, 본선) 둘 다 산출.
#   ★30분 ETA 로깅(time.time). 같은 seed=재현. 출력 cpcv_reopt_result.txt.
import os, sys, json, time, itertools
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import numpy as np, pandas as pd
import trendstack_signal_engine as TS
from fib_replay_1m import load_1m, load_funding
import bt_full as B
from blend_opt import rev_side, monthly
HERE = os.path.dirname(os.path.abspath(__file__))
T0 = time.time()


def _p(*a):
    print(*a, flush=True)
    with open(os.path.join(HERE, "cpcv_reopt_run.log"), "a", encoding="utf-8") as f:
        f.write(" ".join(str(x) for x in a) + "\n")


def el(): return time.time() - T0
def hm(s): return f"{int(s//3600)}h{int((s%3600)//60):02d}m"


def cmdd(m):
    if len(m) < 2: return 0.0, 0.0, 0.0
    eq = np.cumprod(1 + m); tot = (eq[-1] - 1) * 100
    mdd = ((eq - np.maximum.accumulate(eq)) / np.maximum.accumulate(eq)).min() * 100
    cagr = ((1 + tot / 100) ** (12 / len(m)) - 1) * 100
    return tot, mdd, cagr


def sample(rng):
    return dict(ts_tf=int(rng.choice([240, 420, 480, 720])), rev_tf=int(rng.choice([240, 480, 720])),
                piv=int(rng.choice([20, 60, 240])), N=int(rng.integers(2, 9)),
                f1=float(rng.uniform(0.15, 0.45)), f2=float(rng.uniform(0.45, 0.65)), f3=float(rng.uniform(0.65, 0.92)),
                iam=float(rng.uniform(0.5, 3.0)), erg=float(rng.uniform(0.0, 0.4)),
                q=float(rng.uniform(0.2, 0.4)), qwin=int(rng.integers(20, 80)),
                arm=int(rng.integers(2, 12)), w=float(rng.uniform(0.4, 0.95)))


def cand_monthly(d1m, fund, p, cal):
    fib = (p["f1"], p["f2"], p["f3"])
    TSt = B.gen_trades(d1m, fund, p["ts_tf"], p["piv"], p["N"], fib, p["iam"], er_gate=p["erg"])
    _, side = rev_side(d1m, p["rev_tf"], p["q"], p["qwin"])
    REVt = B.gen_trades(d1m, fund, p["rev_tf"], p["piv"], p["N"], fib, p["iam"], er_gate=0.0,
                        ext_side=side, align_pivot=True, use_trend_flip=False, arm_bars=p["arm"])
    tsm = monthly(TSt); revm = monthly(REVt)
    allm = sorted(set(tsm.index) | set(revm.index))
    if not allm: return None
    ts_s = tsm.reindex(allm, fill_value=0.0); rev_s = revm.reindex(allm, fill_value=0.0)
    base = (1 - p["w"]) * ts_s + p["w"] * rev_s
    return pd.Series(base.values, index=pd.PeriodIndex(allm, freq="M")).reindex(cal, fill_value=0.0).values


def fold_eval(cands, series, cal, test_idx):
    """test 구간 보류 → 나머지(인접1달 purge)서 학습Calmar 최고 후보 선택 → test 채점."""
    test_mask = np.zeros(len(cal), bool); test_mask[test_idx] = True
    purge = np.zeros(len(cal), bool)
    for ti in test_idx:
        for j in (ti - 1, ti + 1):
            if 0 <= j < len(cal): purge[j] = True
    train_mask = ~test_mask & ~purge
    best = None
    for s in series:
        trm = s[train_mask]
        tot, mdd, _ = cmdd(trm)
        cal_score = tot / abs(mdd) if mdd < 0 else tot
        if best is None or cal_score > best[0]: best = (cal_score, s, mdd)
    _, s, tr_mdd = best
    e = float(np.clip(20.0 / abs(tr_mdd), 0.3, 2.0)) if tr_mdd < 0 else 1.0
    _, te_mdd, te_cagr = cmdd(e * s[test_mask])
    return te_cagr, te_mdd


def run_cpcv(name, groups, choose, cands, series, cal):
    folds = list(itertools.combinations(range(len(groups)), choose))
    cg = []; mdds = []
    for c in folds:
        test_idx = np.concatenate([groups[k] for k in c])
        ca, md = fold_eval(cands, series, cal, test_idx)
        cg.append(ca); mdds.append(md)
    cg = np.array(cg); mdds = np.array(mdds)
    p25 = np.percentile(cg, 25)
    _p(f"\n[{name}] {len(folds)}폴드 (재선택·purge·테스트OOS)")
    _p(f"  테스트 연환산수익률: 중앙 {np.median(cg):+.1f}% · p25 {p25:+.1f}% · 최악 {cg.min():+.1f}%/yr")
    _p(f"  음수폴드 {100*(cg<0).mean():.0f}% · MDD최악 {mdds.min():.0f}% · MDD-20위반 {100*(mdds<-20).mean():.0f}%")
    return dict(name=name, folds=len(folds), median=float(np.median(cg)), p25=float(p25),
                worst=float(cg.min()), neg=float(100*(cg < 0).mean()),
                mdd_worst=float(mdds.min()), mdd_viol=float(100*(mdds < -20).mean()))


def main():
    NC = int(sys.argv[1]) if len(sys.argv) > 1 else 150
    _p(f"\n===== CPCV 재최적화 시작 (후보 {NC}개) {time.strftime('%H:%M')} =====")
    d1m = load_1m(); fund = load_funding()
    cal = pd.period_range(d1m.index.min().to_period("M"), d1m.index.max().to_period("M"), freq="M")
    _p(f"[달력] {cal[0]} ~ {cal[-1]} ({len(cal)}개월) · 데이터 로드 {hm(el())}")
    rng = np.random.default_rng(7)
    cands = []; series = []
    for i in range(NC):
        p = sample(rng)
        try:
            s = cand_monthly(d1m, fund, p, cal)
        except Exception:
            s = None
        if s is not None: cands.append(p); series.append(s)
        if (i + 1) % 10 == 0 or i == NC - 1:
            done = i + 1; per = el() / done; eta = per * (NC - done)
            _p(f"  후보 {done}/{NC} · 경과 {hm(el())} · 후보당 {per:.0f}s · ★예상종료 {hm(eta)} 뒤 ({time.strftime('%H:%M', time.localtime(time.time()+eta))})")
    _p(f"[후보계산 완료] 유효 {len(cands)}개 · 총 {hm(el())}")
    # 그룹 정의
    yr = np.array([m.year for m in cal])
    g_year = [np.where(yr == y)[0] for y in sorted(set(yr))]
    g_std6 = [np.array(x) for x in np.array_split(np.arange(len(cal)), 6)]
    r1 = run_cpcv("연도그룹 leave-one-out (참고)", g_year, 1, cands, series, cal)
    r2 = run_cpcv("표준6그룹 choose-2 = 15경로 (본선)", g_std6, 2, cands, series, cal)
    out = dict(candidates=len(cands), calendar=f"{cal[0]}~{cal[-1]}", year4=r1, std6=r2, runtime=hm(el()))
    json.dump(out, open(os.path.join(HERE, "cpcv_reopt_result.json"), "w"), indent=2, ensure_ascii=False)
    _p("\n" + "=" * 60)
    _p(f"[★본선 표준6 판정] p25 {r2['p25']:+.1f}%/yr · 음수폴드 {r2['neg']:.0f}% · MDD-20위반 {r2['mdd_viol']:.0f}%")
    ok = r2["p25"] > 0 and r2["mdd_viol"] == 0
    _p(f"[결론] {'채택가능 — 36개월 전구간 정직검증 통과(p25양수·위반0)' if ok else '미달 — p25 또는 MDD위반(헛수치 위 쌓기 금지)'}")
    _p(f"[총 소요] {hm(el())} · 저장 cpcv_reopt_result.json")


if __name__ == "__main__":
    main()
