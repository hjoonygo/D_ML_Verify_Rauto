# -*- coding: utf-8 -*-
# [reexec_champion_botrun.py] ★실제 king봇을 1m로 돌려 청산 '실체결'을 계측 (진짜 수익 상한).
#   bt36_ledgers.run()을 1:1 복제(§15-1 봇 무수정)하되, sl_intrabar 청산 순간의 '그 봉 o/h/l'과
#   봇이 기록한 exit(=self.sl)을 함께 포착 → 실체결을 봉 안 '가능한 최선가'로 교정(=관대=상한).
#     롱: real = min(sl, high)  (sl이 봉위로 갭이면 최선=high에 매도)  · clean이면 sl.
#     숏: real = max(sl, low)
#   원본 R(=sl 체결)과 실체결 R 둘 다 같은 PaperAccount로 복리 → 앵커(+11397%) 재현 + 진짜 대조.
#   ★관대(최선가)라 결과가 나빠도 하한은 더 나쁨. trend_flip(종가체결)·진입은 불변.
import os, sys
import numpy as np, pandas as pd
STG = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork"
HERE = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(STG, "bots"), STG):
    if p not in sys.path: sys.path.insert(0, p)
import bot_trendstack_impatient_king as TBK
import rauto_paper_engine as PE
from rauto_contract import MarketBar, Action, Signal, Action as A, Side
DATA = r"D:\ML\Verify\Merged_Data.csv"
LEV = 22.0


def _p(*a): print(*a, flush=True)


def load():
    dd = pd.read_csv(DATA, usecols=lambda c: c in ('timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi_zscore_24h'))
    dd['timestamp'] = pd.to_datetime(dd['timestamp'], utc=True).dt.tz_convert(None)
    return dd.dropna(subset=['open', 'high', 'low', 'close']).sort_values('timestamp').reset_index(drop=True)


def bkt7(ts): return int(pd.Timestamp(ts).value // 60_000_000_000) // 420


def run_instrumented(dd):
    bot = TBK.TrendStackImpatientKingBot(); bot.on_init({})
    led = []; held = False; entry = 0.0; side = 0; prior = 0.0; cur = 0.0; cbkt = None; cur_size = 0.0
    ntr = 0
    for ts, o, h, l, c, v, oz in dd[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi_zscore_24h']].itertuples(index=False):
        oz = float(oz) if oz == oz else float('nan')
        sig = bot.on_bar(MarketBar(ts=ts, o=o, h=h, l=l, c=c, v=v, aux={'oi_zscore': oz}))
        if sig is not None and sig.action == Action.ENTER:
            held = True; entry = c; side = sig.side.value; prior = 0.0; cur = 0.0; cbkt = bkt7(ts)
            cur_size = float(sig.size_pct)
            ext = l if side == 1 else h; cur = min(cur, side * (ext - entry) / entry)
        elif sig is not None and sig.action == Action.EXIT and held:
            t = bot._trades[-1]
            sl = float(t['exit']); reason = t['reason']
            # ★실체결: 청산 '그 봉'(o,h,l)에서 가능한 최선가 (sl이 봉밖 갭이면 최선가로 교정)
            if reason == 'sl_intrabar':
                if side == 1:
                    real = sl if (l <= sl <= h) else (h if sl > h else l)   # 롱매도 최선
                else:
                    real = sl if (l <= sl <= h) else (l if sl < l else h)   # 숏매수 최선
            else:
                real = sl   # trend_flip 등 종가체결=real
            final = side * (sl - entry) / entry
            final_r = side * (real - entry) / entry
            ec = cur if reason == 'trend_flip' else final
            ec_r = cur if reason == 'trend_flip' else final_r
            mae = min(prior, ec, final); mae_r = min(prior, ec_r, final_r)
            R_orig = float(t['R'])
            R_real = R_orig + side * (real - sl) / entry * LEV
            led.append(dict(exit_t=pd.Timestamp(ts), side=side, entry_px=entry, sl_px=sl, real_px=real,
                            o=o, h=h, l=l, sl_in_bar=bool(l <= sl <= h), reason=reason,
                            R=R_orig, R_real=R_real, mae=mae, mae_real=mae_r, size_pct=cur_size,
                            fund=float(t.get('fund', 0.0)), year=pd.Timestamp(t['entry_t']).year))
            held = False; ntr += 1
        elif held:
            b = bkt7(ts)
            if b != cbkt: prior = min(prior, cur); cur = 0.0; cbkt = b
            ext = l if side == 1 else h; cur = min(cur, side * (ext - entry) / entry)
    return pd.DataFrame(led)


def runbt(L, rcol, maecol):
    acct = PE.PaperAccount()
    for _, r in L.iterrows():
        acct.open(Signal(A.ENTER, side=Side(int(r.side)), size_pct=r.size_pct, leverage=LEV), ts=None, price=100.0)
        R = r[rcol] - (0.0005 if r.reason in ('sl', 'sl_intrabar') else 0.0)
        acct.resolve_replay(R=R, mae=r[maecol], fund=r.fund)
    ret, mdd, _ = acct.metrics()
    return ret, mdd


def main():
    dd = load(); _p(f"data {len(dd)} {dd.timestamp.iloc[0]}~{dd.timestamp.iloc[-1]}")
    L = run_instrumented(dd)
    sli = L[L.reason == 'sl_intrabar']
    _p("=" * 80)
    _p("챔피언 R2 성급왕 — 실제 봇 1m 재실행 + 청산 실체결 계측 (관대=상한)")
    _p("=" * 80)
    _p(f"거래 {len(L)} | sl_intrabar {len(sli)} | trend_flip {len(L[L.reason=='trend_flip'])}")
    _p(f"청산봉서 sl 실존(clean): {int(sli.sl_in_bar.sum())}/{len(sli)} = {100*sli.sl_in_bar.mean():.0f}%")
    gap = sli[~sli.sl_in_bar]
    deg = gap.apply(lambda r: r.side * (r.real_px - r.sl_px) / r.entry_px, axis=1)
    _p(f"갭(sl 봉밖): {len(gap)}건 | 실체결열화(가격%): 중앙{deg.median()*100:.2f}% 평균{deg.mean()*100:.2f}% 최악{deg.min()*100:.2f}%")
    o_ret, o_mdd = runbt(L, 'R', 'mae')
    r_ret, r_mdd = runbt(L, 'R_real', 'mae_real')
    _p("-" * 80)
    _p(f"[원본 앵커] sl체결:      {o_ret:+.0f}% / MDD {o_mdd:.1f}%   (≈+11397% 재현이면 하니스 OK)")
    _p(f"[1m 실체결] 관대(최선가): {r_ret:+.0f}% / MDD {r_mdd:.1f}%   ← 진짜 상한")
    _p("-" * 80)
    for y in sorted(L.year.unique()):
        s = L[L.year == y]
        _p(f"  {int(y)}: R합 {s.R.sum():+.2f} → {s.R_real.sum():+.2f} ({len(s)}거래)")
    L.to_csv(os.path.join(HERE, "champion_botrun_reexec.csv"), index=False, encoding="utf-8-sig")
    _p(f"\n[저장] champion_botrun_reexec.csv")
    _p("[정직] 관대(봉내 최선가)=상한. 실제는 더 나쁠 수(틱). 진입·trend_flip 불변. 5bp 스톱슬립 유지.")


if __name__ == "__main__":
    main()
