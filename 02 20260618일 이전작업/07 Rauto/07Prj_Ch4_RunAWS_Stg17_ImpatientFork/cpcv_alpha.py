# -*- coding: utf-8 -*-
# [cpcv_alpha.py] §5-7 표준6 CPCV(15경로 p25)로 성급TS 알파 과최적합 검증 + 듀얼 재최적 config.
#   거래별 수익 r_i = (가격이동 - 비용) × 노출. 6그룹 2-leave-out 15경로 복리 → p25/최악/평균.
#   비용 C: TS adj=R+0.0004-C, SW adj=R+0.0014-C. C=4bp(메이커양측 낙관)·8bp(SL테이커 현실) 둘다.
#   ★p25>0 & 최악경로>0이면 견고(전표본 짜맞춤 아님). 듀얼 allocation 견고성은 OOS서 이미 확인.
import os, sys
from itertools import combinations
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); BOTS = os.path.join(HERE, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import trendstack_signal_engine as E
import trendstack_poc as P
import trendstack_regime as RG
import SidewayDCA_Stg7_engine as SWENG
from bot_trendstack_signal import TrendStackSignalBot
from bot_trendstack_impatient import TrendStackImpatientBot

DATA = r"D:\ML\Verify\Merged_Data.csv"
TS_BASE = 7.0864; TS_LEV = 22.0; SH = 0.0; POC_LB = 60; POC_BINS = 50; K = 0.85
SW_SIZE = 26.67; SW_LEV = 15.0; SW_SHORT = SWENG.SHORT_SIZE


def load():
    df = pd.read_csv(DATA, usecols=lambda c: c in
                     ('timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi_zscore_24h'))
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None)
    return df.set_index('timestamp')


def build_ts(bot, df7, oi7, poc7, atr7, fs):
    bot.on_init({}); tr = bot.replay_7h(df7, oi7, gate_mode='er', gate_er=0.45)
    t7 = df7.index.values; out = []
    for t in tr:
        et, side = t['entry_t'], int(t['side'])
        bi = int(np.searchsorted(t7, np.datetime64(et)))
        dev, rdir = P.dev_rdir(t['entry'], poc7[bi], atr7[bi]) if (bi < len(poc7) and atr7[bi] > 0 and not np.isnan(poc7[bi])) else (np.nan, 0)
        mlt = bot.opvnn_mult(dev, rdir, side)
        feat = str(fs.asof(et)) if len(fs) else "range"
        cut = SH if (feat == "uptrend" and side == -1) else 1.0
        exp = TS_BASE * mlt * cut * K / 100.0 * TS_LEV
        out.append((float(t['R']), exp, float(t['fund'])))    # R has 4bp
    return out


def cpcv(r, ng=6):
    r = np.asarray(r, float); g = np.array_split(np.arange(len(r)), ng); rr = []
    for lv in combinations(range(ng), 2):
        idx = np.concatenate([x for j, x in enumerate(g) if j not in lv])
        rr.append(np.prod(1.0 + r[idx]) - 1.0)
    rr = np.array(rr)
    return np.percentile(rr, 25), rr.min(), rr.mean()


def main():
    df = load(); ohlc = df[['open', 'high', 'low', 'close']]
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
    pat = build_ts(TrendStackSignalBot(), df7, oi7, poc7, atr7, fs)
    imp = build_ts(TrendStackImpatientBot(), df7, oi7, poc7, atr7, fs)
    print(f"[거래] 참을성 TS {len(pat)} / 성급 TS {len(imp)} | CPCV 표준6(15경로) p25, k{K}")
    print(f"\n{'비용':>6} {'모델':>8} | {'전표본수익':>10} {'CPCV p25':>10} {'최악경로':>10} {'평균경로':>10} | 판정")
    for C in [0.0004, 0.0008]:
        for nm, recs in [("참을성", pat), ("성급", imp)]:
            r = np.array([(R + 0.0004 - C) * exp for R, exp, fund in recs])
            full = np.prod(1.0 + r) - 1.0
            p25, mn, mean = cpcv(r)
            ok = "PASS(견고)" if (p25 > 0 and mn > 0) else ("p25>0但최악<0" if p25 > 0 else "FAIL")
            print(f"{C*1e4:>4.0f}bp {nm:>8} | {full*100:>9.0f}% {p25*100:>9.0f}% {mn*100:>9.0f}% {mean*100:>9.0f}% | {ok}")
    print("\n[기준] §5-7: 표준6 p25>0=본선통과. 최악경로(15중 최저)도 >0이면 더 견고.")
    print("[주의] 이건 TS 알파의 CPCV. 듀얼 k/댐핑 견고성은 OOS(23-24→25-26)서 이미 통과.")


if __name__ == "__main__":
    main()
