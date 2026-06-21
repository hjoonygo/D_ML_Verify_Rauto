# -*- coding: utf-8 -*-
# [test_Rauto_cvd.py] R5/R6/R7 라이브 러너 — CVD흡수+OI손절 챔피언변종. env로 파라미터화.
#   env: CVD_SLOT(R5) CVD_STRAT(TS_CvdBoth) CVD_VARIANT(both/rc_both/long) CVD_CHAMP(0/1)
#   C:\BinanceData(taker_buy_volume·open_interest 포함) → 피처(oi_zscore·oi_change_1h·cvd_z) → CvdStopBot → state.json.
#   ★equity=전구간 다운샘플, wk=최근7일 (R3/R4 버그 회피). 단독 $10k.
import os, sys, glob, json, datetime
import numpy as np, pandas as pd
if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__)); BOTS = os.path.join(HERE, "bots")
for p in (BOTS, HERE):
    if p not in sys.path: sys.path.insert(0, p)
import trendstack_signal_engine as E
import rauto_paper_engine as PE
import trendstack_regime as RG
from oi_zscore_adapter import build_aux
from bot_cvd_stop import CvdStopBot
from rauto_contract import MarketBar, Signal, Action, Side

DAUTO = os.environ.get("RAUTO_DAUTO_DIR", r"C:\BinanceData")
_CMAP = {"R5": ("TS_CvdBoth", "both"), "R6": ("TS_CvdRcBoth", "rc_both"), "R7": ("TS_CvdLong", "long")}  # bat은 SLOT만
SLOT = os.environ.get("CVD_SLOT", "R5")
STRAT = os.environ.get("CVD_STRAT") or _CMAP.get(SLOT, ("TS_Cvd", "long"))[0]
VARIANT = os.environ.get("CVD_VARIANT") or _CMAP.get(SLOT, ("", "long"))[1]
CHAMP = os.environ.get("CVD_CHAMP", "0") == "1"
LEV = 22.0; BUCKET_7H = 420; OUT_STATE = os.path.join(HERE, "state.json")
VCONF = {"both": dict(LONG_ONLY=False, RISK_CONSTANT=False),
         "rc_both": dict(LONG_ONLY=False, RISK_CONSTANT=True),
         "long": dict(LONG_ONLY=True, RISK_CONSTANT=False)}


def load():
    files = sorted(glob.glob(os.path.join(DAUTO, "BTCUSDT_1m_*.csv")))
    if not files: raise FileNotFoundError(f"Dauto 없음: {DAUTO}")
    cols = ['ts_utc', 'open', 'high', 'low', 'close', 'volume', 'taker_buy_volume', 'open_interest']
    dd = pd.concat([pd.read_csv(f, usecols=lambda c: c in cols) for f in files])
    dd['ts_utc'] = pd.to_datetime(dd['ts_utc'])
    dd = dd.drop_duplicates('ts_utc').sort_values('ts_utc').dropna(subset=['open', 'high', 'low', 'close']).reset_index(drop=True)
    # CVD z (인과적 롤링), OI 1h변화율
    if 'taker_buy_volume' in dd:
        net = 2.0 * dd['taker_buy_volume'] - dd['volume']
        c7 = net.rolling(420, min_periods=200).sum()
        W = 420 * 40
        dd['cvd_z'] = ((c7 - c7.rolling(W, min_periods=420).mean()) / (c7.rolling(W, min_periods=420).std() + 1e-9))
    else: dd['cvd_z'] = np.nan
    dd['oi_change_1h_pct'] = (dd['open_interest'].pct_change(60) * 100) if 'open_interest' in dd else np.nan
    return dd


def bkt7(ts): return int(pd.Timestamp(ts).value // 60_000_000_000) // BUCKET_7H


def main():
    dd = load()
    aux = build_aux(); aux['ts_utc'] = pd.to_datetime(aux['ts_utc'])
    dd = dd.merge(aux[['ts_utc', 'oi_zscore_24h']], on='ts_utc', how='left')
    print(f"[{SLOT}] {STRAT}({VARIANT}) | 1m {len(dd)}행 {dd.ts_utc.iloc[0]}~{dd.ts_utc.iloc[-1]}")

    bot = CvdStopBot()
    for k, v in VCONF[VARIANT].items(): setattr(bot, k, v)
    bot.on_init({})
    acct = PE.PaperAccount(10000.0); led = []
    held = False; entry = 0.0; side = 0; prior = 0.0; cur = 0.0; cbkt = None; csize = 0.0
    for ts, o, h, l, c, v, tb, oi, cz, oic, oz in dd[['ts_utc', 'open', 'high', 'low', 'close', 'volume', 'taker_buy_volume', 'open_interest', 'cvd_z', 'oi_change_1h_pct', 'oi_zscore_24h']].itertuples(index=False):
        oz = float(oz) if oz == oz else float('nan')
        mb = MarketBar(ts=ts, o=o, h=h, l=l, c=c, v=v, aux={'oi_zscore': oz, 'oi_change_1h_pct': oic, 'cvd_z': cz})
        sig = bot.on_bar(mb)
        if sig is not None and sig.action == Action.ENTER:
            acct.open(sig, ts=ts, price=c); held = True; entry = c; side = sig.side.value
            prior = 0.0; cur = 0.0; cbkt = bkt7(ts); csize = float(sig.size_pct)
            ext = l if side == 1 else h; cur = min(cur, side * (ext - entry) / entry)
        elif sig is not None and sig.action == Action.EXIT and held:
            t = bot._trades[-1]; final = side * (t['exit'] - entry) / entry
            ec = cur if t['reason'] in ('trend_flip', 'ff') else final
            mae = min(prior, ec, final)
            acct.resolve_replay(R=t['R'], mae=mae, fund=t.get('fund', 0.0))
            led.append(dict(entry_t=pd.Timestamp(t['entry_t']), exit_t=pd.Timestamp(ts), side=side,
                            entry_px=float(t['entry']), exit_px=float(t['exit']), R=float(t['R']),
                            bal=acct.bal, reason=t['reason']))
            held = False
        elif held:
            b = bkt7(ts)
            if b != cbkt: prior = min(prior, cur); cur = 0.0; cbkt = b
            ext = l if side == 1 else h; cur = min(cur, side * (ext - entry) / entry)
    ret, mdd, _ = acct.metrics()
    print(f"[거래] {len(bot._trades)} | 잔고 ${acct.bal:,.0f} ({ret:+.1f}%/MDD {mdd:.1f}%)")

    L = pd.DataFrame(led)
    ddw = dd[['ts_utc', 'high', 'low', 'close']]
    def _ms(t): return int(pd.Timestamp(t).value // 1_000_000)
    def _fillms(bar_t, price, win_start=None):
        p = float(price); tgt = pd.Timestamp(bar_t); t0 = pd.Timestamp(win_start) if win_start is not None else tgt
        seg = ddw[(ddw.ts_utc >= t0) & (ddw.ts_utc <= tgt + pd.Timedelta(hours=8))]
        if not len(seg): return _ms(bar_t)
        hit = seg[(seg.low <= p) & (seg.high >= p)]
        ts2 = hit.ts_utc.iloc[(hit.ts_utc - tgt).abs().values.argmin()] if len(hit) else seg.loc[(seg.close - p).abs().idxmin(), 'ts_utc']
        return _ms(ts2)
    # 품질 통계
    def _pf(a): a = np.asarray(a, float); g = a[a > 0].sum(); b = -a[a < 0].sum(); return round(float(g / b), 2) if b > 0 else None
    winrate = payoff = expect = pf_all = None; consec = 0; equity = [10000.0]; eqt = []; trades = []; wk = None; reg = {"up": None, "down": None, "range": None}
    if len(L):
        ps = (L['bal'] / L['bal'].shift(1).fillna(10000.0) - 1).values
        winrate = round(float((ps > 0).mean()) * 100); w = ps[ps > 0]; ls = ps[ps < 0]
        payoff = round(float(w.mean() / abs(ls.mean())), 1) if len(w) and len(ls) else None
        expect = round(float(ps.mean()) * 100, 2); pf_all = _pf(ps)
        cc = 0
        for x in ps: cc = cc + 1 if x < 0 else 0; consec = max(consec, cc)
        eqv = [10000.0] + list(L['bal'].values.astype(float)); eqtv = [_ms(L['entry_t'].iloc[0])] + [_ms(t) for t in L['exit_t'].values]
        if len(eqv) > 60:
            ix = np.linspace(0, len(eqv) - 1, 60).astype(int); equity = [round(eqv[i]) for i in ix]; eqt = [eqtv[i] for i in ix]
        else: equity = [round(x) for x in eqv]; eqt = eqtv
        # 장세별 PF (4H feat)
        try:
            o4 = dd.set_index('ts_utc')[['open', 'high', 'low', 'close']].resample('240min', label='left', closed='left').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
            _, fs = RG.feat_struct_of(o4, 8); fs.index = o4.index
            L['rk'] = L['entry_t'].apply(lambda t: ("up" if str(fs.asof(pd.Timestamp(t))) == "uptrend" else "down" if str(fs.asof(pd.Timestamp(t))) == "downtrend" else "range"))
            for k in ("up", "down", "range"):
                sub = ps[(L['rk'] == k).values]
                if len(sub): reg[k] = _pf(sub)
        except Exception: pass
        for _, rr in L.iterrows():
            sdn = "L" if int(rr['side']) == 1 else "S"
            trades.append({"et": _fillms(rr['entry_t'], rr['entry_px']), "ep": float(rr['entry_px']), "xt": _fillms(rr['exit_t'], rr['exit_px'], rr['entry_t']), "xp": float(rr['exit_px']), "side": sdn, "pnl": round(float(rr['R']) * 100, 1)})
        # 최근7일 wk
        try:
            cutx = pd.Timestamp(L['exit_t'].iloc[-1]) - pd.Timedelta(days=7); s7 = L[pd.to_datetime(L['exit_t']) >= cutx]
            if len(s7):
                p7 = (s7['bal'] / s7['bal'].shift(1).fillna(s7['bal'].iloc[0]) - 1).values; w7 = p7[p7 > 0]; l7 = p7[p7 < 0]; mx = cc = 0
                for x in p7: cc = cc + 1 if x < 0 else 0; mx = max(mx, cc)
                wk = {"trades": int(len(s7)), "winrate": round(float((p7 > 0).mean()) * 100), "payoff": round(float(w7.mean() / abs(l7.mean())), 1) if len(w7) and len(l7) else None, "consec": int(mx), "pf": _pf(p7), "ret": round((float(np.prod(1 + p7)) - 1) * 100, 1)}
        except Exception: pass
    # 15m px
    px = []
    try:
        o15 = dd.set_index('ts_utc')[['open', 'high', 'low', 'close']].resample('15min', label='left', closed='left').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
        if len(o15) > 4000: o15 = o15.iloc[-4000:]
        px = [[int(t.value // 1_000_000), round(float(r.open), 1), round(float(r.high), 1), round(float(r.low), 1), round(float(r.close), 1)] for t, r in o15.iterrows()]
    except Exception: pass
    last_data = pd.Timestamp(dd['ts_utc'].iloc[-1]); now = pd.Timestamp.utcnow().tz_localize(None); stale = (now - last_data).total_seconds() / 60.0
    open_now = bot.pos != 0; sd = "L" if bot.pos == 1 else "S" if bot.pos == -1 else "-"
    open_et = _fillms(bot._h7[bot.entry_i][0], bot.entry_price) if (open_now and 0 <= bot.entry_i < len(bot._h7) and not np.isnan(bot.entry_price)) else None
    state = {"balance": round(acct.bal, 2), "ret_pct": round(ret, 2), "mdd": round(mdd, 2), "exposure": 0.0, "exp_cap": 5.6,
             "guard_armed": True, "last_brake": "없음", "dauto_ok": bool(stale <= 15.0), "dauto_stale_min": round(stale, 1),
             "live": bool(os.environ.get("RAUTO_LIVE") == "1"),
             "acct": {k: None for k in ("balance", "spot", "fut_seed", "profit_gross", "trade_cost", "profit_net", "withdraw", "seed_topup", "other_cost")},
             "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "slots": [{"name": f"{SLOT}·{STRAT}", "side": sd, "pnl": 0.0, "champ": CHAMP, "kind": "추세",
                        "status": "보유" if open_now else "대기", "entry": round(float(bot.entry_price), 2) if open_now else None, "open_et": open_et,
                        "trades": len(bot._trades), "bal": round(acct.bal, 2), "ret": round(ret, 1), "mdd": round(mdd, 1),
                        "equity": equity, "eqt": eqt, "reg": reg, "winrate": winrate, "payoff": payoff, "expect": expect,
                        "consec": consec, "pf": pf_all, "px": px, "trd": trades, "wk": wk}]}
    with open(OUT_STATE, "w", encoding="utf-8") as f: json.dump(state, f, ensure_ascii=False, indent=1)
    print(f"[state] {SLOT} state.json | equity점={len(equity)} wk={'O' if wk else 'None'} 보유={open_now}")


if __name__ == "__main__":
    main()
