# -*- coding: utf-8 -*-
# [comprehensive_4bot.py] 4봇(R1성급·R2성급왕·R3듀얼k1.1·R4듀얼k1.4) 36개월 종합/연도/롱숏.
#   신뢰 ledger(핀고정 검증엔진): led36_imp_pinned/led36_king + sw_patient(인내SW). 5bp 스톱슬립, lev22(SW lev15).
#   듀얼 = king(k) + SW(k, ER>=0.40→size×0 댐핑) 일별합성 $20k. 단독 $10k.
#   R1/R2 내부검증: +5932%/+11397% 재현되어야 함.
import os, sys, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); BOTS = os.path.join(HERE, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import trendstack_signal_engine as E, rauto_paper_engine as PE
import SidewayDCA_Stg7_engine as SWENG
from rauto_contract import Signal, Action, Side
DATA = r"D:\ML\Verify\Merged_Data.csv"
SLIP = 0.0005; SW_SIZE = 26.67; SW_LEV = 15.0; SW_SHORT = SWENG.SHORT_SIZE; ERT = 0.40

imp = pd.read_csv(os.path.join(HERE, "led36_imp_pinned.csv"), parse_dates=['entry_t', 'exit_t'])
king = pd.read_csv(os.path.join(HERE, "led36_king.csv"), parse_dates=['entry_t', 'exit_t'])
sw = pd.read_csv(os.path.join(HERE, "sw_patient.csv"), parse_dates=['entry_t', 'exit_t'])

# SW 댐핑용 ER 시리즈(신호엔진)
df = pd.read_csv(DATA, usecols=lambda c: c in ('timestamp', 'open', 'high', 'low', 'close'))
df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None); df = df.set_index('timestamp')
df7 = E.resample_tf(df[['open', 'high', 'low', 'close']], E.TF_MIN)
er7 = pd.Series(E.compute_signals(df7)['er'], index=df7.index)
sw['er'] = sw['entry_t'].map(lambda t: er7.asof(pd.Timestamp(t))).astype(float)

DAYS = pd.date_range(df7.index[0].normalize(), df7.index[-1].normalize(), freq='D')
def daily(s): return s.reindex(s.index.union(DAYS)).sort_index().ffill().reindex(DAYS).ffill().fillna(s.iloc[0] if len(s) else 0.0)


def acct_ledger(led, k, is_sw=False):
    """ledger → (exit_t별 잔고 시리즈, per-trade dict 리스트). $10k base."""
    a = PE.PaperAccount(10000.0); rows = []
    for _, r in led.iterrows():
        side = int(r['side'])
        if is_sw:
            w = 0.0 if r['er'] >= ERT else 1.0
            size = SW_SIZE * (SW_SHORT if side == -1 else 1.0) * k * w
            R = float(r['R']); lev = SW_LEV; fund = 0.0; mae = 0.0
        else:
            size = float(r['size_pct']) * k; lev = 22.0
            R = float(r['R']) - (SLIP if r['reason'] in ('sl', 'sl_intrabar') else 0.0)
            fund = float(r['fund']); mae = float(r['mae'])
        b0 = a.bal
        a.open(Signal(Action.ENTER, side=Side(side), size_pct=size, leverage=lev), ts=None, price=100.0)
        p = a.resolve_replay(R=R, mae=mae if size > 0 else 0.0, fund=fund) if size > 0 else 0.0
        rows.append(dict(exit_t=pd.Timestamp(r['exit_t']), side=side, p=float(p or 0.0), year=int(r['year']), bal=a.bal))
    return pd.DataFrame(rows), a


def series_from(rows):
    s = rows.groupby('exit_t')['bal'].last()
    return daily(s)


def metrics_from_ptrades(rows, eq_daily, base):
    ps = rows['p'].values.astype(float)
    ps = ps[rows['p'].abs().values > 0] if 'p' in rows else ps
    nz = rows[rows['p'].abs() > 1e-12]
    pv = nz['p'].values
    g = pv[pv > 0].sum(); b = -pv[pv < 0].sum()
    pf = g / b if b > 0 else float('nan')
    wr = (pv > 0).mean() * 100 if len(pv) else 0
    w = pv[pv > 0]; ls = pv[pv < 0]
    payoff = (w.mean() / abs(ls.mean())) if len(w) and len(ls) else float('nan')
    eq = eq_daily.values; pk = np.maximum.accumulate(eq); mdd = ((eq / pk - 1).min()) * 100
    ret = (eq[-1] / base - 1) * 100
    return dict(final=float(eq[-1]), ret=float(ret), mdd=float(mdd), n=int(len(pv)),
                wr=float(wr), pf=float(pf), payoff=float(payoff))


def yearly(rows, base_each):
    out = {}
    for y in (2023, 2024, 2025, 2026):
        sub = rows[(rows['year'] == y) & (rows['p'].abs() > 1e-12)]
        pv = sub['p'].values
        if not len(pv): continue
        g = pv[pv > 0].sum(); b = -pv[pv < 0].sum()
        out[y] = dict(ret=float((np.prod(1 + pv) - 1) * 100), n=int(len(pv)),
                      wr=float((pv > 0).mean() * 100), pf=float(g / b) if b > 0 else None)
    return out


def longshort(rows):
    out = {}
    for nm, sd in (('long', 1), ('short', -1)):
        sub = rows[(rows['side'] == sd) & (rows['p'].abs() > 1e-12)]
        pv = sub['p'].values
        if not len(pv): continue
        g = pv[pv > 0].sum(); b = -pv[pv < 0].sum()
        w = pv[pv > 0]; l = pv[pv < 0]
        out[nm] = dict(ret=float((np.prod(1 + pv) - 1) * 100), n=int(len(pv)),
                       wr=float((pv > 0).mean() * 100), pf=float(g / b) if b > 0 else None,
                       payoff=float(w.mean() / abs(l.mean())) if len(w) and len(l) else None)
    return out


def build_single(led, is_sw=False):
    rows, a = acct_ledger(led, 1.0, is_sw)
    eq = series_from(rows)
    m = metrics_from_ptrades(rows, eq, 10000.0)
    return m, yearly(rows, 10000.0), longshort(rows), eq, rows


def build_dual(k):
    kr, _ = acct_ledger(king, k, False)
    sr, _ = acct_ledger(sw, k, True)
    eqk = series_from(kr); eqs = series_from(sr)
    eq = daily(pd.Series(eqk.values, index=DAYS)) + daily(pd.Series(eqs.values, index=DAYS))
    allrows = pd.concat([kr, sr]).sort_values('exit_t')
    m = metrics_from_ptrades(allrows, eq, 20000.0)
    return m, yearly(allrows, 20000.0), longshort(allrows), eq, allrows


res = {}
for key, (m, yr, ls, eq, rows) in [
    ("R1 성급", build_single(imp)),
    ("R2 성급왕", build_single(king)),
    ("R3 듀얼k1.1", build_dual(1.1)),
    ("R4 듀얼k1.4", build_dual(1.4)),
]:
    res[key] = dict(metrics=m, yearly=yr, longshort=ls,
                    equity=[round(float(v)) for v in eq.values[::max(1, len(eq)//60)]],
                    eqt=[int(pd.Timestamp(t).value // 10**6) for t in eq.index[::max(1, len(eq)//60)]])
    print(f"[{key}] ${m['final']:,.0f} ({m['ret']:+.0f}%) MDD{m['mdd']:.1f}% 거래{m['n']} 승률{m['wr']:.0f}% PF{m['pf']:.2f} 손익비{m['payoff']:.2f}")
    print(f"    연도 " + " ".join(f"{y}:{v['ret']:+.0f}%(PF{v['pf']:.1f})" for y, v in yr.items() if v['pf']))
    print(f"    롱숏 " + " ".join(f"{k2}:{v['ret']:+.0f}%/PF{v['pf']:.1f}/승{v['wr']:.0f}%" for k2, v in ls.items() if v['pf']))
json.dump(res, open(os.path.join(HERE, "comprehensive_4bot.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n검증: R1≈+5932% R2≈+11397% 면 정상. JSON 저장.")
