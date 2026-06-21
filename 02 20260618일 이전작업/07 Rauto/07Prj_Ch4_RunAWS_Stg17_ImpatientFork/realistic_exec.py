# -*- coding: utf-8 -*-
# [realistic_exec.py] 현실적 체결모델(지정가→재지정가→시장가)로 3년 A/B.
#   진입/청산: ①수동 지정가@신호가(maker, M1분) 미체결→②현재가 재지정(maker, M2분) 미체결→③시장가(taker+스프레드).
#   SL청산=스톱→시장가(taker+스프레드). 체결판정=1분봉 고저 터치(틱/호가창 없음=한계, 큐무시).
#   수수료 maker 2bp/taker 4bp 측당, 시장 스프레드 1bp/측. 비교: 종가체결(낙관) vs 현실체결.
#   ★핵심: 참을성없는 모멘텀 진입이 수동지정가 자주 미체결→시장가 추격으로 비용↑ 되는지 직접측정.
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
BASE_SIZE = 7.0864; LEV = 22.0; SH = 0.0; POC_LB = 60; POC_BINS = 50; K = 0.77
MK, TK, SPRD = 0.0002, 0.0004, 0.0001     # maker/taker 측당, 시장 스프레드 측당
M1, M2 = 3, 3                              # 지정가 대기(분)
TF = pd.Timedelta(minutes=E.TF_MIN); MIN = pd.Timedelta(minutes=1)


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
    O = df['open']; Hi = df['high']; Lo = df['low']; C = df['close']
    oidx = O.index

    def at(ts):
        pos = oidx.get_indexer([ts], method='bfill')[0]
        return pos

    def exec_fill(T, signal_px, d, is_buy):
        """지정가→재지정가→시장가. 반환(체결가, 수수료측당, 타입). is_buy=진입방향 매수여부."""
        p0 = at(T)
        if p0 < 0:
            return signal_px, TK, "mkt(noidx)"
        # ① 수동 지정가 @ signal_px (maker), M1분
        for k in range(M1):
            j = p0 + k
            if j >= len(O): break
            if (is_buy and Lo.iloc[j] <= signal_px) or ((not is_buy) and Hi.iloc[j] >= signal_px):
                return signal_px, MK, "limit1"
        # ② 현재가 재지정 (M1 시점 종가), M2분
        jc = min(p0 + M1 - 1, len(C) - 1); reprice = C.iloc[jc]
        for k in range(M2):
            j = p0 + M1 + k
            if j >= len(O): break
            if (is_buy and Lo.iloc[j] <= reprice) or ((not is_buy) and Hi.iloc[j] >= reprice):
                return reprice, MK, "limit2"
        # ③ 시장가 @ M1+M2 이후 첫 시가 + 스프레드(불리)
        jm = min(p0 + M1 + M2, len(O) - 1); mp = O.iloc[jm]
        mp = mp * (1 + SPRD) if is_buy else mp * (1 - SPRD)
        return float(mp), TK, "market"

    m1hl = df[['high', 'low']]

    def run(bot, name):
        trades = bot.replay_7h(df7, oi7, gate_mode='er', gate_er=0.45)
        acc_sig = PE.PaperAccount(10000.0)   # 종가체결(낙관, 기존)
        acc_real = PE.PaperAccount(10000.0)  # 현실체결
        rows = []; types = {"limit1": 0, "limit2": 0, "market": 0}
        for t in trades:
            et, xt, side = t['entry_t'], t['exit_t'], int(t['side'])
            bi = int(np.searchsorted(t7, np.datetime64(et)))
            dev, rdir = P.dev_rdir(t['entry'], poc7[bi], atr7[bi]) if (bi < len(poc7) and atr7[bi] > 0 and not np.isnan(poc7[bi])) else (np.nan, 0)
            mlt = bot.opvnn_mult(dev, rdir, side)
            feat = str(featser.asof(et)) if len(featser) else "range"
            cut = SH if (feat == "uptrend" and side == -1) else 1.0
            size = BASE_SIZE * mlt * cut * K
            # 현실 진입 체결(진입=side매수면 buy). 진입봉 마감 et+7h 부터.
            ef, efee, etype = exec_fill(et + TF, t['entry'], side, is_buy=(side == 1))
            types[etype] = types.get(etype, 0) + 1
            # 현실 청산 체결
            if t['reason'] == 'trend_flip':
                xf, xfee, xtype = exec_fill(xt + TF, t['exit'], side, is_buy=(side == -1))  # 청산=반대방향
            else:  # SL = 스톱→시장가
                xf = t['exit'] * (1 - side * SPRD); xfee = TK; xtype = "sl_mkt"
            # mae (현실 진입가 기준, 1m)
            seg = m1hl.loc[et:xt]
            ext = (seg['low'].values if side == 1 else seg['high'].values) if len(seg) else np.array([ef])
            mae = float(np.min(side * (ext - ef) / ef))
            # 신호가 R (maker 양측 가정 비교기준) vs 현실 R
            R_sig = side * (t['exit'] - t['entry']) / t['entry'] - 2 * MK - t['fund']
            R_real = side * (xf - ef) / ef - (efee + xfee) - t['fund']
            for acc, Rv, px in [(acc_sig, R_sig, t['entry']), (acc_real, R_real, ef)]:
                acc.open(Signal(Action.ENTER, side=Side(side), size_pct=size, leverage=LEV), ts=None, price=px)
                acc.resolve_replay(R=Rv, mae=mae, fund=t['fund'])
            rows.append(dict(entry_t=et, side=side, reason=t['reason'], feat=feat, etype=etype,
                             slip_bp=round(side * (ef - t['entry']) / t['entry'] * 10000, 2),
                             R_sig=round(R_sig, 6), R_real=round(R_real, 6)))
        led = pd.DataFrame(rows); led.to_csv(os.path.join(HERE, f"real_ledger_{name}.csv"), index=False, encoding='utf-8-sig')
        n = len(led)
        rs = acc_sig.metrics(); rr = acc_real.metrics()
        fillrate = (types['limit1'] + types['limit2']) / n
        print(f"\n[{name}] 거래 {n} | 진입체결: 지정가1 {types['limit1']}({types['limit1']/n:.0%}) 지정가2 {types['limit2']}({types['limit2']/n:.0%}) 시장가 {types['market']}({types['market']/n:.0%}) | 지정가체결률 {fillrate:.0%}")
        print(f"  평균 진입슬리피지 {led['slip_bp'].mean():+.2f}bp (시장가추격 포함)")
        print(f"  낙관(종가,maker양측): ${acc_sig.bal:,.0f} ({rs[0]:+.1f}%) MDD{rs[1]:.1f}% PF{pf(led['R_sig']):.2f}")
        print(f"  현실(지정가→시장가) : ${acc_real.bal:,.0f} ({rr[0]:+.1f}%) MDD{rr[1]:.1f}% PF{pf(led['R_real']):.2f}")
        print(f"  → 현실체결 영향: {rr[0]-rs[0]:+.1f}%p")
        return led, acc_sig, acc_real

    bb = TrendStackSignalBot(); bb.on_init({}); ib = TrendStackImpatientBot(); ib.on_init({})
    print("="*72 + "\n현실 체결모델(지정가→재지정→시장가) 3년 A/B | k0.77\n" + "="*72)
    lb, sb, rb = run(bb, "base"); li, si, ri = run(ib, "imp")
    print("\n" + "="*72)
    print("[판정] 현실 체결모델 적용 후")
    print(f"  기존 : {sb.metrics()[0]:+.0f}% → 현실 {rb.metrics()[0]:+.0f}% (PF {pf(lb['R_real']):.2f})")
    print(f"  분기 : {si.metrics()[0]:+.0f}% → 현실 {ri.metrics()[0]:+.0f}% (PF {pf(li['R_real']):.2f})")
    print(f"  현실체결 후에도 분기 우위? {'YES' if ri.metrics()[0]>rb.metrics()[0] else 'NO'}  ({ri.metrics()[0]:+.0f}% vs {rb.metrics()[0]:+.0f}%)")
    print("="*72)


if __name__ == "__main__":
    main()
