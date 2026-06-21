# -*- coding: utf-8 -*-
# [run_fastfail.py] 비대칭 Fast-Fail 변종 백테 (king-단독 k1.0·lev22·5bp 스톱슬립 공정비교).
#   V0(OFF)=king 동치 자가검증(+11397%/MDD-17.3%/668거래 재현必). 이후 변종 델타 측정.
#   거래생성 = 검증엔진(1m on_bar, bt36_ledgers와 동일 경로). 봇 무수정(상속 래퍼).
import os, sys
import numpy as np, pandas as pd

STG17 = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork"
BOTS = os.path.join(STG17, "bots")
for p in (BOTS, os.path.dirname(os.path.abspath(__file__))):
    if p not in sys.path: sys.path.insert(0, p)

import rauto_paper_engine as PE
from bot_trendstack_signal import BUCKET_7H
from rauto_contract import MarketBar, Signal, Action, Side
import bot_trendstack_impatient_king as TBK
import bot_trendstack_fastfail as FF

DATA = r"D:\ML\Verify\Merged_Data.csv"
SLIP = 0.0005


def load():
    dd = pd.read_csv(DATA, usecols=lambda c: c in ('timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi_zscore_24h'))
    dd['timestamp'] = pd.to_datetime(dd['timestamp'], utc=True).dt.tz_convert(None)
    return dd.dropna(subset=['open', 'high', 'low', 'close']).sort_values('timestamp').reset_index(drop=True)


def bkt7(ts): return int(pd.Timestamp(ts).value // 60_000_000_000) // 420


def run(make, dd):
    """봇 1m on_bar 흘려 ledger 생성 (bt36_ledgers.run 1:1 + reason 'ff' mae 처리)."""
    bot = make(); bot.on_init({})
    led = []; held = False; entry = 0.0; side = 0; prior = 0.0; cur = 0.0; cbkt = None; cur_size = 0.0
    for ts, o, h, l, c, v, oz in dd[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi_zscore_24h']].itertuples(index=False):
        oz = float(oz) if oz == oz else float('nan')
        sig = bot.on_bar(MarketBar(ts=ts, o=o, h=h, l=l, c=c, v=v, aux={'oi_zscore': oz}))
        if sig is not None and sig.action == Action.ENTER:
            held = True; entry = c; side = sig.side.value; prior = 0.0; cur = 0.0; cbkt = bkt7(ts)
            cur_size = float(sig.size_pct)
            ext = l if side == 1 else h; cur = min(cur, side * (ext - entry) / entry)
        elif sig is not None and sig.action == Action.EXIT and held:
            t = bot._trades[-1]
            final = side * (t['exit'] - entry) / entry
            ec = cur if t['reason'] in ('trend_flip', 'ff') else final
            mae = min(prior, ec, final)
            led.append(dict(entry_t=pd.Timestamp(t['entry_t']), exit_t=pd.Timestamp(ts), side=side,
                            entry_px=float(t['entry']), exit_px=float(t['exit']),
                            R=float(t['R']), size_pct=cur_size, fund=float(t.get('fund', 0.0)),
                            mae=float(mae), reason=t['reason'], year=pd.Timestamp(t['entry_t']).year))
            held = False
        elif held:
            b = bkt7(ts)
            if b != cbkt: prior = min(prior, cur); cur = 0.0; cbkt = b
            ext = l if side == 1 else h; cur = min(cur, side * (ext - entry) / entry)
    return pd.DataFrame(led)


def metrics(led):
    """king-단독 k1.0 lev22 5bp: 잔고시리즈→ret/mdd + PF/승률/손익비/연도/롱숏."""
    a = PE.PaperAccount(10000.0); rows = []
    for _, r in led.iterrows():
        side = int(r['side'])
        R = float(r['R']) - (SLIP if r['reason'] in ('sl', 'sl_intrabar') else 0.0)
        a.open(Signal(Action.ENTER, side=Side(side), size_pct=float(r['size_pct']), leverage=22.0), ts=None, price=100.0)
        p = a.resolve_replay(R=R, mae=float(r['mae']), fund=float(r['fund']))
        rows.append(dict(side=side, p=float(p or 0.0), year=int(r['year']), reason=r['reason']))
    rdf = pd.DataFrame(rows)
    # 일별 잔고 곡선은 거래순 누적으로 근사(comprehensive는 exit_t 일별; 여기선 단조 누적 → MDD는 거래순 peak기준)
    bal = 10000.0; eq = []
    for p in rdf['p'].values:
        bal *= (1 + p); eq.append(bal)
    eq = np.array(eq); pk = np.maximum.accumulate(eq); mdd = ((eq / pk - 1).min()) * 100 if len(eq) else 0.0
    nz = rdf[rdf['p'].abs() > 1e-12]; pv = nz['p'].values
    g = pv[pv > 0].sum(); b = -pv[pv < 0].sum(); pf = g / b if b > 0 else float('nan')
    wr = (pv > 0).mean() * 100 if len(pv) else 0
    w = pv[pv > 0]; ls = pv[pv < 0]
    payoff = (w.mean() / abs(ls.mean())) if len(w) and len(ls) else float('nan')
    ret = (eq[-1] / 10000.0 - 1) * 100 if len(eq) else 0.0
    # 연도
    yr = {}
    for y in (2023, 2024, 2025, 2026):
        sub = nz[nz['year'] == y]['p'].values
        if len(sub): yr[y] = (np.prod(1 + sub) - 1) * 100
    # 롱숏
    lsd = {}
    for nm, sd in (('long', 1), ('short', -1)):
        sub = nz[nz['side'] == sd]['p'].values
        if len(sub): lsd[nm] = (np.prod(1 + sub) - 1) * 100
    rc = rdf['reason'].value_counts().to_dict()
    return dict(ret=ret, mdd=mdd, n=len(pv), wr=wr, pf=pf, payoff=payoff, final=eq[-1] if len(eq) else 10000.0,
                yr=yr, ls=lsd, reasons=rc)


VARIANTS = {
    'off':  dict(FF_LONG=None, FF_SHORT=None, HALT_ENTRY=False),  # king 동치
    'v1':   dict(FF_LONG=1, FF_SHORT=None, HALT_ENTRY=True),      # 롱 즉시 fast-fail + halt
    'v2':   dict(FF_LONG=2, FF_SHORT=None, HALT_ENTRY=True),      # 롱 2봉확정 + halt
    'v3':   dict(FF_LONG=1, FF_SHORT=1, HALT_ENTRY=True),         # 대칭 (롱숏 둘다)
}


def make_factory(cfg):
    def mk():
        b = FF.TrendStackFastFailBot()
        b.FF_LONG = cfg['FF_LONG']; b.FF_SHORT = cfg['FF_SHORT']; b.HALT_ENTRY = cfg['HALT_ENTRY']
        return b
    return mk


if __name__ == "__main__":
    which = sys.argv[1:] or list(VARIANTS.keys())
    dd = load()
    print(f"data {len(dd)} rows {dd.timestamp.iloc[0]}~{dd.timestamp.iloc[-1]}\n")
    out = {}
    for name in which:
        cfg = VARIANTS[name]
        led = run(make_factory(cfg), dd)
        m = metrics(led)
        out[name] = (m, led)
        led.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), f"led_ff_{name}.csv"), index=False, encoding="utf-8-sig")
        print(f"[{name}] {cfg}")
        print(f"   ${m['final']:,.0f} ({m['ret']:+.0f}%) MDD{m['mdd']:.1f}% 거래{m['n']} 승률{m['wr']:.0f}% PF{m['pf']:.2f} 손익비{m['payoff']:.2f}")
        print(f"   연도 " + " ".join(f"{y}:{v:+.0f}%" for y, v in m['yr'].items()))
        print(f"   롱숏 " + " ".join(f"{k}:{v:+.0f}%" for k, v in m['ls'].items()) + f"   reasons={m['reasons']}")
    print("\n※ off는 king(+11397%/MDD-17.3%/668거래)과 동일해야 정상(동치 자가검증).")
