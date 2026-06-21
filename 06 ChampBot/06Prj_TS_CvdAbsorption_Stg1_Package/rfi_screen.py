# -*- coding: utf-8 -*-
# [rfi_screen.py] 챗GPT RFI(Regime Fracture Index) 스크리닝 — 손실군집 사전감지 진입필터.
#   원리: price/OI/CVD가 '정합(aligned)'이면 추세건강, '균열(divergence)'이면 손실군집 직전 → 진입차단.
#   v1(챗GPT 원안): align = corr(price,oi,120) + corr(price,cvd,120).
#   v2(발전판): align = corr(price,cvd,120)만 — price-OI corr은 롱/숏 regime서 부호반전(숏 오탐) → 제거.
#                + cvd가 price와 같이 움직임=흐름지지(건강), 어긋남=균열. 측면 견고.
#   RFI = align의 트레일링 백분위(250). 하위 X% = 균열 = skip. 롤링=인과적 → OOS 동시평가.
#   §15: 검증 led36_king 무수정, 진입결정(entry_t+420) asof, 룩어헤드 없음. 스크리닝(재진입 근사).
import os, sys
import numpy as np, pandas as pd
STG17 = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork"
BOTS = os.path.join(STG17, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import trendstack_signal_engine as E
import rauto_paper_engine as PE
from rauto_contract import Signal, Action, Side
HERE = os.path.dirname(os.path.abspath(__file__))
FEAT = os.path.join(HERE, "king_trades_pullback_feat.csv")
DATA = r"D:\ML\Verify\Merged_Data.csv"
TF = 420; CW = 120; PW = 250; SLIP = 0.0005; LEV = 22.0


def roll_pct(s, win=PW):
    return s.rolling(win, min_periods=40).apply(lambda x: (x[:-1] < x[-1]).mean() * 100.0, raw=True)


def build():
    df = pd.read_csv(DATA, usecols=lambda c: c in ('timestamp', 'open', 'high', 'low', 'close', 'volume', 'taker_buy_volume', 'oi_sum'))
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None)
    df = df.dropna(subset=['open', 'high', 'low', 'close']).set_index('timestamp').sort_index()
    df7 = E.resample_tf(df[['open', 'high', 'low', 'close']], TF)
    agg = lambda col, how: df[col].resample(f"{TF}min", label='left', closed='left').agg(how).reindex(df7.index)
    net = (2.0 * agg('taker_buy_volume', 'sum') - agg('volume', 'sum'))  # 7h 순매수흐름(CVD delta)
    oi = agg('oi_sum', 'last')
    f = pd.DataFrame(index=df7.index)
    pd_ = df7['close'].pct_change(); od = oi.pct_change(); cd = net
    f['c_pc'] = pd_.rolling(CW).corr(cd)     # price-CVD 정합
    f['c_po'] = pd_.rolling(CW).corr(od)     # price-OI 정합(부호 regime의존)
    f['align_v1'] = f['c_pc'] + f['c_po']    # 챗GPT 원안
    f['align_v2'] = f['c_pc']                # 발전판(측면견고)
    f['rfi_v1'] = roll_pct(f['align_v1'])
    f['rfi_v2'] = roll_pct(f['align_v2'])
    return f


def stats(pv):
    pv = np.asarray(pv, float); nz = pv[np.abs(pv) > 1e-12]
    if not len(nz): return (0, 0, np.nan, 0.0)
    g = nz[nz > 0].sum(); b = -nz[nz < 0].sum()
    return (len(nz), (nz > 0).mean() * 100, g / b if b > 0 else np.nan, nz.mean() * 100)


def full(led):
    a = PE.PaperAccount(10000.0); ps = []
    for _, r in led.iterrows():
        R = float(r['R']) - (SLIP if r['reason'] in ('sl', 'sl_intrabar') else 0.0)
        a.open(Signal(Action.ENTER, side=Side(int(r['side'])), size_pct=float(r['size_pct']), leverage=LEV), ts=None, price=100.0)
        ps.append(float(a.resolve_replay(R=R, mae=float(r['mae']), fund=float(r['fund'])) or 0.0))
    ps = np.array(ps); eq = 10000 * np.cumprod(1 + ps); pk = np.maximum.accumulate(eq)
    n, wr, pf, exp = stats(ps)
    return dict(ret=(eq[-1] / 10000 - 1) * 100, mdd=((eq / pk - 1).min()) * 100, n=n, wr=wr, pf=pf)


def main():
    f = build()
    led = pd.read_csv(FEAT, parse_dates=['entry_t']).sort_values('entry_t').reset_index(drop=True)
    led['dt'] = led['entry_t'] + pd.Timedelta(minutes=TF)
    led = pd.merge_asof(led.sort_values('dt'), f.sort_index(), left_on='dt', right_index=True, direction='backward')
    led = led.sort_values('entry_t').reset_index(drop=True)
    base = full(led)
    print(f"[원본 king] {base['ret']:+.0f}%/MDD{base['mdd']:.1f}%/승률{base['wr']:.0f}%/PF{base['pf']:.2f}/n{base['n']}\n")

    for ver in ('rfi_v1', 'rfi_v2'):
        print(f"========== {ver} ({'챗GPT 원안' if ver=='rfi_v1' else '발전판 price-CVD'}) ==========")
        for thr in (10, 15, 20):
            sub = led.dropna(subset=[ver]).copy()
            skip = sub[ver] < thr
            sk = sub[skip]; kp = sub[~skip]
            ns, ws, pfs, exs = stats(sk['R'].values)
            m = full(kp)
            pct_removed = len(sk) / len(sub) * 100
            # OOS
            oos = sub[sub.entry_t >= '2025-01-01']; oos_kp = oos[oos[ver] >= thr]
            no, wo, pfo, _ = stats(oos['R'].values); nk, wk, pfk, _ = stats(oos_kp['R'].values)
            print(f"  [하위{thr}% skip] 제거 {len(sk)}건({pct_removed:.0f}%) 스킵승률{ws:.0f}%/PF{pfs:.2f}/기대{exs:+.2f}% "
                  f"| 필터후 {m['ret']:+.0f}%/MDD{m['mdd']:.1f}%/승률{m['wr']:.0f}%/PF{m['pf']:.2f}/n{m['n']}")
            print(f"          OOS25-26: 원본 승률{wo:.0f}%/PF{pfo:.2f} → 필터 승률{wk:.0f}%/PF{pfk:.2f} (스킵 {no-nk}건)")
        print()


if __name__ == "__main__":
    main()
