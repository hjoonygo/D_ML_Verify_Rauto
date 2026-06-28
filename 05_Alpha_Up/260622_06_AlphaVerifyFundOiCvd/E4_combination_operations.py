# -*- coding: utf-8 -*-
# [E4_combination_operations.py] 결합 연산 연구 — 선행성 랭킹 + +/−/÷ 연산별 결합 (캡틴 지시 2026-06-22).
#   Direction1: 약한 신호엔 궁합좋은 직교 상대를 붙이되 '선행성 선명한 것부터'. 선행성=lead-lag IC 프로파일.
#   Direction2: 선행연구 종합 — 덧셈(IC가중, IR=IC√N 정석)·뺄셈(다이버전스)·나눗셈(정규화)·곱셈(조건부,과적합주의).
#   검증: alpha_verification_system 3단으로 각 연산결과 비교. 등가중 앙상블(E3) 대비.
import os
import numpy as np, pandas as pd
from scipy import stats
import alpha_verification_system as AV

HERE = os.path.dirname(os.path.abspath(__file__))


def _p(*a): print(*a, flush=True)
def zr(s): return s.rank(pct=True) - 0.5
def ic(x, y):
    m = x.notna() & y.notna(); return stats.spearmanr(x[m], y[m])[0] if m.sum() > 30 else np.nan


def main():
    P = AV.build_panel().sort_index()
    P["mom_24h"] = P["open"].pct_change(3)
    P["ret_8h"] = P["open"].pct_change(1)
    P["vol"] = P["ret_8h"].rolling(30, min_periods=10).std()        # 변동성(정규화용)
    # 미래 lag별 8h수익 (선행성 프로파일)
    for k in range(4):
        P[f"fwd_lag{k}"] = P["open"].shift(-(k+1)) / P["open"].shift(-k) - 1.0

    comps = ["mom_24h", "oi_z", "fund_slope"]
    win = P.dropna(subset=comps + ["fwd_lag0", "vol"])
    _p(f"[표본] {len(win)}")

    # ── ① 선행성(lead-lag) 프로파일: 각 신호의 IC가 미래 어느 lag서 선명한가 ──
    _p("\n① 선행성 프로파일 — 신호 IC vs 미래 8h수익(lag0=다음8h ~ lag3=24~32h후)")
    _p(f"{'신호':<14}{'lag0':>9}{'lag1':>9}{'lag2':>9}{'lag3':>9}  (|IC| 큰 lag서 선명·빨리 감쇠=선행 뚜렷)")
    lead = {}
    for c in comps + ["fund"]:
        ics = [ic(win[c], win[f"fwd_lag{k}"]) for k in range(4)]
        lead[c] = ics
        _p(f"{c:<14}" + "".join(f"{v:>+9.3f}" for v in ics))
    # 선행성 점수 = |lag0| (즉시 선행 선명도) 기준 랭킹
    order = sorted(comps, key=lambda c: -abs(lead[c][0]))
    _p(f"  → 선행성(즉시 lag0) 랭킹: " + " > ".join(f"{c}({abs(lead[c][0]):.3f})" for c in order))

    # ── ② 연산별 결합 (선행성 순서로 정렬·IC방향 정렬) ──
    sign = {c: (np.sign(ic(win[c], win["fwd_lag0"])) or 1.0) for c in comps}
    a = {c: zr(win[c]) * sign[c] for c in comps}            # +방향=고수익 정렬
    icw = {c: abs(ic(win[c], win["fwd_lag0"])) for c in comps}
    icsum = sum(icw.values())

    sig = {}
    sig["+ 등가중(E3)"] = sum(a[c] for c in comps)
    sig["+ IC가중(정석)"] = sum(a[c] * icw[c] / icsum for c in comps)            # 덧셈: IC비례 가중
    sig["− 다이버전스(mom−oi)"] = zr(win["mom_24h"]) - zr(win["oi_z"])           # 뺄셈: 가격vs포지셔닝 불일치
    sig["÷ 변동성정규화(mom/vol)"] = win["mom_24h"] / (win["vol"] + 1e-9)        # 나눗셈: 위험조정 모멘텀
    sig["÷ oi_z÷|mom|"] = win["oi_z"] / (win["mom_24h"].abs() + 1e-3)           # 나눗셈: 모멘텀당 포지셔닝
    # 선행성순 2개만(최선행 mom + 차선행) IC가중
    top2 = order[:2]
    sig[f"+ 선행top2 IC가중({top2[0][:4]}+{top2[1][:4]})"] = (a[top2[0]] * icw[top2[0]] + a[top2[1]] * icw[top2[1]]) / (icw[top2[0]] + icw[top2[1]])

    _p("\n② 연산별 결합 — 검증시스템 3단 (vs 단독 최강 mom_24h)")
    _p(f"{'결합':<30}{'IC':>8}{'방향':>5}{'WF안정':>7}{'net SR':>8}{'CPCV p25':>10}{'DSR':>6}{'①가능':>6}{'③배포':>6}")
    _p("-" * 92)
    fwd = win["fwd_lag0"]
    base = AV.verify_signal("mom_24h 단독", win["mom_24h"], fwd, n_trials=1)
    _p(f"{'mom_24h 단독(기준)':<30}{base['ic']:>+8.3f}{'+' if base['direction']>0 else '-':>5}"
       f"{base['wf']['sign_stability']:>6.0%}{base['net_sharpe']:>8.2f}{base['cpcv']['p25']:>10.2f}"
       f"{base['dsr']['dsr']:>6.2f}{'O' if base['possibility'] else 'X':>6}{'O' if base['deployable'] else 'X':>6}")
    N = len(sig) + 1; rows = []
    for nm, s in sig.items():
        r = AV.verify_signal(nm, s, fwd, n_trials=N)
        _p(f"{nm:<30}{r['ic']:>+8.3f}{'+' if r['direction']>0 else '-':>5}"
           f"{r['wf']['sign_stability']:>6.0%}{r['net_sharpe']:>8.2f}{r['cpcv']['p25']:>10.2f}"
           f"{r['dsr']['dsr']:>6.2f}{'O' if r['possibility'] else 'X':>6}{'O' if r['deployable'] else 'X':>6}")
        rows.append(dict(combo=nm, ic=r['ic'], wf=r['wf']['sign_stability'], net_sharpe=r['net_sharpe'],
                         cpcv_p25=r['cpcv']['p25'], dsr=r['dsr']['dsr'], info_sharpe=r['info_sharpe'],
                         possibility=r['possibility'], deployable=r['deployable']))
    pd.DataFrame(rows).to_csv(os.path.join(HERE, "E4_results.csv"), index=False, encoding="utf-8-sig")
    best = max(rows, key=lambda r: (r['wf'], r['net_sharpe']))
    _p("-" * 92)
    _p(f"[최고 결합] {best['combo']}: WF {best['wf']:.0%} / net SR {best['net_sharpe']:.2f} / info SR {best['info_sharpe']:.2f}")
    _p("[해석] IC가중 덧셈이 정석(IR=IC√N). 뺄셈=다이버전스, 나눗셈=정규화. 곱셈은 E1서 과적합으로 제외.")
    _p("[다음] 합격 결합을 ★1m 실체결 교정판 SL+눌림목 로직으로 시뮬(낙관체결 금지) → 진짜 알파 확인.")


if __name__ == "__main__":
    main()
