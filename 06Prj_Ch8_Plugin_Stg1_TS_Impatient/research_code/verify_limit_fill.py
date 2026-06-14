# -*- coding: utf-8 -*-
# [verify_limit_fill.py] 7h/8h 진입에 '지정가 체결 가능한가' 데이터 검증.
#   각 진입 신호가(봉 종가)에 지정가 가정 → 다음 1봉(TS 7h/SW 8h) 1분봉 고저가 그 가격 터치하면 체결.
#   ① 체결률 ② 체결까지 분 분포 ③ 미체결(가격 도망) 건이 수익거래였나(놓친 손해=역선택) 점검.
#   ★한계: '터치=체결가능'은 보이나, 큐위치(메이커 실체결 여부)는 1분봉으론 불가 → 테스트넷 필요.
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); BOTS = os.path.join(HERE, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import trendstack_signal_engine as E
from bot_trendstack_impatient import TrendStackImpatientBot

DATA = r"D:\ML\Verify\Merged_Data.csv"


def load():
    df = pd.read_csv(DATA, usecols=lambda c: c in
                     ('timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi_zscore_24h'))
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None)
    return df.set_index('timestamp')


def check(entries, m1, win_min, label):
    """passive offset(bp)별 체결률: 신호가보다 유리하게 걸어도 다음봉 안에 채워지나(=메이커+가격개선)."""
    win = pd.Timedelta(minutes=win_min)
    n = len(entries)
    print(f"\n[{label}] 진입 {n}건 | 다음 {win_min}분({win_min//60}h)창 passive 지정가 체결검증")
    print(f"  {'offset':>8} {'체결률':>7} {'미체결':>6} {'미체결평균R':>11} {'미체결중 수익/손실':>16}")
    for bp in [0, 5, 10, 20]:
        filled = 0; miss = []
        for st, px, side, pnl in entries:
            seg = m1.loc[st: st + win - pd.Timedelta(minutes=1)]
            if not len(seg):
                continue
            lim = px * (1 - bp / 1e4) if side == 1 else px * (1 + bp / 1e4)   # 유리한 쪽
            hit = (seg['low'].values <= lim) if side == 1 else (seg['high'].values >= lim)
            if hit.any():
                filled += 1
            else:
                miss.append(pnl)
        miss = np.array(miss)
        mr = f"{miss.mean()*100:+.2f}%" if len(miss) else "-"
        wl = f"{int((miss>0).sum())}/{int((miss<=0).sum())}" if len(miss) else "0/0"
        print(f"  {bp:>6}bp {filled/n*100:>6.1f}% {n-filled:>6} {mr:>11} {wl:>16}")


def main():
    df = load(); m1 = df[['high', 'low']]; ohlc = df[['open', 'high', 'low', 'close']]
    # TS 진입
    df7 = E.resample_tf(ohlc, E.TF_MIN)
    oi7 = df['oi_zscore_24h'].resample(f"{E.TF_MIN}min", label='left', closed='left').last().reindex(df7.index).values
    bot = TrendStackImpatientBot(); bot.on_init({})
    tr = bot.replay_7h(df7, oi7, gate_mode='er', gate_er=0.45)
    TF7 = pd.Timedelta(minutes=E.TF_MIN)
    ts_entries = [(t['entry_t'] + TF7, t['entry'], int(t['side']), float(t['R'])) for t in tr]  # 봉마감=entry_t+7h
    check(ts_entries, m1, E.TF_MIN, "TS 7h (성급)")
    # SW 진입 (8h 종가를 신호가로)
    df8 = ohlc.resample("480min", label='left', closed='left').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
    c8 = df8['close']
    sw = pd.read_csv(os.path.join(HERE, "sw_patient.csv"))
    sw['entry_t'] = pd.to_datetime(sw['entry_t'])
    sw_entries = []
    for _, r in sw.iterrows():
        bar_close_t = r['entry_t'] + pd.Timedelta(minutes=480)
        px = c8.asof(r['entry_t'])   # 그 8h봉 종가(신호가)
        if pd.notna(px):
            sw_entries.append((bar_close_t, float(px), int(r['side']), float(r['R'])))
    check(sw_entries, m1, 480, "SW 8h (참을성)")
    print("\n[해석] 체결률 높음 + 즉시체결 비중 = 7h/8h 긴 창이라 신호가 지정가가 거의 다 채워짐.")
    print("       → 백테 'close 체결' 가정이 지정가로 현실적. 단 메이커/테이커 구분은 테스트넷서 확인.")


if __name__ == "__main__":
    main()
