# -*- coding: utf-8 -*-
# [plugin_common.py] 4봇 Plugin 공용 실슬리피지 백테 하니스 — 검증 ledger 기반(Merged_Data 불요로 재현).
#   입력: led36_king.csv·led36_imp_pinned.csv(핀고정 검증엔진 on_bar 산출)·sw_patient_er.csv(인내SW+ER).
#   비용: 손절 5bp 스톱슬립(검증 A/B '0~20bp 견고' 범위), 진입/청산 슬립~0(measure_slippage 검증). lev22(SW lev15).
#   재현 검증: R1≈+5932·R2≈+11397·R3≈+8850·R4≈+30156%.
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); BOTS = os.path.join(HERE, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import rauto_paper_engine as PE
import SidewayDCA_Stg7_engine as SWENG
from rauto_contract import Signal, Action, Side
SLIP = 0.0005; SW_SIZE = 26.67; SW_LEV = 15.0; SW_SHORT = SWENG.SHORT_SIZE


def _load():
    king = pd.read_csv(os.path.join(HERE, "led36_king.csv"), parse_dates=['entry_t', 'exit_t'])
    imp = pd.read_csv(os.path.join(HERE, "led36_imp_pinned.csv"), parse_dates=['entry_t', 'exit_t'])
    swf = os.path.join(HERE, "sw_patient_er.csv")
    sw = pd.read_csv(swf if os.path.exists(swf) else os.path.join(HERE, "sw_patient.csv"), parse_dates=['entry_t', 'exit_t'])
    if 'er' not in sw.columns: sw['er'] = 0.0   # ER 없으면 무댐핑(보수)
    return king, imp, sw


def _days(king):
    s = pd.Timestamp(king['entry_t'].min()).normalize(); e = pd.Timestamp(king['exit_t'].max()).normalize()
    return pd.date_range(s, e, freq='D')


def _daily(series, days):
    return series.reindex(series.index.union(days)).sort_index().ffill().reindex(days).ffill().fillna(series.iloc[0] if len(series) else 0.0)


def _acct(led, k, is_sw=False, er_thr=0.40, w=0.0):
    a = PE.PaperAccount(10000.0); rows = []
    for _, r in led.iterrows():
        side = int(r['side'])
        if is_sw:
            weff = w if float(r.get('er', 0.0)) >= er_thr else 1.0
            size = SW_SIZE * (SW_SHORT if side == -1 else 1.0) * k * weff
            R = float(r['R']); lev = SW_LEV; fund = 0.0; mae = 0.0
        else:
            size = float(r['size_pct']) * k; lev = 22.0
            R = float(r['R']) - (SLIP if r['reason'] in ('sl', 'sl_intrabar') else 0.0)
            fund = float(r['fund']); mae = float(r['mae'])
        if size > 0:
            a.open(Signal(Action.ENTER, side=Side(side), size_pct=size, leverage=lev), ts=None, price=100.0)
            p = a.resolve_replay(R=R, mae=mae, fund=fund)
        else:
            p = 0.0
        rows.append(dict(exit_t=pd.Timestamp(r['exit_t']), side=side, p=float(p or 0.0), year=int(r['year']), bal=a.bal))
    return pd.DataFrame(rows)


def _metrics(rows, eq, base):
    nz = rows[rows['p'].abs() > 1e-12]; pv = nz['p'].values
    g = pv[pv > 0].sum(); b = -pv[pv < 0].sum(); pf = g / b if b > 0 else float('nan')
    w = pv[pv > 0]; ls = pv[pv < 0]
    eqv = eq.values; pk = np.maximum.accumulate(eqv); mdd = ((eqv / pk - 1).min()) * 100
    return dict(final=float(eqv[-1]), ret=float((eqv[-1] / base - 1) * 100), mdd=float(mdd), n=int(len(pv)),
                wr=float((pv > 0).mean() * 100) if len(pv) else 0, pf=float(pf),
                payoff=float(w.mean() / abs(ls.mean())) if len(w) and len(ls) else float('nan'))


def _yearly(rows):
    out = {}
    for y in sorted(rows['year'].unique()):
        sub = rows[(rows['year'] == y) & (rows['p'].abs() > 1e-12)]; pv = sub['p'].values
        if not len(pv): continue
        g = pv[pv > 0].sum(); b = -pv[pv < 0].sum()
        out[int(y)] = dict(ret=float((np.prod(1 + pv) - 1) * 100), n=int(len(pv)), wr=float((pv > 0).mean() * 100), pf=(float(g / b) if b > 0 else None))
    return out


def _longshort(rows):
    out = {}
    for nm, sd in (('long', 1), ('short', -1)):
        sub = rows[(rows['side'] == sd) & (rows['p'].abs() > 1e-12)]; pv = sub['p'].values
        if not len(pv): continue
        g = pv[pv > 0].sum(); b = -pv[pv < 0].sum()
        out[nm] = dict(ret=float((np.prod(1 + pv) - 1) * 100), n=int(len(pv)), wr=float((pv > 0).mean() * 100), pf=(float(g / b) if b > 0 else None))
    return out


def run_single(which, k=1.0):
    king, imp, sw = _load(); led = king if which == 'king' else imp
    rows = _acct(led, k); days = _days(king)
    eq = _daily(rows.groupby('exit_t')['bal'].last(), days)
    return _metrics(rows, eq, 10000.0), _yearly(rows), _longshort(rows)


def run_dual(k=1.1, er_thr=0.40, w=0.0):
    king, imp, sw = _load()
    kr = _acct(king, k); sr = _acct(sw, k, is_sw=True, er_thr=er_thr, w=w); days = _days(king)
    eq = _daily(kr.groupby('exit_t')['bal'].last(), days) + _daily(sr.groupby('exit_t')['bal'].last(), days)
    allrows = pd.concat([kr, sr]).sort_values('exit_t')
    return _metrics(allrows, eq, 20000.0), _yearly(allrows), _longshort(allrows)


def report(name, res):
    m, yr, ls = res
    print(f"[{name}] ${m['final']:,.0f} ({m['ret']:+.0f}%) MDD{m['mdd']:.1f}% 거래{m['n']} 승률{m['wr']:.0f}% PF{m['pf']:.2f} 손익비{m['payoff']:.2f}")
    print("  연도 " + " ".join(f"{y}:{v['ret']:+.0f}%" for y, v in yr.items()))
    print("  롱숏 " + " ".join(f"{k2}:{v['ret']:+.0f}%/승{v['wr']:.0f}%" for k2, v in ls.items()))
    return m, yr, ls
