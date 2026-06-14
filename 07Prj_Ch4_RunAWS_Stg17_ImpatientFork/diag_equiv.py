# -*- coding: utf-8 -*-
# [diag_equiv.py] 분기봇 라이브≡리플레이 불일치 원인 진단(읽기전용). 라이브 누적경로 vs replay_7h 비교.
import os, sys, glob
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); BOTS = os.path.join(HERE, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import trendstack_signal_engine as TE
import bot_trendstack_impatient as TBI
from rauto_contract import MarketBar
from oi_zscore_adapter import build_aux

DAUTO = r"C:\BinanceData"

def main():
    files = sorted(glob.glob(os.path.join(DAUTO, "BTCUSDT_1m_*.csv")))
    dd = pd.concat([pd.read_csv(f, usecols=['ts_utc','open','high','low','close','volume']) for f in files])
    dd['ts_utc'] = pd.to_datetime(dd['ts_utc']); dd = dd.drop_duplicates('ts_utc').sort_values('ts_utc').reset_index(drop=True)
    aux = build_aux(); aux['ts_utc'] = pd.to_datetime(aux['ts_utc'])
    dd = dd.merge(aux[['ts_utc','oi_zscore_24h']], on='ts_utc', how='left')

    # 라이브 누적경로
    bot = TBI.TrendStackImpatientBot(); bot.on_init({})
    for ts,o,h,l,c,v,oz in dd.itertuples(index=False):
        bot.on_bar(MarketBar(ts=ts,o=o,h=h,l=l,c=c,v=v,aux={'oi_zscore':(float(oz) if oz==oz else None)}))
    live = bot._trades

    # 리플레이
    df7 = pd.DataFrame(bot._h7, columns=['ts','open','high','low','close','volume']).set_index('ts')
    fresh = TBI.TrendStackImpatientBot(); fresh.on_init({})
    rep = fresh.replay_7h(df7[['open','high','low','close']], np.array(bot._oiz,float), gate_mode='er', gate_er=0.45)

    print(f"라이브 {len(live)}거래 / 리플레이 {len(rep)}거래")
    key = lambda t: (str(t['entry_t']), str(t['exit_t']), t['side'], round(float(t['R']),6))
    sl = set(map(key, live)); sr = set(map(key, rep))
    only_live = [t for t in live if key(t) not in sr]
    only_rep = [t for t in rep if key(t) not in sl]
    print(f"라이브에만 {len(only_live)} / 리플레이에만 {len(only_rep)}")
    print("\n[라이브에만 있는 거래]")
    for t in only_live[:8]:
        print(f"  in {t['entry_t']} out {t['exit_t']} side{t['side']} R{t['R']:+.5f} {t['reason']} bars{t['bars']}")
    print("[리플레이에만 있는 거래]")
    for t in only_rep[:8]:
        print(f"  in {t['entry_t']} out {t['exit_t']} side{t['side']} R{t['R']:+.5f} {t['reason']} bars{t['bars']}")
    # 첫 거래 비교
    print("\n[첫 3거래 라이브] ", [(str(t['entry_t']),t['side'],round(t['R'],4)) for t in live[:3]])
    print("[첫 3거래 리플레이]", [(str(t['entry_t']),t['side'],round(t['R'],4)) for t in rep[:3]])

if __name__ == "__main__":
    main()
