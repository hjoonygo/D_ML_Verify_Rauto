# -*- coding: utf-8 -*-
# [measure_slippage.py] 실측 슬리피지 적용 3년 A/B.
#   백테스트 가정: 7h '종가(신호가)'에 체결. 현실: 종가 보고→'다음 1분봉 시가'에 체결.
#   그 갭 = 실측 슬리피지(데이터 기반, 가정 아님). 진입 + trend_flip청산에 적용. SL청산은 SL가(스톱주문).
#   비용 = 거래소 수수료만 별도(taker 왕복 0.0010), 슬리피지는 실측 체결가에 내재.
#   ※한계: 호가스프레드·시장충격 미포함(OHLCV 한계). BTC선물 소액 ~1bp 수준 추가 추정.
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); BOTS = os.path.join(HERE, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import trendstack_signal_engine as E
import trendstack_poc as P
import trendstack_regime as RG
import rauto_paper_engine as PE
from rauto_contract import Signal, Action, Side
from bot_trendstack_signal import TrendStackSignalBot
from bot_trendstack_impatient import TrendStackImpatientBot

DATA = r"D:\ML\Verify\Merged_Data.csv"
BASE_SIZE = 7.0864; LEV = 22.0; SH = 0.0; POC_LB = 60; POC_BINS = 50
K = 0.77; FEE = 0.0010                 # taker 왕복 수수료(슬리피지는 체결가에 내재)
TF = pd.Timedelta(minutes=E.TF_MIN)


def load():
    df = pd.read_csv(DATA, usecols=lambda c: c in
                     ('timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi_zscore_24h'))
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None)
    return df.set_index('timestamp')


def pf(s):
    g = s[s > 0].sum(); b = -s[s < 0].sum(); return (g / b) if b > 0 else np.nan


def main():
    df = load(); ohlc = df[['open', 'high', 'low', 'close']]
    df7 = E.resample_tf(ohlc, E.TF_MIN)
    vol7 = df['volume'].resample(f"{E.TF_MIN}min", label='left', closed='left').sum().reindex(df7.index).fillna(0.0)
    oi7 = df['oi_zscore_24h'].resample(f"{E.TF_MIN}min", label='left', closed='left').last().reindex(df7.index).values
    h7 = df7['high'].values; l7 = df7['low'].values; c7 = df7['close'].values; mid7 = (h7 + l7) / 2.0
    atr7 = E.compute_atr(h7, l7, c7, E.ATR_PERIOD); poc7 = P.compute_poc(h7, l7, mid7, vol7.values, POC_LB, POC_BINS)
    df4 = E.resample_tf(ohlc, 240)
    try:
        _, featser = RG.feat_struct_of(df4, 8); featser.index = df4.index
    except Exception:
        featser = pd.Series("range", index=df4.index)
    t7 = df7.index.values
    o1 = df['open']; m1 = df[['high', 'low']]
    o1idx = o1.index

    def fill_at(tf_time):
        # tf_time 시점(이후 첫 1분봉) 시가 = 현실 체결가
        pos = o1idx.get_indexer([tf_time], method='bfill')[0]
        return float(o1.iloc[pos]) if pos >= 0 else np.nan

    def run(bot, name):
        trades = bot.replay_7h(df7, oi7, gate_mode='er', gate_er=0.45)
        acct_sig = PE.PaperAccount(10000.0)   # 신호가 체결(기존 가정)
        acct_slp = PE.PaperAccount(10000.0)   # 실측 슬리피지 체결
        eslips = []; rows = []
        for t in trades:
            et, xt, side = t['entry_t'], t['exit_t'], int(t['side'])
            bi = int(np.searchsorted(t7, np.datetime64(et)))
            dev, rdir = P.dev_rdir(t['entry'], poc7[bi], atr7[bi]) if (bi < len(poc7) and atr7[bi] > 0 and not np.isnan(poc7[bi])) else (np.nan, 0)
            mlt = bot.opvnn_mult(dev, rdir, side)
            feat = str(featser.asof(et)) if len(featser) else "range"
            cut = SH if (feat == "uptrend" and side == -1) else 1.0
            size = BASE_SIZE * mlt * cut * K
            seg = m1.loc[et:xt]
            ext = (seg['low'].values if side == 1 else seg['high'].values) if len(seg) else np.array([t['entry']])
            mae = float(np.min(side * (ext - t['entry']) / t['entry']))
            # 현실 체결가: 진입=진입봉마감(et+7h) 다음 1분시가 / 청산: trend_flip만 다음시가, sl은 sl가
            ef = fill_at(et + TF)
            ef = ef if not np.isnan(ef) else t['entry']
            if t['reason'] == 'trend_flip':
                xf = fill_at(xt + TF); xf = xf if not np.isnan(xf) else t['exit']
            else:
                xf = t['exit']    # SL = 스톱가
            # 실측 진입 슬리피지(불리방향 +bp)
            eslip_bp = side * (ef - t['entry']) / t['entry'] * 10000
            eslips.append(eslip_bp)
            # 신호가 R (FEE만; 기존 t['R']는 0.0004 포함 → 제거 후 FEE)
            R_sig = side * (t['exit'] - t['entry']) / t['entry'] - FEE - t['fund']
            # 실측가 R
            R_slp = side * (xf - ef) / ef - FEE - t['fund']
            for acct, Rv in [(acct_sig, R_sig), (acct_slp, R_slp)]:
                sig = Signal(Action.ENTER, side=Side(side), size_pct=size, leverage=LEV)
                acct.open(sig, ts=None, price=ef); acct.resolve_replay(R=Rv, mae=mae, fund=t['fund'])
            rows.append(dict(entry_t=et, side=side, reason=t['reason'], year=t['year'], feat=feat,
                             R_sig=round(R_sig, 6), R_slp=round(R_slp, 6), eslip_bp=round(eslip_bp, 2)))
        led = pd.DataFrame(rows); led.to_csv(os.path.join(HERE, f"slip_ledger_{name}.csv"), index=False, encoding='utf-8-sig')
        es = np.array(eslips)
        rs, ms, _ = acct_sig.metrics(); rp, mp, _ = acct_slp.metrics()
        print(f"\n[{name}] 거래 {len(led)}")
        print(f"  실측 진입슬리피지(bp): 평균 {es.mean():+.2f} 중앙 {np.median(es):+.2f} (불리>0) | 표준 {es.std():.1f}")
        print(f"  신호가체결 : ${acct_sig.bal:,.0f} ({rs:+.1f}%) MDD{ms:.2f}% PF{pf(led['R_sig']):.2f}")
        print(f"  실측슬립체결: ${acct_slp.bal:,.0f} ({rp:+.1f}%) MDD{mp:.2f}% PF{pf(led['R_slp']):.2f}")
        print(f"  → 슬리피지 영향: 수익 {rp-rs:+.1f}%p")
        return led, acct_sig, acct_slp, es

    bb = TrendStackSignalBot(); bb.on_init({})
    ib = TrendStackImpatientBot(); ib.on_init({})
    print("="*70 + "\n실측 슬리피지(신호종가→다음1분시가 갭) 적용 3년 A/B | k0.77·FEE10bp\n" + "="*70)
    lb, asb, apb, esb = run(bb, "base")
    li, asi, api, esi = run(ib, "imp")

    print("\n" + "="*70)
    print("[판정] 실측 슬리피지 적용 후")
    print(f"  기존  : {asb.metrics()[0]:+.1f}% → (슬립) {apb.metrics()[0]:+.1f}%")
    print(f"  분기  : {asi.metrics()[0]:+.1f}% → (슬립) {api.metrics()[0]:+.1f}%")
    print(f"  분기 진입슬립이 기존보다 {esi.mean()-esb.mean():+.2f}bp 더 {'불리' if esi.mean()>esb.mean() else '유리'}")
    print(f"  실측슬립 적용 후에도 분기 우위? {'YES' if api.metrics()[0]>apb.metrics()[0] else 'NO'} "
          f"(분기 {api.metrics()[0]:+.0f}% vs 기존 {apb.metrics()[0]:+.0f}%)")
    print("="*70)


if __name__ == "__main__":
    main()
