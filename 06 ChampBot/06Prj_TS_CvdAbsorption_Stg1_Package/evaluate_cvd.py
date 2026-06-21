# -*- coding: utf-8 -*-
# [evaluate_cvd.py] B레버: CVD 흡수(absorption) 사이징 검증. 전표본 + CPCV 표준6.
#   가설: 진입 직전 7h 순매수흐름(CVD)이 '거래방향과 역행'일수록(흡수) 결과 좋음.
#   통합지표 absorption = -side * cvd_7h  (롱 IC-0.17/숏+0.17을 한 부호로 통합 → 클수록 흡수=좋음).
#   ★평균중립 가중: w = clip(1 + g*z(absorption), lo, hi), z평균0 → 총노출≈불변 → '배분 스킬'만 검증.
#   등가원리(§15): 진입/청산 불변, size만 가중 → led36_king 재가중 = 게이트 재실행과 동일.
import os, sys
from itertools import combinations
import numpy as np, pandas as pd
STG17 = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork"
BOTS = os.path.join(STG17, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import rauto_paper_engine as PE
from rauto_contract import Signal, Action, Side

HERE = os.path.dirname(os.path.abspath(__file__))
FEAT = os.path.join(HERE, "king_trades_pullback_feat.csv")
SLIP = 0.0005; LEV = 22.0
GAIN = 0.40; W_LO = 0.55; W_HI = 1.45   # 가중 강도/한계


def build_weights(led, mode):
    if mode == 'off':
        return np.ones(len(led))
    ab = (-led['side'].values * led['cvd_7h'].values).astype(float)  # 흡수지표
    if mode == 'long':                       # 롱에만 적용(숏 신호 약하면 비교용)
        pass
    z = (ab - np.nanmean(ab)) / (np.nanstd(ab) + 1e-9)
    z = np.nan_to_num(z, nan=0.0)
    w = np.clip(1.0 + GAIN * z, W_LO, W_HI)
    if mode == 'long':
        w = np.where(led['side'].values == 1, w, 1.0)
    w = w / w.mean()                         # 평균중립(총노출 불변)
    return w


def full_sample(led, w):
    a = PE.PaperAccount(10000.0); ps = []
    for i, (_, r) in enumerate(led.iterrows()):
        size = float(r['size_pct']) * w[i]
        R = float(r['R']) - (SLIP if r['reason'] in ('sl', 'sl_intrabar') else 0.0)
        a.open(Signal(Action.ENTER, side=Side(int(r['side'])), size_pct=size, leverage=LEV), ts=None, price=100.0)
        ps.append(float(a.resolve_replay(R=R, mae=float(r['mae']), fund=float(r['fund'])) or 0.0))
    ps = np.array(ps); eq = 10000.0 * np.cumprod(1 + ps)
    pk = np.maximum.accumulate(eq); mdd = ((eq / pk - 1).min()) * 100
    nz = ps[np.abs(ps) > 1e-12]; g = nz[nz > 0].sum(); b = -nz[nz < 0].sum()
    return dict(ret=(eq[-1] / 10000 - 1) * 100, mdd=mdd, pf=g / b if b > 0 else float('nan'),
                wr=(nz > 0).mean() * 100, exp=nz.mean() * 100)


def cpcv(r, ng=6):
    r = np.asarray(r, float); grp = np.array_split(np.arange(len(r)), ng); rr = []
    for lv in combinations(range(ng), 2):
        idx = np.concatenate([x for j, x in enumerate(grp) if j not in lv])
        rr.append(np.prod(1.0 + r[idx]) - 1.0)
    rr = np.array(rr); return np.percentile(rr, 25), rr.min(), rr.mean()


def main():
    led = pd.read_csv(FEAT, parse_dates=['entry_t']).sort_values('entry_t').reset_index(drop=True)
    print(f"trades {len(led)} | cvd_7h 결측 {int(led['cvd_7h'].isna().sum())}")
    # IC 재확인(통합지표)
    ab = -led['side'] * led['cvd_7h']
    print(f"absorption(-side*cvd_7h) IC vs R (Spearman, 전체) = {ab.corr(led['R'], method='spearman'):+.3f}\n")

    print("=== 전표본 (PaperAccount, k1.0 lev22 5bp, 평균중립가중) ===")
    print(f"{'mode':>8} | {'수익':>9} {'MDD':>7} {'PF':>5} {'승률':>5} {'기대값':>7}")
    for mode in ('off', 'both', 'long'):
        m = full_sample(led, build_weights(led, mode))
        print(f"{mode:>8} | {m['ret']:>+8.0f}% {m['mdd']:>6.1f}% {m['pf']:>5.2f} {m['wr']:>4.0f}% {m['exp']:>+6.2f}%")

    print("\n=== CPCV 표준6(15경로) ===")
    print(f"{'비용':>5} {'mode':>8} | {'전표본':>9} {'p25':>9} {'최악':>9} {'평균':>9} | 판정")
    for C in (0.0004, 0.0008):
        for mode in ('off', 'both', 'long'):
            w = build_weights(led, mode)
            exp = led['size_pct'].values * w / 100.0 * LEV
            r = (led['R'].values + 0.0004 - C) * exp
            full = (np.prod(1 + r) - 1) * 100
            p25, mn, mean = cpcv(r)
            ok = "PASS(견고)" if (p25 > 0 and mn > 0) else ("p25>0 최악<0" if p25 > 0 else "FAIL")
            print(f"{C*1e4:>3.0f}bp {mode:>8} | {full:>+8.0f}% {p25*100:>+8.0f}% {mn*100:>+8.0f}% {mean*100:>+8.0f}% | {ok}")
    print("\n[기준] off 대비 p25·최악 동반개선해야 '채택가치'(§5.6/5.7).")


if __name__ == "__main__":
    main()
