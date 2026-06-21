# -*- coding: utf-8 -*-
# [bt36_ledgers.py] 정설(핀고정 on_bar) 36개월 ledger 생성 — 4봇 deliverable의 신뢰 원천.
#   성급=핀고정 래퍼(§1 래퍼, _bucket만 GRID_ANCHOR로 정렬), 성급왕=검증 king(이미 핀). 둘 다 봇 self-size(OPVnN).
#   거래별 size_pct·R·mae·fund·side·year·reason 저장 → 이후 k스케일/듀얼/연도/롱숏/슬리피지는 ledger에서 계산.
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); BOTS = os.path.join(HERE, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import bot_trendstack_impatient as TBI
import bot_trendstack_impatient_king as TBK
import rauto_paper_engine as PE
from bot_trendstack_signal import BUCKET_7H
from rauto_contract import MarketBar, Action
DATA = r"D:\ML\Verify\Merged_Data.csv"
GRID_ANCHOR = pd.Timestamp("2023-05-01 00:00:00")


class PinnedImpatientBot(TBI.TrendStackImpatientBot):   # 성급 + 7H 그리드 핀고정(king과 동일 정렬). 진입/사이징/손절 전부 부모 그대로.
    def _bucket(self, ts, width):
        if width == BUCKET_7H:
            return int((pd.Timestamp(ts).value - GRID_ANCHOR.value) // (width * 60_000_000_000))
        return super()._bucket(ts, width)


def bkt7(ts): return int(pd.Timestamp(ts).value // 60_000_000_000) // 420


def load():
    dd = pd.read_csv(DATA, usecols=lambda c: c in ('timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi_zscore_24h'))
    dd['timestamp'] = pd.to_datetime(dd['timestamp'], utc=True).dt.tz_convert(None)
    return dd.dropna(subset=['open', 'high', 'low', 'close']).sort_values('timestamp').reset_index(drop=True)


def run(make, dd):
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
            ec = cur if t['reason'] == 'trend_flip' else final
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


if __name__ == "__main__":
    dd = load(); print(f"data {len(dd)} {dd.timestamp.iloc[0]}~{dd.timestamp.iloc[-1]}")
    for nm, mk in [("imp_pinned", lambda: PinnedImpatientBot()), ("king", lambda: TBK.TrendStackImpatientKingBot())]:
        led = run(mk, dd)
        fp = os.path.join(HERE, f"led36_{nm}.csv"); led.to_csv(fp, index=False, encoding="utf-8-sig")
        # 빠른 확인용: k1.0 lev22 5bp 손익
        acct = PE.PaperAccount()
        from rauto_contract import Signal, Action as A, Side
        for _, r in led.iterrows():
            acct.open(Signal(A.ENTER, side=Side(int(r['side'])), size_pct=r['size_pct'], leverage=22.0), ts=None, price=100.0)
            R = r['R'] - (0.0005 if r['reason'] in ('sl', 'sl_intrabar') else 0.0)
            acct.resolve_replay(R=R, mae=r['mae'], fund=r['fund'])
        ret, mdd, _ = acct.metrics()
        print(f"[{nm}] {len(led)}거래 저장 → {os.path.basename(fp)} | k1.0 lev22 5bp: {ret:+.0f}%/MDD{mdd:.1f}%")
    print("DONE ledgers saved")
