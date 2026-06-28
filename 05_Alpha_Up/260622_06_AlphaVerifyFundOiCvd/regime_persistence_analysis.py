# -*- coding: utf-8 -*-
# [regime_persistence_analysis.py] 레짐 상황변수 검증 — '관성 유지 vs 해체'(추세지속 vs 평균회귀).
#   가설(문헌: Hurst·BTC 0.52 취약추세): 우리 reversion 결합신호(mom+oi)는 회귀레짐서 작동·추세레짐서 실패.
#   레짐변수 = 자기상관(AC1)·분산비(VR) 롤링(과거만, 룩어헤드0). 조건부 IC·연도분포·게이팅 향상 측정.
#   ★전이 조기경보(분산/AC 상승)도 점검. 캡틴 '상황변수 변화 예측' 검증.
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
    P["ret"] = P["open"].pct_change(1)
    # 결합신호(IC가중·정렬, 고=고수익)
    P["combo"] = (-zr(P["mom_24h"])) * 0.048 + (-zr(P["oi_z"])) * 0.037
    # 레짐 상황변수 (전부 과거 롤링 = t에 알려짐)
    W = 45   # 45×8h=15일
    P["ac1"] = P["ret"].rolling(W).apply(lambda x: pd.Series(x).autocorr(1) if len(x) > 3 else np.nan, raw=False)
    # 분산비 VR(q): Var(q기간수익)/(q·Var(1기간)). >1 추세, <1 회귀
    q = 4
    P["rq"] = P["open"].pct_change(q)
    P["vr"] = P["rq"].rolling(W).var() / (q * P["ret"].rolling(W).var() + 1e-12)
    P["vol"] = P["ret"].rolling(W).std()

    win = P.dropna(subset=["combo", "oi_z", "ac1", "vr", "fwd_8h"])
    _p(f"[표본] {len(win)} | AC1 중앙 {win.ac1.median():+.3f} | VR 중앙 {win.vr.median():.2f}")

    # ① 레짐별 조건부 IC (결합신호 → 다음8h)
    _p("\n① 레짐별 조건부 IC (결합신호 mom+oi, 고=고수익 정렬이라 +IC=작동)")
    for nm, var, lo_lbl, hi_lbl in [("AC1(자기상관)", "ac1", "음(회귀)", "양(추세)"),
                                     ("VR(분산비)", "vr", "<1(회귀)", ">1(추세)")]:
        t1, t2 = win[var].quantile(1/3), win[var].quantile(2/3)
        for lbl, msk in [(f"하{lo_lbl}", win[var] <= t1), ("중", (win[var] > t1) & (win[var] < t2)), (f"상{hi_lbl}", win[var] >= t2)]:
            s = win[msk]; _p(f"  {nm} {lbl:<10} n={len(s):4d} | combo IC {ic(s['combo'], s['fwd_8h']):+.3f} | 평균 fwd {s['fwd_8h'].mean()*1e4:+.1f}bp")

    # ② 연도별 레짐 (2025 음수가 추세레짐이었나)
    _p("\n② 연도별 레짐 상태 (AC1>0·VR>1 = 추세=우리신호 불리)")
    win = win.copy(); win["year"] = win.index.year
    for y in sorted(win.year.unique()):
        s = win[win.year == y]
        _p(f"  {int(y)}: AC1 {s.ac1.mean():+.3f} | VR {s.vr.mean():.2f} | combo IC {ic(s['combo'], s['fwd_8h']):+.3f}")

    # ③ 레짐 게이팅: 회귀레짐(AC1<0)일 때만 신호 활성 → 향상되나
    gA = np.where(win["ac1"] < 0, win["combo"] - win["combo"].mean(), 0.0)
    gV = np.where(win["vr"] < 1.0, win["combo"] - win["combo"].mean(), 0.0)
    SIGS = [("combo 무게이트", win["combo"]),
            ("◆AC1<0 게이트(회귀때만)", pd.Series(gA, index=win.index)),
            ("◆VR<1 게이트(회귀때만)", pd.Series(gV, index=win.index))]
    N = len(SIGS); fwd = win["fwd_8h"]
    _p("\n③ 레짐 게이팅 — 검증 3단 (회귀레짐서만 거래)")
    _p(f"{'신호':<24}{'IC':>8}{'WF안정':>7}{'net SR':>8}{'CPCV p25':>10}{'DSR':>6}{'①가능':>6}{'③배포':>6}")
    _p("-" * 72)
    for nm, s in SIGS:
        r = AV.verify_signal(nm, s, fwd, n_trials=N)
        _p(f"{nm:<24}{r['ic']:>+8.3f}{r['wf']['sign_stability']:>6.0%}{r['net_sharpe']:>8.2f}"
           f"{r['cpcv']['p25']:>10.2f}{r['dsr']['dsr']:>6.2f}{'O' if r['possibility'] else 'X':>6}{'O' if r['deployable'] else 'X':>6}")

    # ④ 전이 조기경보: 레짐변수의 '변화'(분산/AC 상승)가 다음 레짐을 예측하나
    win["ac1_chg"] = win["ac1"].diff()
    win["vol_chg"] = win["vol"].diff()
    fut_ac = win["ac1"].shift(-5)   # 5봉(40h) 후 AC1
    _p("\n④ 전이 조기경보 (critical slowing down): 분산/AC 상승이 다음 레짐 예측?")
    _p(f"  vol변화 → 미래 AC1 상관: {ic(win['vol_chg'], fut_ac):+.3f} | AC1변화 → 미래 AC1: {ic(win['ac1_chg'], fut_ac):+.3f}")
    _p("[해석] 레짐별 IC가 갈리면(회귀서 강·추세서 약/음) = 관성 유지/해체가 신호 좌우 = 게이팅 가치. 전이예측은 문헌상 혼재.")


if __name__ == "__main__":
    main()
