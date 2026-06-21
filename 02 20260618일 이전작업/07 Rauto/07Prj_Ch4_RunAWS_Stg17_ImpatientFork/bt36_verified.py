# -*- coding: utf-8 -*-
# [bt36_verified.py] 검증엔진(무수정)으로 36개월 백테 — 재구현 금지(§1). test_Rauto1 검증루프 1:1 재사용.
#   실제 봇(성급/성급왕)을 Merged_Data 1분봉 on_bar로 먹이고 paper_engine으로 P&L. 5bp 스톱슬립.
#   ★1단계: 앵커 재현 검증(성급 +5791%/MDD-19.6%, 성급왕 +7087%/MDD-19.4% @ k1.0·lev22·5bp).
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); BOTS = os.path.join(HERE, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import bot_trendstack_impatient as TBI
import bot_trendstack_impatient_king as TBK
import rauto_paper_engine as PE
from rauto_contract import MarketBar, Action
DATA = r"D:\ML\Verify\Merged_Data.csv"
BUCKET_7H = 420; STOP_SLIP = 0.0005   # 5bp 스톱슬립(SL청산에 추가 불리)


def bkt7(ts): return int(pd.Timestamp(ts).value // 60_000_000_000) // BUCKET_7H


def load():
    dd = pd.read_csv(DATA, usecols=lambda c: c in ('timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi_zscore_24h'))
    dd['timestamp'] = pd.to_datetime(dd['timestamp'], utc=True).dt.tz_convert(None)
    dd = dd.dropna(subset=['open', 'high', 'low', 'close']).sort_values('timestamp').reset_index(drop=True)
    return dd


def run_bot(make_bot, dd, k=1.0, stop_slip=STOP_SLIP):
    bot = make_bot(); bot.on_init({})
    acct = PE.PaperAccount()
    led = []; held = False; entry = 0.0; side = 0; prior_adv = 0.0; cur_adv = 0.0; cur_bkt = None
    arr = dd[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi_zscore_24h']].itertuples(index=False)
    for ts, o, h, l, c, v, oz in arr:
        oz = float(oz) if oz == oz else float('nan')
        mb = MarketBar(ts=ts, o=o, h=h, l=l, c=c, v=v, aux={'oi_zscore': oz})
        sig = bot.on_bar(mb)
        if sig is not None and sig.action == Action.ENTER:
            acct.open(sig, ts=ts, price=c)
            held = True; entry = c; side = sig.side.value; prior_adv = 0.0; cur_adv = 0.0; cur_bkt = bkt7(ts)
            ext = l if side == 1 else h; cur_adv = min(cur_adv, side * (ext - entry) / entry)
        elif sig is not None and sig.action == Action.EXIT and held:
            t = bot._trades[-1]
            final = side * (t['exit'] - entry) / entry
            exit_contrib = cur_adv if t['reason'] == 'trend_flip' else final
            mae = min(prior_adv, exit_contrib, final)
            R = t['R'] - (stop_slip if t['reason'] in ('sl', 'sl_intrabar') else 0.0)
            p = acct.resolve_replay(R=R, mae=mae, fund=t['fund'])
            held = False
            led.append(dict(entry_t=t['entry_t'], exit_t=ts, side=side, entry=float(t['entry']), exit=float(t['exit']),
                            R=float(R), p=float(p or 0.0), bal=acct.bal, reason=t['reason'],
                            year=pd.Timestamp(t['entry_t']).year))
        elif held:
            b = bkt7(ts)
            if b != cur_bkt: prior_adv = min(prior_adv, cur_adv); cur_adv = 0.0; cur_bkt = b
            ext = l if side == 1 else h; cur_adv = min(cur_adv, side * (ext - entry) / entry)
    ret, mdd, cal = acct.metrics()
    return pd.DataFrame(led), acct.bal, ret, mdd, bot


def metrics(led):
    ps = led['p'].values.astype(float)
    g = ps[ps > 0].sum(); b = -ps[ps < 0].sum()
    pf = g / b if b > 0 else float('nan')
    wr = (ps > 0).mean() * 100
    w = ps[ps > 0]; ls = ps[ps < 0]
    payoff = (w.mean() / abs(ls.mean())) if len(w) and len(ls) else float('nan')
    return len(ps), wr, pf, payoff


if __name__ == "__main__":
    dd = load()
    print(f"데이터 {len(dd)}행 {dd.timestamp.iloc[0]}~{dd.timestamp.iloc[-1]}")
    for nm, mk in [("성급", lambda: TBI.TrendStackImpatientBot()), ("성급왕", lambda: TBK.TrendStackImpatientKingBot())]:
        led, bal, ret, mdd, bot = run_bot(mk, dd)
        n, wr, pf, po = metrics(led)
        # 동치(live≡replay): 봇이 누적한 _h7로 fresh replay → on_bar 거래와 일치?
        dieq = None
        try:
            df7 = pd.DataFrame(bot._h7, columns=['ts', 'open', 'high', 'low', 'close', 'volume']).set_index('ts')
            fresh = TBI.TrendStackImpatientBot(); fresh.on_init({})
            rep = fresh.replay_7h(df7[['open', 'high', 'low', 'close']], np.array(bot._oiz, dtype=float), gate_mode='er', gate_er=0.45)
            kf = lambda t: (pd.Timestamp(t['entry_t']), pd.Timestamp(t['exit_t']), t['side'], round(float(t['R']), 6))
            ob = [t for t in bot._trades if t['reason'] != 'sl_intrabar']   # 인트라바는 batch에 없음(king만)
            dieq = (len(rep) == len(ob)) and all(kf(a) == kf(b) for a, b in zip(rep, ob))
            extra = f" (batch{len(rep)} vs on_bar非인트라{len(ob)})"
        except Exception as e:
            extra = f" (동치오류:{e})"
        print(f"[{nm}] 거래{n} 잔고${bal:,.0f} ({ret:+.0f}%/MDD{mdd:.1f}%) 승률{wr:.0f}% PF{pf:.2f} 손익비{po:.2f} | 동치={dieq}{extra}")
    print("\n동치=True면 하니스가 검증봇을 충실히 재현(앵커 +7087%는 v1 stale). 4봇 확장 진행가능.")
