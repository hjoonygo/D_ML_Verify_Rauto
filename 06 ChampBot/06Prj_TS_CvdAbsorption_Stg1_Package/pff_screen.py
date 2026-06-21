# -*- coding: utf-8 -*-
# [pff_screen.py] 챗GPT PFF(Pullback Failure Filter) 스크리닝 — 진입 차단 필터의 승률 효과 1차검증.
#   조건(롱): oi_pct>80 & taker_sell_pct>80 & dist_to_swinglow_pct<20 (전부 롤링180 백분위, 매직넘버無) → skip.
#   ★스크리닝 한계: 진입 스킵은 재진입 타이밍을 바꾸므로 봇 재실행과 다름(='스킵거래가 패자인가'만 정확).
#     유망하면 봇 재실행으로 확정. 롤링백분위=인과적 → OOS(2025-26)도 동시 평가.
#   §15: 검증 led36_king 무수정. 피처는 진입결정시점(entry_t+420) asof, 룩어헤드 없음.
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
TF = 420; SWING_W = 20; ROLL = 180; SLIP = 0.0005; LEV = 22.0


def roll_pct(s, win=ROLL):
    """현재값이 직전 win개 중 몇 %보다 큰지(트레일링, 인과적)."""
    return s.rolling(win, min_periods=30).apply(lambda x: (x[:-1] < x[-1]).mean() * 100.0, raw=True)


def build_feats():
    df = pd.read_csv(DATA, usecols=lambda c: c in ('timestamp', 'open', 'high', 'low', 'close', 'volume', 'taker_buy_volume', 'oi_change_1h_pct'))
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None)
    df = df.dropna(subset=['open', 'high', 'low', 'close']).set_index('timestamp').sort_index()
    df7 = E.resample_tf(df[['open', 'high', 'low', 'close']], TF)
    agg = lambda col, how: df[col].resample(f"{TF}min", label='left', closed='left').agg(how).reindex(df7.index)
    vol7 = agg('volume', 'sum'); tb7 = agg('taker_buy_volume', 'sum')
    f = pd.DataFrame(index=df7.index)
    f['oi_delta'] = agg('oi_change_1h_pct', 'last')
    f['taker_sell_ratio'] = 1.0 - (tb7 / vol7.replace(0, np.nan))
    sw_low = df7['low'].rolling(SWING_W, min_periods=5).min()
    sw_high = df7['high'].rolling(SWING_W, min_periods=5).max()
    f['dist_low'] = (df7['close'] - sw_low) / df7['close']      # 작을수록 전저점 근접
    f['dist_high'] = (sw_high - df7['close']) / df7['close']    # 숏 거울: 작을수록 전고점 근접
    # 롤링180 백분위(트레일링)
    f['oi_pct'] = roll_pct(f['oi_delta'])
    f['taker_sell_pct'] = roll_pct(f['taker_sell_ratio'])
    f['taker_buy_pct'] = roll_pct(1.0 - f['taker_sell_ratio'])
    f['dist_low_pct'] = roll_pct(f['dist_low'])
    f['dist_high_pct'] = roll_pct(f['dist_high'])
    return f


def stats(pv):
    pv = np.asarray(pv, float); nz = pv[np.abs(pv) > 1e-12]
    if not len(nz): return (0, 0, np.nan, 0.0)
    g = nz[nz > 0].sum(); b = -nz[nz < 0].sum()
    return (len(nz), (nz > 0).mean() * 100, g / b if b > 0 else np.nan, nz.mean() * 100)


def full_sample(led):
    a = PE.PaperAccount(10000.0); ps = []
    for _, r in led.iterrows():
        R = float(r['R']) - (SLIP if r['reason'] in ('sl', 'sl_intrabar') else 0.0)
        a.open(Signal(Action.ENTER, side=Side(int(r['side'])), size_pct=float(r['size_pct']), leverage=LEV), ts=None, price=100.0)
        ps.append(float(a.resolve_replay(R=R, mae=float(r['mae']), fund=float(r['fund'])) or 0.0))
    ps = np.array(ps); eq = 10000 * np.cumprod(1 + ps); pk = np.maximum.accumulate(eq)
    n, wr, pf, exp = stats(ps)
    return dict(ret=(eq[-1] / 10000 - 1) * 100, mdd=((eq / pk - 1).min()) * 100, n=n, wr=wr, pf=pf, exp=exp)


def main():
    f = build_feats()
    led = pd.read_csv(FEAT, parse_dates=['entry_t']).sort_values('entry_t').reset_index(drop=True)
    led['dt'] = led['entry_t'] + pd.Timedelta(minutes=TF)
    led = pd.merge_asof(led.sort_values('dt'), f.sort_index(), left_on='dt', right_index=True, direction='backward')
    led = led.sort_values('entry_t').reset_index(drop=True)

    # PFF skip 조건: 롱=구조공격(OI↑+테이커매도↑+전저점근접) / 숏=거울(OI↑+테이커매수↑+전고점근접)
    long_skip = (led.side == 1) & (led.oi_pct > 80) & (led.taker_sell_pct > 80) & (led.dist_low_pct < 20)
    short_skip = (led.side == -1) & (led.oi_pct > 80) & (led.taker_buy_pct > 80) & (led.dist_high_pct < 20)
    led['skip_long'] = long_skip
    led['skip_both'] = long_skip | short_skip

    for tag, skipmask in [('롱전용 PFF', 'skip_long'), ('롱+숏거울 PFF', 'skip_both')]:
        sk = led[led[skipmask]]; kp = led[~led[skipmask]]
        ns, ws, pfs, exs = stats(sk['R'].values); nk, wk, pfk, exk = stats(kp['R'].values)
        print(f"\n=== {tag} ===")
        print(f"  스킵된 거래: n={ns} 승률={ws:.0f}% PF={pfs:.2f} 기대값={exs:+.2f}%  ← 이게 패자군이어야 PFF 유효")
        print(f"  남은 거래  : n={nk} 승률={wk:.0f}% PF={pfk:.2f} 기대값={exk:+.2f}%")
        base = full_sample(led); filt = full_sample(kp)
        print(f"  [전표본] 원본 {base['ret']:+.0f}%/MDD{base['mdd']:.1f}%/승률{base['wr']:.0f}%/PF{base['pf']:.2f}/n{base['n']}")
        print(f"          PFF  {filt['ret']:+.0f}%/MDD{filt['mdd']:.1f}%/승률{filt['wr']:.0f}%/PF{filt['pf']:.2f}/n{filt['n']}")
        # OOS: 2025-2026만
        oos = led[led['entry_t'] >= '2025-01-01']; oos_kp = oos[~oos[skipmask]]
        no, wo, pfo, exo = stats(oos['R'].values); nok, wok, pfok, exok = stats(oos_kp['R'].values)
        print(f"  [OOS 2025-26] 원본 승률{wo:.0f}%/PF{pfo:.2f}/n{no} → PFF 승률{wok:.0f}%/PF{pfok:.2f}/n{nok} (스킵 {no-nok}건)")


if __name__ == "__main__":
    main()
