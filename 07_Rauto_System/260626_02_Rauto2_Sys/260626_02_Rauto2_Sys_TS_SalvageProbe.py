# -*- coding: utf-8 -*-
# [TS_SalvageProbe] TS(성급왕) 레짐 살리기 1차검증 (세션 260626_02_Rauto2_Sys).
#   캡틴 가설: TS 환각=청산가 부풀리기(방향은 진짜). 레짐(고변동)판별로 살릴 수 있나?
#   방법: ①정직청산=exit_px를 exit_t 1m봉 [저,고]로 클램프(그 순간 체결가능치) → honest_R
#         ②장세분류=진입시점 24h 변동성(고/중/저) + 추세(상승/하락/횡보)
#         ③원본 vs 정직, 장세별 PF·승률·평균R 대조 → '고변동서 정직해도 엣지 남나' 판정.
#   ★한계(정직): 클램프는 1차근사. 트레일 실체결 1분 정밀복원은 TS 봇 래퍼 필요(§15.3·다음).
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
from path_finder import ensure_paths; ensure_paths()
import numpy as np, pandas as pd
from fib_replay_1m import load_1m

LED = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork\led36_king.csv"
TOL = 0.6


def stats(R):
    R = np.array(R, dtype=float)
    if not len(R): return dict(n=0, win=0, pf=0, avg=0, comp=0)
    w = R[R > 0]; l = R[R < 0]
    pf = (w.sum() / abs(l.sum())) if len(l) else 9.99
    comp = (np.prod(1 + R) - 1) * 100
    return dict(n=len(R), win=round((R > 0).mean() * 100), pf=round(pf, 2), avg=round(R.mean() * 100, 3), comp=round(comp, 1))


def main():
    d = load_1m()
    m_t = d.index.values; mH = d["high"].values; mL = d["low"].values; mC = d["close"].values
    led = pd.read_csv(LED)
    et = pd.to_datetime(led["entry_t"]).values
    xt = pd.to_datetime(led["exit_t"]).values
    side = led["side"].astype(int).values
    epx = led["entry_px"].astype(float).values
    xpx = led["exit_px"].astype(float).values
    R = led["R"].astype(float).values

    honest_R = R.copy(); clamped = 0
    # 진입시점 24h 변동성·추세
    volp = np.zeros(len(led)); trend = np.empty(len(led), dtype=object)
    for i in range(len(led)):
        xk = int(np.searchsorted(m_t, np.datetime64(pd.Timestamp(xt[i])), "right")) - 1
        if 0 <= xk < len(m_t):
            lo, hi = mL[xk], mH[xk]
            he = min(max(xpx[i], lo), hi)                       # 클램프 = 그 순간 체결가능치
            if abs(he - xpx[i]) > TOL:
                clamped += 1
            honest_R[i] = R[i] + (he - xpx[i]) / epx[i] * side[i]   # 청산 보정분
        a = int(np.searchsorted(m_t, np.datetime64(pd.Timestamp(et[i])), "left"))
        a0 = max(0, a - 1440)
        if a < len(m_t):
            hh = mH[a0:a + 1].max(); ll = mL[a0:a + 1].min(); cc = mC[a]
            volp[i] = (hh - ll) / cc * 100                      # 24h 변동폭%
            ch = (cc / mC[a0] - 1) * 100 if a0 < len(m_t) else 0
            trend[i] = "up" if ch > 2 else ("down" if ch < -2 else "range")
        else:
            trend[i] = "range"

    # 변동성 terciles
    q1, q2 = np.percentile(volp, [33, 66])
    vlab = np.where(volp >= q2, "고변동", np.where(volp <= q1, "저변동", "중변동"))

    print("=" * 70)
    print("[TS 성급왕 레짐 살리기 1차검증] 668거래 · 정직청산(봉클램프) vs 원본")
    print("=" * 70)
    print(f"클램프된(환상→체결가능 보정) 거래 = {clamped}/{len(led)} ({100*clamped/len(led):.1f}%)")
    so, sh = stats(R), stats(honest_R)
    print(f"\n[전체]  원본:  거래{so['n']} 승률{so['win']}% PF{so['pf']} 평균R{so['avg']}% 복리{so['comp']}%(언사이즈드)")
    print(f"        정직:  거래{sh['n']} 승률{sh['win']}% PF{sh['pf']} 평균R{sh['avg']}% 복리{sh['comp']}%")

    print(f"\n[변동성별 — 정직청산] (캡틴 가설: 고변동서 엣지 남나)")
    print(f"  {'장세':<7}{'거래':>5}{'승률':>6}{'PF':>6}{'평균R':>8}{'복리(언사)':>11}")
    for lab in ["고변동", "중변동", "저변동"]:
        s = stats(honest_R[vlab == lab])
        print(f"  {lab:<7}{s['n']:>5}{s['win']:>5}%{s['pf']:>6}{s['avg']:>7}%{s['comp']:>+10}%")
    print(f"\n[변동성별 — 원본(환상포함) 대조]")
    for lab in ["고변동", "중변동", "저변동"]:
        s = stats(R[vlab == lab])
        print(f"  {lab:<7}{s['n']:>5}{s['win']:>5}%{s['pf']:>6}{s['avg']:>7}%{s['comp']:>+10}%")

    print(f"\n[추세별 — 정직청산]")
    for lab in ["up", "down", "range"]:
        s = stats(honest_R[trend == lab])
        nm = {"up": "상승", "down": "하락", "range": "횡보"}[lab]
        print(f"  {nm:<7}{s['n']:>5}{s['win']:>5}%{s['pf']:>6}{s['avg']:>7}%{s['comp']:>+10}%")

    print(f"\n[해석] · 정직청산해도 '고변동' PF/평균R가 양호하면 = 캡틴 가설(레짐으로 살림) 근거.")
    print(f"       · 단 이건 클램프 1차근사. 정밀=TS 1m 트레일 honest 래퍼 필요(REVoi bt_full식).")
    return True


if __name__ == "__main__":
    main()
