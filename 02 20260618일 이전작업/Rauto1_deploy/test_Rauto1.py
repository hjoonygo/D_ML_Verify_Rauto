# -*- coding: utf-8 -*-
# [test_Rauto1.py] 슬롯1(R1) = TS-성급(인내심없는) 단독. C:\BinanceData 1m → 임패션트 TS → 페이퍼엔진.
#   ★슬롯=봇1개 컨벤션(C:\Rauto1..8). SW 없음, k 배분 없음(단독). state.json(대시보드 데이터원) 작성.
#   §8 엔진/봇 무수정 import. 진입 지정가 가정은 EXEC_PROFILE 문서(실행라우팅), 여기선 신호+페이퍼 P&L.
import os, sys, glob, json, traceback, datetime
import numpy as np, pandas as pd
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
BOTS = os.path.join(HERE, "bots")
if BOTS not in sys.path:
    sys.path.insert(0, BOTS)
import bot_trendstack_impatient as TBI
import trendstack_signal_engine as TE
import rauto_paper_engine as PE
from rauto_contract import MarketBar, Action
from oi_zscore_adapter import build_aux

DAUTO = os.environ.get("RAUTO_DAUTO_DIR", r"C:\BinanceData")
SLOT = "R1"; STRAT = "TS-성급"; BUCKET_7H = 420
OUT_TXT = os.path.join(HERE, "result.txt")
OUT_LED = os.path.join(HERE, "paper_ledger.csv")
OUT_STATE = os.path.join(HERE, "state.json")


def load_stream():
    files = sorted(glob.glob(os.path.join(DAUTO, "BTCUSDT_1m_*.csv")))
    if not files:
        raise FileNotFoundError(f"Dauto CSV 없음: {DAUTO}")
    dd = pd.concat([pd.read_csv(f, usecols=['ts_utc', 'open', 'high', 'low', 'close', 'volume']) for f in files])
    dd['ts_utc'] = pd.to_datetime(dd['ts_utc'])
    dd = dd.drop_duplicates('ts_utc').sort_values('ts_utc').reset_index(drop=True)
    n0 = len(dd); dd = dd.dropna(subset=['open', 'high', 'low', 'close'])
    return dd, n0 - len(dd)


def bkt7(ts):
    return int(pd.Timestamp(ts).value // 60_000_000_000) // BUCKET_7H


def main():
    lines = []
    def log(s): print(s); lines.append(s)

    dd, drop_n = load_stream()
    aux = build_aux(); aux['ts_utc'] = pd.to_datetime(aux['ts_utc'])
    dd = dd.merge(aux[['ts_utc', 'oi_zscore_24h']], on='ts_utc', how='left')
    n_z = int(np.isfinite(dd['oi_zscore_24h']).sum())
    log(f"[{SLOT}] {STRAT} 단독 | Dauto 1m {len(dd)}행({dd.ts_utc.iloc[0]}~{dd.ts_utc.iloc[-1]}) | OHLC결측 {drop_n} | oi_z 유한 {n_z}")

    bot = TBI.TrendStackImpatientBot(); bot.on_init({})
    acct = PE.PaperAccount()
    ledger = []; err = 0; exc = ""
    held = False; entry = 0.0; side = 0; prior_adv = 0.0; cur_adv = 0.0; cur_bkt = None
    prev_ts = None; gaps = 0
    try:
        for ts, o, h, l, c, v, oz in dd.itertuples(index=False):
            if prev_ts is not None and (ts - prev_ts) > pd.Timedelta(minutes=1):
                gaps += 1
            prev_ts = ts
            oz = float(oz) if oz == oz else float('nan')
            mb = MarketBar(ts=ts, o=o, h=h, l=l, c=c, v=v, aux={'oi_zscore': oz})
            sig = bot.on_bar(mb)
            if sig is not None and sig.action == Action.ENTER:
                acct.open(sig, ts=ts, price=c)            # 단독: k 배분 없음
                held = True; entry = c; side = sig.side.value
                prior_adv = 0.0; cur_adv = 0.0; cur_bkt = bkt7(ts)
                ext = l if side == 1 else h
                cur_adv = min(cur_adv, side * (ext - entry) / entry)
            elif sig is not None and sig.action == Action.EXIT and held:
                t = bot._trades[-1]
                final = side * (t['exit'] - entry) / entry
                exit_contrib = cur_adv if t['reason'] == 'trend_flip' else final
                mae = min(prior_adv, exit_contrib, final)
                bal0 = acct.bal
                p = acct.resolve_replay(R=t['R'], mae=mae, fund=t['fund'])
                held = False
                ledger.append(dict(bot=SLOT, entry_t=t['entry_t'], exit_t=ts, side=side,
                                   R=round(float(t['R']), 6), p=round(p or 0.0, 6),
                                   bal=round(acct.bal, 2), reason=t['reason']))
            elif held:
                b = bkt7(ts)
                if b != cur_bkt:
                    prior_adv = min(prior_adv, cur_adv); cur_adv = 0.0; cur_bkt = b
                ext = l if side == 1 else h
                cur_adv = min(cur_adv, side * (ext - entry) / entry)
    except Exception:
        err += 1; exc = traceback.format_exc()

    # 동치(live≡replay)
    match = None
    try:
        df7 = pd.DataFrame(bot._h7, columns=['ts', 'open', 'high', 'low', 'close', 'volume']).set_index('ts')
        fresh = TBI.TrendStackImpatientBot(); fresh.on_init({})
        rep = fresh.replay_7h(df7[['open', 'high', 'low', 'close']], np.array(bot._oiz, dtype=float), gate_mode='er', gate_er=0.45)
        key = lambda t: (t['entry_t'], t['exit_t'], t['side'], round(float(t['R']), 6))
        match = (len(rep) == len(bot._trades)) and all(key(a) == key(b) for a, b in zip(rep, bot._trades))
    except Exception:
        match = False

    pd.DataFrame(ledger).to_csv(OUT_LED, index=False, encoding='utf-8-sig')
    ret, mdd, cal = acct.metrics()
    n7 = len(bot._h7)
    log(f"[거래] {len(bot._trades)}건 | 잔고 ${acct.bal:,.2f} ({ret:+.2f}%/MDD {mdd:.2f}%) | 7h봉 {n7} | 갭 {gaps} | 예외 {err}")
    log(f"[동치] live≡replay: {match}")
    if err: log("\n[예외]\n" + exc)

    # ── Dauto 연계: 최근행 신선도(끊김 감지) ──
    last_data = pd.Timestamp(dd['ts_utc'].iloc[-1])
    now_naive = pd.Timestamp.utcnow().tz_localize(None) if pd.Timestamp.utcnow().tzinfo else pd.Timestamp.utcnow()
    stale_min = (now_naive - last_data).total_seconds() / 60.0
    dauto_ok = stale_min <= 15.0          # 15분 넘게 새 데이터 없으면 끊김 간주

    # ── state.json (대시보드 데이터원) ──
    open_now = (bot.pos != 0)
    last_close = float(dd['close'].iloc[-1])
    upnl = round(bot.pos * (last_close - bot.entry_price) / bot.entry_price * 100, 2) if (open_now and not np.isnan(bot.entry_price)) else 0.0
    sd = "L" if bot.pos == 1 else "S" if bot.pos == -1 else "-"
    state = {
        "balance": round(acct.bal, 2), "ret_pct": round(ret, 2), "mdd": round(mdd, 2),
        "exposure": 0.0, "exp_cap": 5.6, "guard_armed": True, "last_brake": "없음",
        "dauto_ok": bool(dauto_ok), "dauto_stale_min": round(stale_min, 1),
        "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "slots": [{"name": f"{SLOT}·{STRAT}", "side": sd, "pnl": upnl,
                   "status": "보유" if open_now else "대기",
                   "entry": round(float(bot.entry_price), 2) if open_now else None,
                   "trades": len(bot._trades), "bal": round(acct.bal, 2)}]
    }
    with open(OUT_STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    log(f"[state] {os.path.basename(OUT_STATE)} 작성 | 보유={open_now} side={sd} uPnL={upnl}%")

    ok = (err == 0) and (match in (True, None))
    verdict = (f"VERDICT {SLOT} {STRAT} 단독 | {'PASS' if ok else 'FAIL'} — 예외{err}·동치{match}·"
               f"거래{len(bot._trades)}·잔고${acct.bal:,.0f}({ret:+.1f}%/MDD{mdd:.1f}%) | state.json OK")
    log("\n" + verdict)
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
