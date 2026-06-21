# -*- coding: utf-8 -*-
# [run_stopquality.py] C레버 봇 재실행(1m on_bar) → ledger → 전표본+CPCV.
#   OFF=king +11397% 재현(동치 관문2). 변종: sq_both(롱숏) / sq_long(롱전용).
#   aux에 oi_zscore(게이트용) + oi_change_1h_pct(손절품질용) 둘 다 공급.
import os, sys
from itertools import combinations
import numpy as np, pandas as pd
STG17 = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork"
BOTS = os.path.join(STG17, "bots")
for p in (BOTS, os.path.dirname(os.path.abspath(__file__))):
    if p not in sys.path: sys.path.insert(0, p)
import rauto_paper_engine as PE
from rauto_contract import MarketBar, Signal, Action, Side
import bot_stop_quality as SQ

DATA = r"D:\ML\Verify\Merged_Data.csv"
SLIP = 0.0005; LEV = 22.0


def load():
    dd = pd.read_csv(DATA, usecols=lambda c: c in ('timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi_zscore_24h', 'oi_change_1h_pct'))
    dd['timestamp'] = pd.to_datetime(dd['timestamp'], utc=True).dt.tz_convert(None)
    return dd.dropna(subset=['open', 'high', 'low', 'close']).sort_values('timestamp').reset_index(drop=True)


def bkt7(ts): return int(pd.Timestamp(ts).value // 60_000_000_000) // 420


def run(make, dd):
    bot = make(); bot.on_init({})
    led = []; held = False; entry = 0.0; side = 0; prior = 0.0; cur = 0.0; cbkt = None; cur_size = 0.0
    for ts, o, h, l, c, v, oz, oichg in dd[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi_zscore_24h', 'oi_change_1h_pct']].itertuples(index=False):
        oz = float(oz) if oz == oz else float('nan')
        sig = bot.on_bar(MarketBar(ts=ts, o=o, h=h, l=l, c=c, v=v, aux={'oi_zscore': oz, 'oi_change_1h_pct': oichg}))
        if sig is not None and sig.action == Action.ENTER:
            held = True; entry = c; side = sig.side.value; prior = 0.0; cur = 0.0; cbkt = bkt7(ts); cur_size = float(sig.size_pct)
            ext = l if side == 1 else h; cur = min(cur, side * (ext - entry) / entry)
        elif sig is not None and sig.action == Action.EXIT and held:
            t = bot._trades[-1]; final = side * (t['exit'] - entry) / entry
            ec = cur if t['reason'] in ('trend_flip', 'ff') else final
            mae = min(prior, ec, final)
            led.append(dict(entry_t=pd.Timestamp(t['entry_t']), exit_t=pd.Timestamp(ts), side=side,
                            R=float(t['R']), size_pct=cur_size, fund=float(t.get('fund', 0.0)),
                            mae=float(mae), reason=t['reason'], year=pd.Timestamp(t['entry_t']).year))
            held = False
        elif held:
            b = bkt7(ts)
            if b != cbkt: prior = min(prior, cur); cur = 0.0; cbkt = b
            ext = l if side == 1 else h; cur = min(cur, side * (ext - entry) / entry)
    return pd.DataFrame(led)


def metrics(led):
    a = PE.PaperAccount(10000.0); ps = []
    for _, r in led.iterrows():
        R = float(r['R']) - (SLIP if r['reason'] in ('sl', 'sl_intrabar') else 0.0)
        a.open(Signal(Action.ENTER, side=Side(int(r['side'])), size_pct=float(r['size_pct']), leverage=LEV), ts=None, price=100.0)
        ps.append(float(a.resolve_replay(R=R, mae=float(r['mae']), fund=float(r['fund'])) or 0.0))
    ps = np.array(ps); eq = 10000.0 * np.cumprod(1 + ps); pk = np.maximum.accumulate(eq)
    mdd = ((eq / pk - 1).min()) * 100; nz = ps[np.abs(ps) > 1e-12]
    g = nz[nz > 0].sum(); b = -nz[nz < 0].sum()
    return dict(ret=(eq[-1] / 10000 - 1) * 100, mdd=mdd, pf=g / b if b > 0 else float('nan'),
                wr=(nz > 0).mean() * 100, n=len(nz), reasons=led['reason'].value_counts().to_dict())


def cpcv(r, ng=6):
    r = np.asarray(r, float); grp = np.array_split(np.arange(len(r)), ng); rr = []
    for lv in combinations(range(ng), 2):
        idx = np.concatenate([x for j, x in enumerate(grp) if j not in lv])
        rr.append(np.prod(1.0 + r[idx]) - 1.0)
    rr = np.array(rr); return np.percentile(rr, 25), rr.min(), rr.mean()


VARIANTS = {
    'off':  dict(ENABLED=False),
    'both': dict(ENABLED=True, LONG_ONLY=False),
    'long': dict(ENABLED=True, LONG_ONLY=True),
    'rc_both': dict(ENABLED=True, LONG_ONLY=False, RISK_CONSTANT=True),  # MDD구제: 손절넓힘=사이즈축소
    'rc_long': dict(ENABLED=True, LONG_ONLY=True, RISK_CONSTANT=True),
}


def mk(cfg):
    def _m():
        b = SQ.StopQualityKingBot()
        for k, val in cfg.items(): setattr(b, k, val)
        return b
    return _m


if __name__ == "__main__":
    which = sys.argv[1:] or list(VARIANTS.keys())
    dd = load(); print(f"data {len(dd)} {dd.timestamp.iloc[0]}~{dd.timestamp.iloc[-1]}\n")
    leds = {}
    print("=== 전표본 (PaperAccount k1.0 lev22 5bp) ===")
    for name in which:
        led = run(mk(VARIANTS[name]), dd); leds[name] = led
        led.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), f"led_sq_{name}.csv"), index=False, encoding="utf-8-sig")
        m = metrics(led)
        print(f"  [{name}] {m['ret']:+.0f}% MDD{m['mdd']:.1f}% PF{m['pf']:.2f} 승률{m['wr']:.0f}% 거래{m['n']} reasons={m['reasons']}")
    print("\n=== CPCV 표준6(15경로) ===")
    print(f"{'비용':>5} {'mode':>6} | {'전표본':>9} {'p25':>9} {'최악':>9} {'평균':>9} | 판정")
    for C in (0.0004, 0.0008):
        for name in which:
            led = leds[name].sort_values('entry_t').reset_index(drop=True)
            exp = led['size_pct'].values / 100.0 * LEV
            r = (led['R'].values + 0.0004 - C) * exp
            full = (np.prod(1 + r) - 1) * 100; p25, mn, mean = cpcv(r)
            ok = "PASS(견고)" if (p25 > 0 and mn > 0) else ("p25>0 최악<0" if p25 > 0 else "FAIL")
            print(f"{C*1e4:>3.0f}bp {name:>6} | {full:>+8.0f}% {p25*100:>+8.0f}% {mn*100:>+8.0f}% {mean*100:>+8.0f}% | {ok}")
    print("\n※ off=king +11397%/MDD-17.3%/668 재현해야 정상. PQ와 달리 거래수/reason도 바뀜(손절거리 변경).")
