# [conclude.py] 결론: 환상율 + 진짜 수익률(환상 체결을 엔진 실제봉 경계로 캡 후 PaperAccount 재계산).
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); BOTS = os.path.join(HERE, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
from verify_fillbar import LogKing, LogImp, LogPatient
import bt36_ledgers as BT
import rauto_paper_engine as PE
from rauto_contract import MarketBar, Signal, Action, Side


def run_full(bot, dd):
    bot.on_init({}); sizes = []; maes = []
    held = False; entry = 0.0; side = 0; prior = 0.0; cur = 0.0; cbkt = None; cur_size = 0.0
    bkt7 = BT.bkt7
    for ts, o, h, l, c, v, oz in dd[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi_zscore_24h']].itertuples(index=False):
        oz = float(oz) if oz == oz else float('nan')
        sig = bot.on_bar(MarketBar(ts=ts, o=o, h=h, l=l, c=c, v=v, aux={'oi_zscore': oz}))
        if sig is not None and sig.action == Action.ENTER:
            held = True; entry = c; side = sig.side.value; prior = 0.0; cur = 0.0; cbkt = bkt7(ts); cur_size = float(sig.size_pct)
            ext = l if side == 1 else h; cur = min(cur, side * (ext - entry) / entry)
        elif sig is not None and sig.action == Action.EXIT and held:
            t = bot._trades[-1]; final = side * (t['exit'] - entry) / entry
            ec = cur if t['reason'] == 'trend_flip' else final
            sizes.append(cur_size); maes.append(min(prior, ec, final)); held = False
        elif held:
            b = bkt7(ts)
            if b != cbkt: prior = min(prior, cur); cur = 0.0; cbkt = b
            ext = l if side == 1 else h; cur = min(cur, side * (ext - entry) / entry)
    return bot, sizes, maes


def evaluate(bot, sizes, maes, m1):
    rep = PE.PaperAccount(10000.0); cap = PE.PaperAccount(10000.0); nf = 0; tot = 0
    for k, t in enumerate(bot._trades):
        if k >= len(sizes): break
        side = int(t['side']); e = float(t['exit']); entry = float(t['entry']); R = float(t['R'])
        reason = str(t['reason']); fund = float(t.get('fund', 0.0)); size = sizes[k]; mae = maes[k]
        xt = pd.Timestamp(t['exit_t'])
        lo = hi = None
        if 'intrabar' in reason:
            if xt in m1.index: lo, hi = m1.at[xt, 'low'], m1.at[xt, 'high']
        else:
            if xt in bot._bar: lo, hi = bot._bar[xt]
        Rreal = R
        if ('sl' in reason) and (lo is not None):
            tot += 1
            if not (lo <= e <= hi):
                nf += 1
                capped = lo if side == -1 else hi          # 현실 최선체결 = 봉경계
                Rreal = R + side * (capped - e) / entry     # led36 R은 raw(lev=1)
        slip = 0.0005 if ('sl' in reason) else 0.0
        for acc, RR in ((rep, R), (cap, Rreal)):
            acc.open(Signal(Action.ENTER, side=Side(side), size_pct=size, leverage=22.0), ts=None, price=100.0)
            acc.resolve_replay(R=RR - slip, mae=mae, fund=fund)
    return rep.metrics(), cap.metrics(), nf, tot


if __name__ == "__main__":
    dd = BT.load(); m1 = dd.set_index('timestamp')[['low', 'high']]
    print("봇 | 환상율 | 보고수익 | ★진짜수익(환상캡) | MDD진짜")
    for nm, mk in [("인내patient", LogPatient), ("성급R1", LogImp), ("성급왕R2", LogKing)]:
        bot, sizes, maes = run_full(mk(), dd)
        (rr, rm, _), (cr, cm, _), nf, tot = evaluate(bot, sizes, maes, m1)
        print(f"{nm} | {nf}/{tot}={nf/tot*100:.1f}% | {rr:+.0f}% | {cr:+.0f}% | MDD{cm:.1f}%")
