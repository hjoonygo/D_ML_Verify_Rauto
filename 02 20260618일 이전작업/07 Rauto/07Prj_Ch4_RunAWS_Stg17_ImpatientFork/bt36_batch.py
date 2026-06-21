# -*- coding: utf-8 -*-
# [bt36_batch.py] canonical batch(정설 그리드) 36개월 — 인내/성급 replay_7h(검증경로). king은 핀 on_bar 별도.
#   measure_slippage(716거래)와 같은 batch 경로. 비용=봇 R(E.COST)+5bp 스톱슬립, k1.0 lev22 paper.
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); BOTS = os.path.join(HERE, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import trendstack_signal_engine as E
import rauto_paper_engine as PE
from bot_trendstack_signal import TrendStackSignalBot
from bot_trendstack_impatient import TrendStackImpatientBot
from rauto_contract import Signal, Action, Side
DATA = r"D:\ML\Verify\Merged_Data.csv"
STOP_SLIP = 0.0005


def load7():
    df = pd.read_csv(DATA, usecols=lambda c: c in ('timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi_zscore_24h'))
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None)
    df = df.set_index('timestamp').sort_index()
    df7 = E.resample_tf(df[['open', 'high', 'low', 'close']], E.TF_MIN)
    oi7 = df['oi_zscore_24h'].resample(f"{E.TF_MIN}min", label='left', closed='left').last().reindex(df7.index).values
    return df7, oi7


def run(make, df7, oi7, k=1.0):
    bot = make(); bot.on_init({})
    trades = bot.replay_7h(df7[['open', 'high', 'low', 'close']], oi7, gate_mode='er', gate_er=0.45)
    acct = PE.PaperAccount(); led = []
    for t in trades:
        size = None
        # replay_7h가 사이즈 정보를 R에 안 담으면 봇 기본 사이징 필요 → 여기선 t에 size_pct 있으면 사용
        sp = t.get('size_pct')
        if sp is None:
            sp = E.BASE_SIZE if hasattr(E, 'BASE_SIZE') else 7.0864
        R = t['R'] - (STOP_SLIP if t['reason'] in ('sl', 'sl_intrabar') else 0.0)
        acct.open(Signal(Action.ENTER, side=Side(int(t['side'])), size_pct=sp * k, leverage=22.0), ts=None, price=100.0)
        p = acct.resolve_replay(R=R, mae=min(0.0, R), fund=t.get('fund', 0.0))
        led.append(dict(side=int(t['side']), R=float(R), p=float(p or 0), bal=acct.bal,
                        reason=t['reason'], year=pd.Timestamp(t['entry_t']).year))
    ret, mdd, _ = acct.metrics()
    return pd.DataFrame(led), acct.bal, ret, mdd, trades


if __name__ == "__main__":
    df7, oi7 = load7()
    print(f"7H봉 {len(df7)} {df7.index[0]}~{df7.index[-1]}")
    # 사이즈 정보 확인: replay_7h trade dict 키
    bb = TrendStackImpatientBot(); bb.on_init({})
    tr = bb.replay_7h(df7[['open', 'high', 'low', 'close']], oi7, gate_mode='er', gate_er=0.45)
    print("replay_7h trade keys:", list(tr[0].keys()))
    print("거래수(성급 batch):", len(tr))
