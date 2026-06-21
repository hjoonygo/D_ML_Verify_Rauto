# -*- coding: utf-8 -*-
# [lsi_screen.py] 챗GPT LSI(Liquidity Stress Index) 스크리닝.
#   LSI = OI가속(d2 OI)·ATR팽창·테이커불균형 백분위(180). severe=2+요소가 95%↑ 동시.
#   ★Funding 컬럼이 Merged에 없음 → 4요소 중 funding_accel 제외(3요소). 데이터 한계 명시.
#   기제=노출축소(보유중)지만 스크리닝은 'severe 진입거래가 나쁜가 + skip효과' 1차판정.
#   ★전제검증: verify_liquidation서 실역행 최악 -2.33%(청산-4.1% 못닿음) → 막을 catastrophe가 없음.
#     LSI가 그래도 저질거래를 거르는지 본다.
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
TF = 420; ROLL = 180; SLIP = 0.0005; LEV = 22.0


def rpct(s, win=ROLL):
    return s.rolling(win, min_periods=40).apply(lambda x: (x[:-1] < x[-1]).mean() * 100.0, raw=True)


def build():
    df = pd.read_csv(DATA, usecols=lambda c: c in ('timestamp', 'open', 'high', 'low', 'close', 'volume', 'taker_buy_volume', 'oi_sum'))
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None)
    df = df.dropna(subset=['open', 'high', 'low', 'close']).set_index('timestamp').sort_index()
    df7 = E.resample_tf(df[['open', 'high', 'low', 'close']], TF)
    agg = lambda col, how: df[col].resample(f"{TF}min", label='left', closed='left').agg(how).reindex(df7.index)
    oi = agg('oi_sum', 'last'); vol = agg('volume', 'sum'); tb = agg('taker_buy_volume', 'sum')
    atr = pd.Series(E.compute_atr(df7['high'].values, df7['low'].values, df7['close'].values, E.ATR_PERIOD), index=df7.index)
    f = pd.DataFrame(index=df7.index)
    f['oi_accel'] = oi.pct_change().diff().abs()        # |d2(OI)| 가속
    f['atr_n'] = atr / df7['close']
    f['taker_imb'] = (tb / vol.replace(0, np.nan) - 0.5).abs()
    f['oi_pct'] = rpct(f['oi_accel']); f['atr_pct'] = rpct(f['atr_n']); f['tk_pct'] = rpct(f['taker_imb'])
    f['lsi_cnt'] = (f[['oi_pct', 'atr_pct', 'tk_pct']] > 95).sum(axis=1)   # 95%↑ 요소 수
    f['lsi_mean'] = f[['oi_pct', 'atr_pct', 'tk_pct']].mean(axis=1)
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
    n, wr, pf, ex = stats(ps)
    return dict(ret=(eq[-1] / 10000 - 1) * 100, mdd=((eq / pk - 1).min()) * 100, n=n, wr=wr, pf=pf)


def main():
    f = build()
    led = pd.read_csv(FEAT, parse_dates=['entry_t']).sort_values('entry_t').reset_index(drop=True)
    led['dt'] = led['entry_t'] + pd.Timedelta(minutes=TF)
    led = pd.merge_asof(led.sort_values('dt'), f[['lsi_cnt', 'lsi_mean']].sort_index(), left_on='dt', right_index=True, direction='backward')
    led = led.sort_values('entry_t').reset_index(drop=True)
    b = full(led)
    print(f"[원본 king] {b['ret']:+.0f}%/MDD{b['mdd']:.1f}%/승률{b['wr']:.0f}%/PF{b['pf']:.2f}/n{b['n']}\n")

    # severe(2+ at 95%) 진입거래 vs 나머지
    sev = led[led['lsi_cnt'] >= 2]; norm = led[led['lsi_cnt'] < 2]
    ns, ws, pfs, exs = stats(sev['R'].values); nn, wn, pfn, exn = stats(norm['R'].values)
    print(f"=== LSI severe(3요소중 2+가 95%↑) 진입거래 vs 나머지 ===")
    print(f"  severe진입: n={ns} 승률{ws:.0f}% PF{pfs:.2f} 기대{exs:+.2f}%  ← 나쁘면 LSI 유효")
    print(f"  정상진입  : n={nn} 승률{wn:.0f}% PF{pfn:.2f} 기대{exn:+.2f}%")
    if ns:
        fl = full(norm)
        print(f"  [severe 진입 skip] 필터후 {fl['ret']:+.0f}%/MDD{fl['mdd']:.1f}%/승률{fl['wr']:.0f}%/PF{fl['pf']:.2f}/n{fl['n']}")

    # lsi_mean 상위 10%(가장 스트레스) 진입거래
    thr = led['lsi_mean'].quantile(0.90)
    hi = led[led['lsi_mean'] >= thr]
    nh, wh, pfh, exh = stats(hi['R'].values)
    print(f"\n=== LSI_mean 상위10% 진입거래 (n={nh}) ===")
    print(f"  승률{wh:.0f}% PF{pfh:.2f} 기대{exh:+.2f}%  (원본 평균기대 {(led['R']>0).mean()*100:.0f}%승률 대비)")
    print(f"\n[전제 메모] verify_liquidation: king 실역행 최악 -2.33%(청산 -4.1% 미도달) → LSI가 막을 '계좌살해 사건' 자체가 표본에 없음.")


if __name__ == "__main__":
    main()
