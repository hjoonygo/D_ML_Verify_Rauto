# -*- coding: utf-8 -*-
# [optimize_dual.py] 성급TS+참을성SW 듀얼 장세조절(k·ER댐핑) 재최적화 — ★현실비용 14bp + 학습/검증분리.
#   비용: TS R(신호4bp) → R-0.0010 으로 14bp화. SW R은 이미 SW_COST 0.0014(14bp).
#   목표: 총수익 최대 s.t. 합산 MDD>=-20%(절대선). 전표본 + OOS(2023-24 최적→2025-26 적용)로 과최적합 점검.
#   3산출: ①성급TS단독 ②듀얼기본(k0.77/er0.40/w0.5) ③듀얼재최적(14bp 전표본 최적).
import os, sys, itertools
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); BOTS = os.path.join(HERE, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import trendstack_signal_engine as E
import trendstack_poc as P
import trendstack_regime as RG
import rauto_paper_engine as PE
import SidewayDCA_Stg7_engine as SWENG
from rauto_contract import Signal, Action, Side
from bot_trendstack_impatient import TrendStackImpatientBot

DATA = r"D:\ML\Verify\Merged_Data.csv"
TS_BASE = 7.0864; TS_LEV = 22.0; SH = 0.0; POC_LB = 60; POC_BINS = 50
SW_SIZE = 26.67; SW_LEV = 15.0; SW_SHORT = SWENG.SHORT_SIZE
MDD_LINE = -20.0
TS_RADJ = -0.0010      # 4bp→14bp (지정가/메이커 가정). SW는 이미 14bp.


def load():
    df = pd.read_csv(DATA, usecols=lambda c: c in
                     ('timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi_zscore_24h'))
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None)
    return df.set_index('timestamp')


def mdd_of(eq):
    eq = np.asarray(eq, float); pk = np.maximum.accumulate(eq); return ((eq - pk) / pk).min() * 100


def build():
    df = load(); m1 = df[['high', 'low']]; ohlc = df[['open', 'high', 'low', 'close']]
    df7 = E.resample_tf(ohlc, E.TF_MIN)
    vol7 = df['volume'].resample(f"{E.TF_MIN}min", label='left', closed='left').sum().reindex(df7.index).fillna(0.0)
    oi7 = df['oi_zscore_24h'].resample(f"{E.TF_MIN}min", label='left', closed='left').last().reindex(df7.index).values
    h7 = df7['high'].values; l7 = df7['low'].values; c7 = df7['close'].values; mid7 = (h7 + l7) / 2.0
    atr7 = E.compute_atr(h7, l7, c7, E.ATR_PERIOD); poc7 = P.compute_poc(h7, l7, mid7, vol7.values, POC_LB, POC_BINS)
    sig = E.compute_signals(df7); er7 = pd.Series(sig['er'], index=df7.index)
    df4 = E.resample_tf(ohlc, 240)
    try:
        _, fs = RG.feat_struct_of(df4, 8); fs.index = df4.index
    except Exception:
        fs = pd.Series("range", index=df4.index)
    bot = TrendStackImpatientBot(); bot.on_init({})
    tr = bot.replay_7h(df7, oi7, gate_mode='er', gate_er=0.45)
    t7 = df7.index.values; TS = []
    for t in tr:
        et, xt, side = t['entry_t'], t['exit_t'], int(t['side'])
        bi = int(np.searchsorted(t7, np.datetime64(et)))
        dev, rdir = P.dev_rdir(t['entry'], poc7[bi], atr7[bi]) if (bi < len(poc7) and atr7[bi] > 0 and not np.isnan(poc7[bi])) else (np.nan, 0)
        mlt = bot.opvnn_mult(dev, rdir, side)
        feat = str(fs.asof(et)) if len(fs) else "range"
        cut = SH if (feat == "uptrend" and side == -1) else 1.0
        base = TS_BASE * mlt * cut
        seg = m1.loc[et:xt]
        ext = (seg['low'].values if side == 1 else seg['high'].values) if len(seg) else np.array([t['entry']])
        mae = float(np.min(side * (ext - t['entry']) / t['entry']))
        TS.append(dict(exit_t=xt, year=pd.Timestamp(xt).year, side=side, base=base,
                       R=float(t['R']) + TS_RADJ, mae=mae, fund=float(t['fund']), er=2.0))  # TS er=2(항상 추세, 댐핑무관)
    sw = pd.read_csv(os.path.join(HERE, "sw_patient.csv"))
    sw['entry_t'] = pd.to_datetime(sw['entry_t']); sw['exit_t'] = pd.to_datetime(sw['exit_t'])
    SW = []
    for _, r in sw.iterrows():
        side = int(r['side']); base = SW_SIZE * (SW_SHORT if side == -1 else 1.0)
        er_at = er7.asof(r['entry_t'])
        SW.append(dict(exit_t=r['exit_t'], year=pd.Timestamp(r['exit_t']).year, side=side, base=base,
                       R=float(r['R']), mae=0.0, fund=0.0, er=float(er_at) if pd.notna(er_at) else 0.0))
    return TS, SW


def run_slot(recs, lev, kfun, years=None):
    acct = PE.PaperAccount(10000.0); ts = []; bals = []
    for r in recs:
        if years is not None and r['year'] not in years:
            continue
        size = r['base'] * kfun(r)
        if size <= 0:
            ts.append(r['exit_t']); bals.append(acct.bal); continue
        acct.open(Signal(Action.ENTER, side=Side(int(r['side'])), size_pct=size, leverage=lev), ts=None, price=100.0)
        acct.resolve_replay(R=r['R'], mae=r['mae'], fund=r['fund'])
        ts.append(r['exit_t']); bals.append(acct.bal)
    ret, mdd, _ = acct.metrics()
    return ts, bals, acct.bal, mdd


def portfolio(ts_t, ts_b, sw_t, sw_b):
    a = pd.DataFrame({'t': pd.to_datetime(ts_t), 'ts': ts_b}).groupby('t').last()
    b = pd.DataFrame({'t': pd.to_datetime(sw_t), 'sw': sw_b}).groupby('t').last() if len(sw_t) else pd.DataFrame({'sw': []})
    tl = pd.DataFrame(index=sorted(set(a.index).union(set(b.index))))
    tl['ts'] = a['ts'].reindex(tl.index).ffill().fillna(10000.0)
    tl['sw'] = (b['sw'].reindex(tl.index).ffill().fillna(10000.0)) if len(b) else 10000.0
    tl['port'] = tl['ts'] + tl['sw']
    return tl, (tl['port'].iloc[-1] / 20000.0 - 1) * 100, mdd_of(tl['port'].values)


def eval_dual(TS, SW, k, er_thr, w, years=None):
    tt, tb, _, _ = run_slot(TS, TS_LEV, lambda r: k, years)
    st, sb, _, _ = run_slot(SW, SW_LEV, lambda r: k * (w if r['er'] >= er_thr else 1.0), years)
    return portfolio(tt, tb, st, sb)


def optimize(TS, SW, years=None):
    KS = [0.6, 0.7, 0.77, 0.85, 0.95, 1.05]; ERT = [0.35, 0.40, 0.45]; WD = [0.0, 0.25, 0.5, 0.75, 1.0]
    best = None; allc = []
    for k, et, w in itertools.product(KS, ERT, WD):
        _, ret, mdd = eval_dual(TS, SW, k, et, w, years)
        allc.append(dict(k=k, er=et, w=w, ret=ret, mdd=mdd))
        if mdd >= MDD_LINE and (best is None or ret > best[0]):
            best = (ret, mdd, k, et, w)
    return best, pd.DataFrame(allc)


def main():
    TS, SW = build()
    print(f"[거래] TS-imp {len(TS)} / SW-patient {len(SW)} | ★현실비용 14bp")

    a_t, a_b, a_fin, a_mdd = run_slot(TS, TS_LEV, lambda r: 0.77)
    a_ret = (a_fin / 10000 - 1) * 100
    print(f"\n① 성급TS 단독(k0.77): ${a_fin:,.0f} ({a_ret:+.0f}%) MDD{a_mdd:.1f}% Calmar{a_ret/abs(a_mdd):.0f}")

    d_tl, d_ret, d_mdd = eval_dual(TS, SW, 0.77, 0.40, 0.5)
    print(f"② 듀얼 기본(k0.77/er0.40/w0.5): ${d_tl['port'].iloc[-1]:,.0f} ({d_ret:+.0f}% on$20k) MDD{d_mdd:.1f}% Calmar{d_ret/abs(d_mdd):.0f}")

    best, allc = optimize(TS, SW)
    allc.to_csv(os.path.join(HERE, "opt_allcombos.csv"), index=False)
    o_ret, o_mdd, k, et, w = best
    o_tl, _, _ = eval_dual(TS, SW, k, et, w)
    print(f"③ 듀얼 재최적(14bp 전표본): k{k}/er{et}/w{w} → ${o_tl['port'].iloc[-1]:,.0f} ({o_ret:+.0f}% on$20k) MDD{o_mdd:.1f}% Calmar{o_ret/abs(o_mdd):.0f}")

    # ── OOS: 2023-24 최적 → 2025-26 적용(과최적합 점검) ──
    print("\n[OOS 과최적합 점검]")
    tr_best, _ = optimize(TS, SW, years={2023, 2024})
    trr, trm, tk, tet, tw = tr_best
    _, te_ret, te_mdd = eval_dual(TS, SW, tk, tet, tw, years={2025, 2026})
    print(f"  학습(2023-24) 최적: k{tk}/er{tet}/w{tw} → {trr:+.0f}% MDD{trm:.1f}%")
    print(f"  → 검증(2025-26) 적용: {te_ret:+.0f}% MDD{te_mdd:.1f}%  ({'-20% 유지 OK' if te_mdd>=-20 else '★-20% 위반=과최적합'})")
    # 전표본 최적 config를 각 반기에 적용(안정성)
    _, h1r, h1m = eval_dual(TS, SW, k, et, w, years={2023, 2024})
    _, h2r, h2m = eval_dual(TS, SW, k, et, w, years={2025, 2026})
    print(f"  전표본최적 config 반기별: 23-24 {h1r:+.0f}%/MDD{h1m:.1f}% | 25-26 {h2r:+.0f}%/MDD{h2m:.1f}%")

    pd.DataFrame({'t': d_tl.index, 'port': d_tl['port'].values}).to_csv(os.path.join(HERE, "opt_default.csv"), index=False)
    pd.DataFrame({'t': o_tl.index, 'port': o_tl['port'].values}).to_csv(os.path.join(HERE, "opt_best.csv"), index=False)
    pd.DataFrame({'t': pd.to_datetime(a_t), 'bal': a_b}).to_csv(os.path.join(HERE, "opt_tsalone.csv"), index=False)
    with open(os.path.join(HERE, "opt_summary.txt"), "w", encoding="utf-8") as f:
        f.write(f"현실비용 14bp(지정가/메이커 가정)\n")
        f.write(f"① 성급TS단독 k0.77: {a_ret:+.0f}% MDD{a_mdd:.1f}% Calmar{a_ret/abs(a_mdd):.0f}\n")
        f.write(f"② 듀얼기본 k0.77/er0.40/w0.5: {d_ret:+.0f}% MDD{d_mdd:.1f}% Calmar{d_ret/abs(d_mdd):.0f}\n")
        f.write(f"③ 듀얼재최적 k{k}/er{et}/w{w}: {o_ret:+.0f}% MDD{o_mdd:.1f}% Calmar{o_ret/abs(o_mdd):.0f}\n")
        f.write(f"OOS: 학습23-24 k{tk}/er{tet}/w{tw} → 검증25-26 {te_ret:+.0f}%/MDD{te_mdd:.1f}%\n")
    print("\n[저장] opt_* + summary (14bp)")
    return dict(ts=(a_ret, a_mdd), dflt=(d_ret, d_mdd), opt=(o_ret, o_mdd, k, et, w))


if __name__ == "__main__":
    main()
