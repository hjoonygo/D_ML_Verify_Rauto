# -*- coding: utf-8 -*-
# [test_dual_runner.py] 듀얼 슬롯 러너 — 성급왕TS + 인내SW, k·ER댐핑. env로 R3/R4 파라미터화.
#   env: DUAL_SLOT(R3) DUAL_STRAT(최적듀얼) DUAL_K(1.1) DUAL_ER(0.40) DUAL_W(0.0) DUAL_CHAMP(0/1)
#   C:\BinanceData 1m → king(on_bar)+SW(on_bar) → 두 페이퍼계좌 합산 포트($20k) → state.json(대시보드).
import os, sys, glob, json, datetime
import numpy as np, pandas as pd
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__)); BOTS = os.path.join(HERE, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import trendstack_signal_engine as E
import rauto_paper_engine as PE
import SidewayDCA_Stg7_engine as SWENG
from bot_trendstack_impatient_king import TrendStackImpatientKingBot
from bot_sidewaydca_signal import SidewayDCASignalBot
from oi_zscore_adapter import build_aux
from atr_ratio_adapter import build_aux as build_atr_aux
from rauto_contract import MarketBar, Action

DAUTO = os.environ.get("RAUTO_DAUTO_DIR", r"C:\BinanceData")
_DMAP = {"R3": ("최적듀얼", 1.1), "R4": ("최고Calmar듀얼", 1.4)}   # bat은 SLOT만 줘도 됨(한글명·k 여기서 결정)
SLOT = os.environ.get("DUAL_SLOT", "R3")
STRAT = os.environ.get("DUAL_STRAT") or _DMAP.get(SLOT, ("듀얼", 1.1))[0]
K = float(os.environ.get("DUAL_K") or _DMAP.get(SLOT, ("", 1.1))[1]); ER_THR = float(os.environ.get("DUAL_ER", "0.40"))
W = float(os.environ.get("DUAL_W", "0.0")); CHAMP = os.environ.get("DUAL_CHAMP", "0") == "1"
TS_LEV = 22.0; SW_COST = 0.0014
OUT_STATE = os.path.join(HERE, "state.json")


def load_stream():
    files = sorted(glob.glob(os.path.join(DAUTO, "BTCUSDT_1m_*.csv")))
    dd = pd.concat([pd.read_csv(f, usecols=['ts_utc', 'open', 'high', 'low', 'close', 'volume']) for f in files])
    dd['ts_utc'] = pd.to_datetime(dd['ts_utc'])
    return dd.drop_duplicates('ts_utc').sort_values('ts_utc').dropna(subset=['open', 'high', 'low', 'close']).reset_index(drop=True)


def main():
    dd = load_stream()
    aux = build_aux(); aux['ts_utc'] = pd.to_datetime(aux['ts_utc'])
    dd = dd.merge(aux[['ts_utc', 'oi_zscore_24h']], on='ts_utc', how='left')
    try:
        adf = build_atr_aux(); adf['ts_utc'] = pd.to_datetime(adf['ts_utc'])
        dd = dd.merge(adf[['ts_utc', 'atr_ratio']], on='ts_utc', how='left')
    except Exception:
        dd['atr_ratio'] = np.nan
    print(f"[{SLOT}] {STRAT} | 1m {len(dd)}행({dd.ts_utc.iloc[0]}~{dd.ts_utc.iloc[-1]}) | k{K}·er{ER_THR}·w{W}")

    # ER 룩업(7h) — SW 댐핑 판정용
    d7 = dd.set_index('ts_utc')[['open', 'high', 'low', 'close']].resample('420min', label='left', closed='left').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
    er7 = pd.Series(E.compute_signals(d7)['er'], index=d7.index)

    king = TrendStackImpatientKingBot(); king.on_init({})
    sw = SidewayDCASignalBot(); sw.on_init({})
    aT = PE.PaperAccount(10000.0); aW = PE.PaperAccount(10000.0)
    ts_sz = None; sw_sz = None; nT = 0; nW = 0
    tl = []   # (ts_utc, aT.bal, aW.bal)
    for ts, o, h, l, c, v, oz, ar in dd.itertuples(index=False):
        oz = float(oz) if oz == oz else float('nan'); ar = float(ar) if ar == ar else float('nan')
        sg = king.on_bar(MarketBar(ts=ts, o=o, h=h, l=l, c=c, v=v, aux={'oi_zscore': oz}))
        if sg is not None and sg.action == Action.ENTER: ts_sz = sg.size_pct
        if len(king._trades) > nT:
            t = king._trades[-1]; nT = len(king._trades)
            aT.open(__import__('rauto_contract').Signal(Action.ENTER, side=__import__('rauto_contract').Side(int(t['side'])),
                    size_pct=(ts_sz or 7.0864) * K, leverage=TS_LEV), ts=None, price=100.0)
            aT.resolve_replay(R=t['R'], mae=min(0.0, t['R']), fund=t.get('fund', 0.0))
        sgw = sw.on_bar(MarketBar(ts=ts, o=o, h=h, l=l, c=c, v=v, aux={'oi_zscore_24h': oz, 'atr_ratio': ar}))
        if sgw is not None and sgw.action == Action.ENTER:
            e = er7.asof(ts); weff = W if (pd.notna(e) and e >= ER_THR) else 1.0
            sw_sz = (sgw.size_pct or 26.67) * K * weff
        if len(sw.trades) > nW:
            t = sw.trades[-1]; nW = len(sw.trades)
            R = int(t['side']) * (float(t['exit']) - float(t['entry'])) / float(t['entry']) - SW_COST
            aW.open(__import__('rauto_contract').Signal(Action.ENTER, side=__import__('rauto_contract').Side(int(t['side'])),
                    size_pct=(sw_sz or 0.0), leverage=SWENG.DEFAULT_LEV if hasattr(SWENG, 'DEFAULT_LEV') else 15.0), ts=None, price=100.0)
            if (sw_sz or 0) > 0: aW.resolve_replay(R=R, mae=0.0, fund=0.0)
        tl.append((ts, aT.bal, aW.bal))

    T = pd.DataFrame(tl, columns=['t', 'ts', 'sw']).groupby('t').last()
    port = (T['ts'] + T['sw']).values
    pk = np.maximum.accumulate(port); mdd = ((port - pk) / pk).min() * 100
    ret = (port[-1] / 20000.0 - 1) * 100
    bal = float(port[-1])
    # 합산 거래목록(차트 마커): king + SW
    # et/xt = 실제 체결 분(_fillms, 7H봉 라벨→1m 역산) → 15m/1H/4H 캔들 정렬. (구: raw _ms 봉라벨이라 어긋남)
    def _ms(t): return int(pd.Timestamp(t).value // 1_000_000)
    ddw = dd[['ts_utc', 'high', 'low', 'close']]
    def _fillms(bar_t, price, win_start=None):
        p = float(price); tgt = pd.Timestamp(bar_t)
        t0 = pd.Timestamp(win_start) if win_start is not None else tgt
        seg = ddw[(ddw.ts_utc >= t0) & (ddw.ts_utc <= tgt + pd.Timedelta(hours=8))]
        if not len(seg):
            return _ms(bar_t)
        hit = seg[(seg.low <= p) & (seg.high >= p)]
        ts = hit.ts_utc.iloc[(hit.ts_utc - tgt).abs().values.argmin()] if len(hit) else seg.loc[(seg.close - p).abs().idxmin(), 'ts_utc']
        return _ms(ts)
    trd = []
    for t in king._trades:
        trd.append({"et": _fillms(t['entry_t'], t['entry']), "ep": float(t['entry']), "xt": _fillms(t['exit_t'], t['exit'], t['entry_t']),
                    "xp": float(t['exit']), "side": "L" if int(t['side']) == 1 else "S",
                    "pnl": round(float(t['R']) * 100, 1)})
    for t in sw.trades:
        R = int(t['side']) * (float(t['exit']) - float(t['entry'])) / float(t['entry']) - SW_COST
        trd.append({"et": _fillms(t['entry_t'], t['entry']), "ep": float(t['entry']), "xt": _fillms(t['exit_t'], t['exit'], t['entry_t']),
                    "xp": float(t['exit']), "side": ("L" if int(t['side']) == 1 else "S") + "·SW",
                    "pnl": round(R * 100, 1)})
    # 합산 거래성과(품질)
    allR = [float(t['R']) for t in king._trades] + [int(t['side']) * (float(t['exit']) - float(t['entry'])) / float(t['entry']) - SW_COST for t in sw.trades]
    allR = np.array(allR) if allR else np.array([0.0])
    wr = round(float((allR > 0).mean()) * 100) if len(allR) else 0
    pf = round(float(allR[allR > 0].sum() / -allR[allR < 0].sum()), 2) if (allR < 0).any() else None
    # 자산곡선(날짜축) — ★버그수정: 전구간 균등 다운샘플(구버그=마지막 400'분'만 잡아 1일만 표시).
    eqd = T.reset_index(); eqd['port'] = eqd['ts'] + eqd['sw']
    _n = len(eqd)
    _ix = np.linspace(0, _n - 1, min(400, _n)).astype(int) if _n else np.array([], dtype=int)
    equity = [round(float(eqd['port'].values[i]), 1) for i in _ix]
    eqt = [int(pd.Timestamp(eqd['t'].values[i]).value // 1_000_000) for i in _ix]
    # 가격(15m)
    o15 = dd.set_index('ts_utc')[['open', 'high', 'low', 'close']].resample('15min', label='left', closed='left').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
    if len(o15) > 4000: o15 = o15.iloc[-4000:]
    px = [[int(t.value // 1_000_000), round(float(r.open), 1), round(float(r.high), 1), round(float(r.low), 1), round(float(r.close), 1)] for t, r in o15.iterrows()]
    last_data = pd.Timestamp(dd['ts_utc'].iloc[-1]); now = pd.Timestamp.utcnow().tz_localize(None)
    stale = (now - last_data).total_seconds() / 60.0
    # ── 최근7일 통계(wk) — ★버그수정: 구버그 None. king+SW 합산, exit_t 기준 최근7일 ──
    wk = None
    _atr = [(pd.Timestamp(t['exit_t']), float(t['R'])) for t in king._trades]
    _atr += [(pd.Timestamp(t['exit_t']), int(t['side']) * (float(t['exit']) - float(t['entry'])) / float(t['entry']) - SW_COST) for t in sw.trades]
    if _atr:
        cutx = last_data - pd.Timedelta(days=7)
        p7 = np.array([r for (xt, r) in _atr if xt >= cutx], float)
        if len(p7):
            w7 = p7[p7 > 0]; l7 = p7[p7 < 0]; cc = mx = 0
            for v in p7:
                cc = cc + 1 if v < 0 else 0; mx = max(mx, cc)
            wk = {"trades": int(len(p7)), "winrate": round(float((p7 > 0).mean()) * 100),
                  "payoff": round(float(w7.mean() / abs(l7.mean())), 1) if len(w7) and len(l7) else None,
                  "consec": int(mx), "pf": round(float(w7.sum() / -l7.sum()), 2) if len(l7) else None,
                  "ret": round((float(np.prod(1 + p7)) - 1) * 100, 1)}
    print(f"[거래] TS {len(king._trades)} + SW {len(sw.trades)} | 포트 ${bal:,.0f} ({ret:+.1f}%/MDD {mdd:.1f}%)")
    state = {"balance": round(bal, 2), "ret_pct": round(ret, 2), "mdd": round(mdd, 2),
             "exposure": 0.0, "exp_cap": 5.6, "guard_armed": True, "last_brake": "없음",
             "dauto_ok": bool(stale <= 15.0), "dauto_stale_min": round(stale, 1),
             "live": bool(os.environ.get("RAUTO_LIVE") == "1"),
             "acct": {"balance": None, "spot": None, "fut_seed": None, "profit_gross": None, "trade_cost": None,
                      "profit_net": None, "withdraw": None, "seed_topup": None, "other_cost": None},
             "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "slots": [{"name": f"{SLOT}·{STRAT}", "side": ("S" if king.pos == -1 else "L" if king.pos == 1 else "-"),
                        "pnl": 0.0, "champ": CHAMP, "kind": "듀얼", "status": "보유" if king.pos != 0 else "대기", "open_et": (_fillms(king._h7[king.entry_i][0], king.entry_price) if (king.pos != 0 and 0 <= king.entry_i < len(king._h7) and not np.isnan(king.entry_price)) else None),
                        "entry": (round(float(king.entry_price), 2) if (king.pos != 0 and not np.isnan(king.entry_price)) else None), "trades": len(king._trades) + len(sw.trades), "bal": round(bal, 2),
                        "ret": round(ret, 1), "mdd": round(mdd, 1), "equity": equity, "eqt": eqt,
                        "reg": {"up": None, "down": None, "range": None}, "winrate": wr, "payoff": None,
                        "expect": None, "consec": 0, "pf": pf, "px": px, "trd": trd, "wk": wk}]}
    with open(OUT_STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    print(f"[state] {SLOT} state.json 작성 | champ={CHAMP}")


if __name__ == "__main__":
    main()
