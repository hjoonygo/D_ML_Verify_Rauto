# -*- coding: utf-8 -*-
# [sw_variants.py] SW 3종(참을성/성급/중간) 3년 + TS분기와 듀얼 조합(MDD 쿠션 검증).
#   SW = on_bar 1m경로(라이브와 동일). P&L: R=side*(exit-avg)/avg - SW_COST(0.0014), 사이징 26.67%×lev15×(숏0.5)×k0.77.
#   TS분기 = replay_7h + OPVnN/숏컷 사이징 ×k0.77. 듀얼 = 2슬롯($10k×2) 합산 포트폴리오 MDD.
#   인자: python sw_variants.py [limit_rows]  (스모크테스트용 행 제한)
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); BOTS = os.path.join(HERE, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import trendstack_signal_engine as E
import trendstack_poc as P
import trendstack_regime as RG
import rauto_paper_engine as PE
import SidewayDCA_Stg7_engine as SWENG
from rauto_contract import Signal, Action, Side, MarketBar
from bot_trendstack_impatient import TrendStackImpatientBot
from bot_sidewaydca_signal import SidewayDCASignalBot
from bot_sidewaydca_impatient import SidewayDCAImpatientBot, SidewayDCAMiddleBot

DATA = r"D:\ML\Verify\Merged_Data.csv"
K = 0.77; SW_COST = 0.0014
SW_SIZE = 26.67; SW_LEV = 15.0; SW_SHORT = SWENG.SHORT_SIZE
TS_BASE = 7.0864; TS_LEV = 22.0; SH = 0.0; POC_LB = 60; POC_BINS = 50
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 0


def load():
    df = pd.read_csv(DATA, usecols=lambda c: c in
                     ('timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi_zscore_24h'))
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None)
    df = df.set_index('timestamp')
    if LIMIT:
        df = df.iloc[:LIMIT]
    return df


def pf(s):
    s = np.asarray(s); g = s[s > 0].sum(); b = -s[s < 0].sum(); return (g / b) if b > 0 else np.nan


def mdd_of(eq):
    eq = np.asarray(eq, float); pk = np.maximum.accumulate(eq); return ((eq - pk) / pk).min() * 100


def run_sw(bot, name, df, m1):
    bot.on_init({})
    ts = df.index.values
    o = df['open'].values; h = df['high'].values; l = df['low'].values
    c = df['close'].values; v = df['volume'].values; oz = df['oi_zscore_24h'].values
    for i in range(len(df)):
        zz = oz[i]; aux = {'oi_zscore_24h': (float(zz) if zz == zz else np.nan), 'atr_ratio': np.nan}
        bot.on_bar(MarketBar(ts=pd.Timestamp(ts[i]), o=float(o[i]), h=float(h[i]),
                             l=float(l[i]), c=float(c[i]), v=float(v[i]), aux=aux))
    bot.flush_partial()
    acct = PE.PaperAccount(10000.0); rows = []
    for t in bot.trades:
        side = int(t['side']); avg = t['entry']; ex = t['exit']
        R = side * (ex - avg) / avg - SW_COST
        size = SW_SIZE * (SW_SHORT if side == -1 else 1.0) * K
        seg = m1.loc[t['entry_t']:t['exit_t']] if (t['entry_t'] is not None) else m1.iloc[0:0]
        if len(seg):
            ext = seg['low'].values if side == 1 else seg['high'].values
            mae = float(np.min(side * (ext - avg) / avg))
        else:
            mae = 0.0
        acct.open(Signal(Action.ENTER, side=Side(side), size_pct=size, leverage=SW_LEV), ts=None, price=avg)
        p = acct.resolve_replay(R=R, mae=mae, fund=0.0)
        rows.append(dict(exit_t=t['exit_t'], entry_t=t['entry_t'], side=side, reason=t['reason'],
                         R=round(R, 6), p=round(p or 0.0, 6), bal=round(acct.bal, 2),
                         year=pd.Timestamp(t['exit_t']).year))
    led = pd.DataFrame(rows); led.to_csv(os.path.join(HERE, f"sw_{name}.csv"), index=False, encoding='utf-8-sig')
    ret, mdd, _ = acct.metrics()
    print(f"[SW-{name}] 거래 {len(led)} | 잔고 ${acct.bal:,.0f} ({ret:+.1f}%) MDD {mdd:.1f}% PF {pf(led['p']) if len(led) else float('nan'):.2f} | 강제청산 {acct.n_liq}")
    if len(led):
        for sd, nm in [(1, "롱"), (-1, "숏")]:
            s = led[led['side'] == sd]
            if len(s): print(f"    {nm}: n{len(s)} PF{pf(s['p']):.2f} 기여{(1+s['p']).prod()-1:+.1%}")
    return led, acct


def run_ts_imp(df, m1):
    ohlc = df[['open', 'high', 'low', 'close']]
    df7 = E.resample_tf(ohlc, E.TF_MIN)
    vol7 = df['volume'].resample(f"{E.TF_MIN}min", label='left', closed='left').sum().reindex(df7.index).fillna(0.0)
    oi7 = df['oi_zscore_24h'].resample(f"{E.TF_MIN}min", label='left', closed='left').last().reindex(df7.index).values
    h7 = df7['high'].values; l7 = df7['low'].values; c7 = df7['close'].values; mid7 = (h7 + l7) / 2.0
    atr7 = E.compute_atr(h7, l7, c7, E.ATR_PERIOD); poc7 = P.compute_poc(h7, l7, mid7, vol7.values, POC_LB, POC_BINS)
    df4 = E.resample_tf(ohlc, 240)
    try:
        _, fs = RG.feat_struct_of(df4, 8); fs.index = df4.index
    except Exception:
        fs = pd.Series("range", index=df4.index)
    bot = TrendStackImpatientBot(); bot.on_init({})
    trades = bot.replay_7h(df7, oi7, gate_mode='er', gate_er=0.45)
    t7 = df7.index.values; acct = PE.PaperAccount(10000.0); rows = []
    for t in trades:
        et, xt, side = t['entry_t'], t['exit_t'], int(t['side'])
        bi = int(np.searchsorted(t7, np.datetime64(et)))
        dev, rdir = P.dev_rdir(t['entry'], poc7[bi], atr7[bi]) if (bi < len(poc7) and atr7[bi] > 0 and not np.isnan(poc7[bi])) else (np.nan, 0)
        mlt = bot.opvnn_mult(dev, rdir, side)
        feat = str(fs.asof(et)) if len(fs) else "range"
        cut = SH if (feat == "uptrend" and side == -1) else 1.0
        size = TS_BASE * mlt * cut * K
        seg = m1.loc[et:xt]
        ext = (seg['low'].values if side == 1 else seg['high'].values) if len(seg) else np.array([t['entry']])
        mae = float(np.min(side * (ext - t['entry']) / t['entry']))
        acct.open(Signal(Action.ENTER, side=Side(side), size_pct=size, leverage=TS_LEV), ts=None, price=t['entry'])
        p = acct.resolve_replay(R=t['R'], mae=mae, fund=t['fund'])
        rows.append(dict(exit_t=xt, bal=round(acct.bal, 2), p=round(p or 0.0, 6)))
    led = pd.DataFrame(rows)
    ret, mdd, _ = acct.metrics()
    print(f"\n[TS-분기 k0.77] 거래 {len(led)} | 잔고 ${acct.bal:,.0f} ({ret:+.1f}%) MDD {mdd:.1f}% PF {pf(led['p']):.2f}")
    return led, acct


def combine(ts_led, sw_led, label):
    # 2슬롯 합산 포트폴리오($10k×2). 모든 청산이벤트 시각에 각 슬롯잔고 ffill 후 합산 → 합산 MDD.
    ev = pd.DataFrame({'t': list(pd.to_datetime(ts_led['exit_t'])) + list(pd.to_datetime(sw_led['exit_t']))})
    a = ts_led.assign(t=pd.to_datetime(ts_led['exit_t']))[['t', 'bal']].rename(columns={'bal': 'ts'})
    b = sw_led.assign(t=pd.to_datetime(sw_led['exit_t']))[['t', 'bal']].rename(columns={'bal': 'sw'}) if len(sw_led) else pd.DataFrame({'t': [], 'sw': []})
    tl = pd.DataFrame({'t': sorted(set(a['t']).union(set(b['t'])))})
    tl = tl.merge(a, on='t', how='left').merge(b, on='t', how='left')
    tl['ts'] = tl['ts'].ffill().fillna(10000.0); tl['sw'] = tl['sw'].ffill().fillna(10000.0)
    tl['port'] = tl['ts'] + tl['sw']
    ret = (tl['port'].iloc[-1] / 20000.0 - 1) * 100
    mdd = mdd_of(tl['port'].values)
    print(f"  [{label}] 합산 ${tl['port'].iloc[-1]:,.0f} (수익 {ret:+.1f}% on $20k) | 합산MDD {mdd:.1f}%")
    return ret, mdd


def main():
    print("="*72 + f"\nSW 3종 + 듀얼조합 3년 {'(스모크 limit='+str(LIMIT)+')' if LIMIT else ''} | k0.77\n" + "="*72)
    df = load(); m1 = df[['high', 'low']]
    print(f"[data] 1m {len(df)}행 {df.index.min()}~{df.index.max()}")
    sw_p = run_sw(SidewayDCASignalBot(), "patient", df, m1)
    sw_i = run_sw(SidewayDCAImpatientBot(), "impatient", df, m1)
    sw_m = run_sw(SidewayDCAMiddleBot(), "middle", df, m1)
    for bot in (sw_p[1], sw_i[1], sw_m[1]):
        pass
    ts = run_ts_imp(df, m1)
    print(f"\n[듀얼 조합: TS분기 + SW각종] vs TS분기 단독 ${ts[1].bal:,.0f} / MDD {ts[1].metrics()[1]:.1f}%")
    combine(ts[0], sw_p[0], "TS분기 + SW참을성")
    combine(ts[0], sw_i[0], "TS분기 + SW성급")
    combine(ts[0], sw_m[0], "TS분기 + SW중간")
    print("="*72)


if __name__ == "__main__":
    main()
