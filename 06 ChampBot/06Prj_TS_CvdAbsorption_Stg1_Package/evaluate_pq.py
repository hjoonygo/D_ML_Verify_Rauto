# -*- coding: utf-8 -*-
# [evaluate_pq.py] OI-눌림품질 사이징(PQ) 본검증: 전표본(PaperAccount) + CPCV 표준6.
#   ★등가원리: PQ게이트는 진입/청산 불변, size_pct만 가중 → 검증 led36_king의 size_pct를
#     pq_weight로 스케일 = 게이트 재실행과 수학적 동일(§15 검증엔진 ledger 무수정).
#   베이스(weight=1)는 king +11397%/MDD-17.3% 재현해야 정상(동치 관문2).
#   데이터(pullback_quality_poc): OI하락 눌림이 롱에서 강함(PF2.38 vs 1.42), 숏은 비단조.
#   → 변종: PQ_both(양측) / PQ_long(롱만, 숏=1.0) 비교.
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

# PQ 파라미터(데이터 기반 초기값)
PQ_FULL = 1.15; PQ_CUT = 0.70; OI_LO = -0.5; OI_HI = 0.5


def pq_weight(oi, side, mode):
    if mode == 'off': return 1.0
    if mode == 'long' and side != 1: return 1.0      # 롱 전용
    if np.isnan(oi): return 1.0
    if oi <= OI_LO: return PQ_FULL
    if oi >= OI_HI: return PQ_CUT
    t = (oi - OI_LO) / (OI_HI - OI_LO)
    return PQ_FULL + t * (PQ_CUT - PQ_FULL)


def full_sample(led, mode):
    a = PE.PaperAccount(10000.0); ps = []
    for _, r in led.iterrows():
        side = int(r['side']); w = pq_weight(r['oi_change_1h_pct'], side, mode)
        size = float(r['size_pct']) * w
        R = float(r['R']) - (SLIP if r['reason'] in ('sl', 'sl_intrabar') else 0.0)
        a.open(Signal(Action.ENTER, side=Side(side), size_pct=size, leverage=LEV), ts=None, price=100.0)
        p = a.resolve_replay(R=R, mae=float(r['mae']), fund=float(r['fund']))
        ps.append(float(p or 0.0))
    ps = np.array(ps); eq = 10000.0 * np.cumprod(1 + ps)
    pk = np.maximum.accumulate(eq); mdd = ((eq / pk - 1).min()) * 100
    nz = ps[np.abs(ps) > 1e-12]; g = nz[nz > 0].sum(); b = -nz[nz < 0].sum()
    pf = g / b if b > 0 else float('nan')
    return dict(ret=(eq[-1] / 10000 - 1) * 100, mdd=mdd, pf=pf,
                wr=(nz > 0).mean() * 100, exp=nz.mean() * 100, final=eq[-1], n=len(nz))


def cpcv(r, ng=6):
    r = np.asarray(r, float); g = np.array_split(np.arange(len(r)), ng); rr = []
    for lv in combinations(range(ng), 2):
        idx = np.concatenate([x for j, x in enumerate(g) if j not in lv])
        rr.append(np.prod(1.0 + r[idx]) - 1.0)
    rr = np.array(rr)
    return np.percentile(rr, 25), rr.min(), rr.mean()


def cpcv_returns(led, mode, C):
    """per-trade r_i = (R + 0.0004 - C) × exposure. exposure = size_pct*w/100*LEV."""
    out = []
    for _, r in led.iterrows():
        side = int(r['side']); w = pq_weight(r['oi_change_1h_pct'], side, mode)
        exp = float(r['size_pct']) * w / 100.0 * LEV
        out.append((float(r['R']) + 0.0004 - C) * exp)
    return np.array(out)


def main():
    led = pd.read_csv(FEAT, parse_dates=['entry_t', 'exit_t', 'dt'])
    led = led.sort_values('entry_t').reset_index(drop=True)
    print(f"trades {len(led)} | OI 결측 {int(led['oi_change_1h_pct'].isna().sum())}\n")

    print("=== 전표본 (PaperAccount, k1.0 lev22 5bp) ===")
    print(f"{'mode':>10} | {'수익':>9} {'MDD':>7} {'PF':>5} {'승률':>5} {'기대값':>7}")
    base = None
    for mode in ('off', 'both', 'long'):
        m = full_sample(led, mode)
        if mode == 'off': base = m
        print(f"{mode:>10} | {m['ret']:>+8.0f}% {m['mdd']:>6.1f}% {m['pf']:>5.2f} {m['wr']:>4.0f}% {m['exp']:>+6.2f}%")
    print(f"  (off는 king +11397%/MDD-17.3% 재현해야 정상)")

    print("\n=== CPCV 표준6(15경로) p25 / 최악 / 평균 ===")
    print(f"{'비용':>5} {'mode':>10} | {'전표본':>9} {'p25':>9} {'최악':>9} {'평균':>9} | 판정")
    for C in (0.0004, 0.0008):
        for mode in ('off', 'both', 'long'):
            r = cpcv_returns(led, mode, C)
            full = (np.prod(1 + r) - 1) * 100
            p25, mn, mean = cpcv(r)
            ok = "PASS(견고)" if (p25 > 0 and mn > 0) else ("p25>0 최악<0" if p25 > 0 else "FAIL")
            print(f"{C*1e4:>3.0f}bp {mode:>10} | {full:>+8.0f}% {p25*100:>+8.0f}% {mn*100:>+8.0f}% {mean*100:>+8.0f}% | {ok}")
    print("\n[기준 §5-7] p25>0=본선통과, 최악경로>0이면 더 견고. PQ가 off 대비 p25·최악 동반개선해야 '채택가치'.")


if __name__ == "__main__":
    main()
