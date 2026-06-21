# -*- coding: utf-8 -*-
# [oi_shock_sniff.py] ChatGPT 'OI Shock Reversal' 봇 1차 sniff-test (타당성·효율성 판단용).
#   가설(롱): z_OI<-2.5(OI급감=청산) & ret<-2ATR(대형음봉) & z_Vol>2(볼륨급증) → 반등(롱).
#   엣지 존재(forward수익+) + 표본수 + 챔피언과 PnL겹침 위험 점검. 데이터=Merged(oi_sum·volume·OHLC).
import os, sys
import numpy as np, pandas as pd
STG17 = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork"
BOTS = os.path.join(STG17, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import trendstack_signal_engine as E
DATA = r"D:\ML\Verify\Merged_Data.csv"


def atr(h, l, c, n=14):
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    return pd.Series(tr).ewm(alpha=1/n, adjust=False).mean().values


def main():
    df = pd.read_csv(DATA, usecols=lambda c: c in ('timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi_sum'))
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None)
    df = df.dropna(subset=['open', 'high', 'low', 'close']).set_index('timestamp').sort_index()
    for TF, lab in [('60min', '1H'), ('240min', '4H')]:
        d = df.resample(TF, label='right', closed='right').agg(
            {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum', 'oi_sum': 'last'}).dropna()
        d['z_oi'] = (d['oi_sum'] - d['oi_sum'].rolling(50).mean()) / d['oi_sum'].rolling(50).std()
        d['z_vol'] = (d['volume'] - d['volume'].rolling(50).mean()) / d['volume'].rolling(50).std()
        a = atr(d['high'].values, d['low'].values, d['close'].values, 14)
        d['ret_atr'] = (d['close'] - d['close'].shift(20)) / a
        d['doi'] = d['oi_sum'].pct_change()
        # forward 12봉 수익
        for fb in (6, 12, 24):
            d[f'fwd{fb}'] = d['close'].shift(-fb) / d['close'] - 1
        print(f"\n========== {lab} ({len(d)}봉) ==========")
        # 롱셋업: OI급감 + 대형음봉 + 볼륨급증
        for zoi, rr, zv in [(-2.5, -2, 2), (-2.0, -1.5, 1.5), (-1.5, -1, 1.0)]:
            L = d[(d.z_oi < zoi) & (d.ret_atr < rr) & (d.z_vol > zv)]
            S = d[(d.z_oi < zoi) & (d.ret_atr > -rr) & (d.z_vol > zv)]  # 숏: 대형양봉
            def fr(sub, sign):
                if not len(sub): return "n=0"
                f12 = sub['fwd12'].values * sign * 100
                return f"n={len(sub)} fwd12 평균{np.nanmean(f12):+.2f}% 승률{(f12>0).mean()*100:.0f}%"
            print(f"  임계(zOI<{zoi},ret<{rr}ATR,zVol>{zv}): 롱 [{fr(L,1)}] | 숏 [{fr(S,-1)}]")
        # OI급감 단독(반등) 베이스라인
        base = d[d.z_oi < -2.0]
        print(f"  [참고] z_OI<-2.0 단독 n={len(base)} fwd12 평균{base['fwd12'].mean()*100:+.2f}%(롱방향)")
    print("\n[해설] fwd12 평균이 +이고 표본 충분하면 엣지 단서. 단 ★'볼륨이 가격못밀음=흡수'는 우리 CVD레버와")
    print("       같은 원리→챔피언과 PnL겹침(상관) 위험. 채택 전 ρ(챔피언,OI봇) 측정 필수.")


if __name__ == "__main__":
    main()
