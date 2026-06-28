# -*- coding: utf-8 -*-
# [trade_forensics.py] 수익률검증 마지막 고리 — 거래 복기 엔진 (재사용, 04_공용엔진코드/verification).
#   trade_diagnostics가 만든 ledger(ret·mae·mfe·tag·year…)를 입력받아 '실제 거래를 철저히 복기':
#   ① R-multiple 분포 + SQN(Van Tharp) ② 택소노미(진입직후SL/수익내다손절/큰수익후반납)
#   ③ 어디서 수익 갉아먹나: DD 귀속·연속손절·Edge decay(손익비 격감) ④ Monte Carlo(MDD·연속손절·risk of ruin).
#   선행연구: Sweeney(MAE/MFE)·Van Tharp(R·SQN)·WFA(edge decay)·risk of ruin(Monte Carlo).
#   ★[B.더 연구]: 라이브 edge decay·거래 클러스터링·틱슬립·SHAP 인과·레짐별 R분포 — 이 엔진에 후속 모듈로 추가.
import os, sys, glob, itertools
import numpy as np, pandas as pd

SL_RISK = 0.02   # 1R = 초기 손절거리(2%). ledger에 risk 없으면 이 값.


def _p(*a): print(*a, flush=True)


def find_ledger(arg=None):
    if arg and os.path.exists(arg): return arg
    for pat in [r"D:\ML\RfRauto\03_IDEA4Bot\*\trade_diagnostics_ledger.csv",
                r"D:\ML\RfRauto\05_Alpha_Up\*\trade_diagnostics_ledger.csv"]:
        g = glob.glob(pat)
        if g: return g[0]
    raise FileNotFoundError("trade_diagnostics_ledger.csv 못찾음 (먼저 trade_diagnostics 실행)")


def mc_sim(ret, n=2000, seed=7):
    rng = np.random.default_rng(seed)
    mdds = np.empty(n); streaks = np.empty(n)
    for k in range(n):
        p = rng.choice(ret, size=len(ret), replace=True)  # 부트스트랩
        eq = np.cumprod(1 + p); pk = np.maximum.accumulate(eq)
        mdds[k] = ((eq - pk) / pk).min() * 100
        s = mx = 0
        for x in p:
            if x < 0: s += 1; mx = max(mx, s)
            else: s = 0
        streaks[k] = mx
    return mdds, streaks


def main():
    led = find_ledger(sys.argv[1] if len(sys.argv) > 1 else None)
    T = pd.read_csv(led)
    _p(f"[복기 대상] {os.path.basename(os.path.dirname(led))}/{os.path.basename(led)} | {len(T)}거래")
    ret = T["ret"].values
    T["R"] = T["ret"] / SL_RISK

    # ── ① R-multiple 분포 + SQN ──
    expR = T.R.mean(); sdR = T.R.std()
    sqn = expR / sdR * np.sqrt(len(T)) if sdR > 0 else 0
    winR = T.R[T.R > 0].mean(); lossR = T.R[T.R < 0].mean()
    _p("\n① R-multiple (1R=초기손절 2%, Van Tharp)")
    _p(f"  expectancy {expR:+.3f}R | SQN {sqn:.2f} ({'우수>2.5' if sqn>2.5 else '평범1.6~2.5' if sqn>1.6 else '약함<1.6'})"
       f" | 평균이익 {winR:+.2f}R · 평균손실 {lossR:+.2f}R | 손익비 {abs(winR/lossR):.2f}")
    for lo, hi, lbl in [(-99, -1, "≤-1R 풀손절"), (-1, 0, "-1~0R 부분손실"), (0, 1, "0~1R 소익"),
                        (1, 3, "1~3R 중익"), (3, 99, "≥3R 대익")]:
        s = T.R[(T.R >= lo) & (T.R < hi)]
        if len(s): _p(f"    {lbl:<14} {len(s):3d}건({100*len(s)/len(T):2.0f}%) 합 {s.sum():+.1f}R")

    # ── ② 택소노미 (mfe 기반) ──
    if "mfe" in T:
        loss = T[T.ret < 0]
        _p("\n② 손실 택소노미")
        for lo, hi, lbl in [(0, .01, "진입직후SL MFE<1%"), (.01, .03, "수익내다손절 1~3%"), (.03, 9, "큰수익후반납 ≥3%")]:
            s = loss[(loss.mfe >= lo) & (loss.mfe < hi)]
            if len(s): _p(f"  {lbl:<18} {len(s):3d}건({100*len(s)/len(loss):2.0f}%) R합 {s.R.sum():+.1f}R")

    # ── ③ 수익 갉아먹는 원인 ──
    _p("\n③ 수익성 잠식 원인")
    # DD 귀속
    eq = np.cumprod(1 + ret); pk = np.maximum.accumulate(eq); dd = (eq - pk) / pk
    mi = dd.argmin(); pi = eq[:mi+1].argmax(); seg = T.iloc[pi:mi+1]
    _p(f"  · MDD {dd[mi]*100:.1f}% = 거래#{pi}~{mi}({len(seg)}건) R합 {seg.R.sum():+.1f}R | 청산 {dict(seg.exit_tag.value_counts()) if 'exit_tag' in seg else ''}")
    # 연속손절
    runs = []; c = 0
    for x in ret:
        if x < 0: c += 1
        else:
            if c: runs.append(c)
            c = 0
    if c: runs.append(c)
    runs = np.array(runs) if runs else np.array([0])
    _p(f"  · 연속손절: 최장 {runs.max()} | 평균 {runs.mean():.1f} | 5연패+ {int((runs>=5).sum())}회")
    # Edge decay (롤링)
    W = 50
    if len(T) >= W * 2:
        rollpf = []; rollR = []
        for i in range(W, len(T) + 1):
            w = ret[i-W:i]; g = w[w > 0].sum(); b = -w[w < 0].sum()
            rollpf.append(g / b if b > 1e-9 else np.nan); rollR.append((w / SL_RISK).mean())
        rollpf = np.array(rollpf); first, last = np.nanmean(rollpf[:20]), np.nanmean(rollpf[-20:])
        _p(f"  · Edge decay(롤링50): PF 초기 {first:.2f} → 최근 {last:.2f} "
           f"({'열화' if last < first*0.8 else '안정'}) | expectancy_R 초기 {np.mean(rollR[:20]):+.2f} → 최근 {np.mean(rollR[-20:]):+.2f}")

    # ── ④ Monte Carlo (risk of ruin) ──
    mdds, streaks = mc_sim(ret)
    _p("\n④ Monte Carlo (거래 부트스트랩 2000회 — 순서 운에 따른 최악 시나리오)")
    _p(f"  · MDD 분포: p50 {np.percentile(mdds,50):.1f}% | p95(나쁨) {np.percentile(mdds,5):.1f}% | 최악 {mdds.min():.1f}%")
    _p(f"  · 최장 연속손절: p50 {np.percentile(streaks,50):.0f} | p95 {np.percentile(streaks,95):.0f} | 최악 {int(streaks.max())}")
    ror = 100 * np.mean(mdds <= -20)
    _p(f"  · ★MDD -20% 위반 확률 {ror:.0f}% (순서 운에 따라 -20% 뚫을 확률) | -30%위반 {100*np.mean(mdds<=-30):.0f}%")

    # ── MFE capture ──
    if "mfe_capture" in T:
        win = T[T.ret > 0]
        _p(f"\n⑤ 청산효율: 이익거래 MFE capture 중앙 {win.mfe_capture.median()*100:.0f}% (본 이익 중 챙긴 %)")
    _p("\n[복기 결론틀] SQN=시스템품질 / R택소노미=어디서 잃나 / MDD귀속·연속손절·edge decay=잠식원인 / MC=순서운 리스크.")
    _p("[B.더 연구] 라이브 edge decay·거래 클러스터링·틱슬립·SHAP 인과·레짐별 R분포 = 후속 모듈.")


if __name__ == "__main__":
    main()
