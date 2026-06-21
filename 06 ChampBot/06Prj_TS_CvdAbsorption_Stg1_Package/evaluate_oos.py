# -*- coding: utf-8 -*-
# [evaluate_oos.py] B: C결합(CVD사이징+OI손절롱)·king OOS분할(학습23-24/검증25-26) + CVD GAIN 파라미터 민감도.
#   OOS: 거래를 진입일로 분할. CVD백분위/z는 트레일링 아닌 전구간 z지만, GAIN민감도로 견고성 확인.
import os, sys
from itertools import combinations
import numpy as np, pandas as pd
STG17 = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork"
BOTS = os.path.join(STG17, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import rauto_paper_engine as PE
from rauto_contract import Signal, Action, Side
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = r"D:\ML\Verify\Merged_Data.csv"
LEV = 22.0; W_LO = 0.55; W_HI = 1.45; SLIP = 0.0005


def load_cvd():
    df = pd.read_csv(DATA, usecols=lambda c: c in ('timestamp', 'volume', 'taker_buy_volume'))
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None)
    df = df.sort_values('timestamp').set_index('timestamp')
    df['net_taker'] = 2.0 * df['taker_buy_volume'] - df['volume']
    df['cvd_7h'] = df['net_taker'].rolling(420, min_periods=200).sum()
    return df[['cvd_7h']]


def join_cvd(led, cvd):
    led = led.copy(); led['entry_t'] = pd.to_datetime(led['entry_t'])
    led = led.drop(columns=[c for c in ('cvd_7h', 'dt') if c in led.columns])
    led['dt'] = led['entry_t'] + pd.Timedelta(minutes=420)
    led = pd.merge_asof(led.sort_values('dt'), cvd.sort_index(), left_on='dt', right_index=True, direction='backward')
    return led.sort_values('entry_t').reset_index(drop=True)


def cvd_w(led, gain, ref=None):
    ab = (-led['side'].values * led['cvd_7h'].values).astype(float)
    m = np.nanmean(ab) if ref is None else ref[0]; sd = np.nanstd(ab) if ref is None else ref[1]
    z = np.nan_to_num((ab - m) / (sd + 1e-9))
    w = np.clip(1.0 + gain * z, W_LO, W_HI); return w / w.mean(), (m, sd)


def metrics(led, w):
    a = PE.PaperAccount(10000.0); ps = []
    for i, (_, r) in enumerate(led.iterrows()):
        R = float(r['R']) - (SLIP if r['reason'] in ('sl', 'sl_intrabar') else 0.0)
        a.open(Signal(Action.ENTER, side=Side(int(r['side'])), size_pct=float(r['size_pct']) * w[i], leverage=LEV), ts=None, price=100.0)
        ps.append(float(a.resolve_replay(R=R, mae=float(r['mae']), fund=float(r['fund'])) or 0.0))
    ps = np.array(ps); eq = 10000 * np.cumprod(1 + ps); pk = np.maximum.accumulate(eq)
    nz = ps[np.abs(ps) > 1e-12]; g = nz[nz > 0].sum(); b = -nz[nz < 0].sum()
    return dict(ret=(eq[-1] / 10000 - 1) * 100, mdd=((eq / pk - 1).min()) * 100,
                wr=(nz > 0).mean() * 100, pf=g / b if b > 0 else np.nan, n=len(nz))


def cpcv_p25(led, w, C=0.0008, ng=6):
    r = (led['R'].values - np.where(np.isin(led['reason'].values, ['sl', 'sl_intrabar']), SLIP, 0.0) + 0.0004 - C) * (led['size_pct'].values * w / 100 * LEV)
    grp = np.array_split(np.arange(len(r)), ng); rr = []
    for lv in combinations(range(ng), 2):
        idx = np.concatenate([x for j, x in enumerate(grp) if j not in lv]); rr.append(np.prod(1 + r[idx]) - 1)
    return np.percentile(rr, 25) * 100, np.min(rr) * 100


def main():
    cvd = load_cvd()
    base = join_cvd(pd.read_csv(os.path.join(HERE, "king_trades_pullback_feat.csv")), cvd)   # king
    C = join_cvd(pd.read_csv(os.path.join(HERE, "led_sq_long.csv")), cvd)                     # OI손절 롱

    print("=== B-1) OOS 분할 (학습 2023-24 / 검증 2025-26) — C결합(CVD+OI손절롱) ===")
    print("  ★학습구간 z(mean,std)로 검증구간 가중 = 미래정보 차단(진짜 OOS)")
    tr = C[C.entry_t < '2025-01-01'].reset_index(drop=True)
    te = C[C.entry_t >= '2025-01-01'].reset_index(drop=True)
    wtr, ref = cvd_w(tr, 0.40)                  # 학습구간 z 기준 적합
    wte, _ = cvd_w(te, 0.40, ref=ref)           # 검증구간엔 학습 z 적용
    # off(가중1) 비교
    for nm, sub, w in [('학습 king', tr, np.ones(len(tr))), ('학습 C결합', tr, wtr),
                       ('검증 king', te, np.ones(len(te))), ('검증 C결합', te, wte)]:
        m = metrics(sub, w)
        print(f"  {nm:>10}: {m['ret']:+8.0f}% MDD{m['mdd']:6.1f}% 승률{m['wr']:3.0f}% PF{m['pf']:.2f} n{m['n']}")

    print("\n=== B-2) CVD GAIN 파라미터 민감도 (전표본 C결합, CPCV p25 8bp) ===")
    print(f"  {'GAIN':>5} | {'ret%':>9} {'MDD%':>7} {'p25%':>8} {'worst%':>8}")
    for gain in (0.20, 0.30, 0.40, 0.50, 0.60):
        w, _ = cvd_w(C, gain); m = metrics(C, w); p25, wo = cpcv_p25(C, w)
        print(f"  {gain:>5.2f} | {m['ret']:>+8.0f}% {m['mdd']:>6.1f}% {p25:>+7.0f}% {wo:>+7.0f}%")
    w0 = np.ones(len(C)); m0 = metrics(C, w0); p0, wo0 = cpcv_p25(C, w0)
    print(f"  {'0(off)':>5} | {m0['ret']:>+8.0f}% {m0['mdd']:>6.1f}% {p0:>+7.0f}% {wo0:>+7.0f}%  (OI손절롱만, CVD無)")


if __name__ == "__main__":
    main()
