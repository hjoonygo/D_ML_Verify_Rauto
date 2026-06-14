# -*- coding: utf-8 -*-
# [validate_ab.py] "격차가 진짜인가" 결정검증.
#   ① k0.77(배포 실제) 적용 ② 비용 민감도 스윕(정상청산 비용 4→14→19→30bp) — 현실비용서도 우위면 진짜.
#   ③ §9 재현 진단: stg6 원장(264) vs 내 base replay(328) 차이 규명.
#   P&L=resolve_replay(정상청산 R×노출, 강제청산 엔진식). adjusted_R=R+0.0004-c 로 비용 c 부과.
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
STG6 = r"D:\ML\Verify\stg6_levsweep_ledger.csv"
BASE_SIZE = 7.0864; LEV = 22.0; SH = 0.0; POC_LB = 60; POC_BINS = 50
K = 0.77                                  # ★배포 실제 배분
SIG_COST = 0.0004                         # 신호엔진 비용(R에 박혀있음)
COSTS = [0.0004, 0.0014, 0.0019, 0.0030]  # 정상청산 부과 비용 스윕(왕복)


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
    m1 = df[['high', 'low']]; t7 = df7.index.values

    # ── 거래 + per-trade 재료(gross_R, exposure(k), mae, fund) ──
    def prep(bot):
        trades = bot.replay_7h(df7, oi7, gate_mode='er', gate_er=0.45)
        recs = []
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
            recs.append(dict(side=side, year=t['year'], feat=feat, size_pct=size, lev=LEV,
                             grossR=float(t['R']) + SIG_COST, fund=float(t['fund']), mae=mae,
                             entry=t['entry']))
        return pd.DataFrame(recs)

    def compound(recs, cost):
        acct = PE.PaperAccount(start_balance=10000.0)
        ps = []
        for r in recs.itertuples(index=False):
            adjR = r.grossR - cost                       # 비용 c 부과(정상청산)
            sig = Signal(Action.ENTER, side=Side(int(r.side)), size_pct=r.size_pct, leverage=r.lev)
            acct.open(sig, ts=None, price=r.entry)
            p = acct.resolve_replay(R=adjR, mae=r.mae, fund=r.fund)
            ps.append(p or 0.0)
        ret, mdd, cal = acct.metrics()
        return ret, mdd, acct.n_liq, np.array(ps)

    print("[prep] 거래생성 중...")
    bb = TrendStackSignalBot(); bb.on_init({}); rb = prep(bb)
    ib = TrendStackImpatientBot(); ib.on_init({}); ri = prep(ib)
    print(f"[거래] 기존 {len(rb)} / 분기 {len(ri)} (k{K} 적용)")

    # ── ② 비용 스윕 ──
    print("\n[②+① 비용 민감도 스윕 — k0.77 적용, $10k]")
    print(f"{'cost(bp)':>9} | {'기존 ret%':>10} {'기존MDD':>8} {'기존PF':>7} | {'분기 ret%':>11} {'분기MDD':>8} {'분기PF':>7} | {'분기우위':>8}")
    rows = []
    for c in COSTS:
        retb, mddb, lqb, pb = compound(rb, c)
        reti, mddi, lqi, pi = compound(ri, c)
        edge = reti - retb
        rows.append((c, retb, mddb, pf(pd.Series(pb)), reti, mddi, pf(pd.Series(pi)), edge))
        print(f"{c*10000:>9.0f} | {retb:>10.1f} {mddb:>8.2f} {pf(pd.Series(pb)):>7.2f} | {reti:>11.1f} {mddi:>8.2f} {pf(pd.Series(pi)):>7.2f} | {('분기' if edge>0 else '기존')}+{abs(edge):>7.0f}%p")
    pd.DataFrame(rows, columns=['cost','base_ret','base_mdd','base_pf','imp_ret','imp_mdd','imp_pf','edge']).to_csv(
        os.path.join(HERE, "validate_costsweep.csv"), index=False, encoding='utf-8-sig')

    # 평균 거래당 net R (비용별) — 빈도효과 직관
    print("\n[거래당 평균 net R(=gross-cost), bp] — 빈도 무관 '한 거래의 질'")
    for c in COSTS:
        mb = (rb['grossR'] - c).mean() * 10000; mi = (ri['grossR'] - c).mean() * 10000
        print(f"  {c*10000:>4.0f}bp: 기존 {mb:+.2f}bp / 분기 {mi:+.2f}bp")

    # ── ③ §9 재현 진단: stg6(264) vs base replay(328) ──
    print("\n[③ §9 재현 진단] stg6 원장(§9 264) vs 내 base replay(328)")
    s6 = pd.read_csv(STG6); s6['entry_t'] = pd.to_datetime(s6['entry_t'])
    bled = prep(bb)  # base trades already; need entry_t — re-extract
    # base entry_t set
    btr = TrendStackSignalBot(); btr.on_init({}); bt = btr.replay_7h(df7, oi7, gate_mode='er', gate_er=0.45)
    bset = set(pd.to_datetime([t['entry_t'] for t in bt]))
    s6set = set(s6['entry_t'])
    print(f"  stg6 거래 {len(s6)} | base replay {len(bt)}")
    print(f"  공통 진입시각 {len(bset & s6set)} | base만 {len(bset - s6set)} | stg6만 {len(s6set - bset)}")
    print(f"  stg6 연도분포: {dict(s6['entry_t'].dt.year.value_counts().sort_index())}")
    by = pd.Series([pd.Timestamp(x).year for x in [t['entry_t'] for t in bt]]).value_counts().sort_index()
    print(f"  base 연도분포: {dict(by)}")
    print(f"  stg6 reason분포: {dict(s6['reason'].value_counts())}")


if __name__ == "__main__":
    main()
