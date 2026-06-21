# [verify_fillbar.py] 결정판 체결현실성 검증 (캡틴 승인 2026-06-20).
#   §1·§15: 엔진/봇 무수정. LogMixin은 _step에서 '엔진이 청산검사에 쓴 그 봉의 OHLC'만 기록(읽기).
#   fill-bar: exit_px가 '엔진이 체결했다고 한 바로 그 봉' [low,high] 안에 있었나. 그리드 추론 0.
#     - sl_intrabar(king 1분가드): 1분봉(exit_t)
#     - sl/trend_flip(7H _step): 엔진 실제 7H봉(bot._bar[exit_t]=idx[i])
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); BOTS = os.path.join(HERE, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import bot_trendstack_impatient_king as TBK
from bot_trendstack_signal import TrendStackSignalBot
import bt36_ledgers as BT
from rauto_contract import MarketBar


class LogMixin:
    def on_init(self, ctx=None):
        super().on_init(ctx); self._bar = {}
    def _step(self, i, arr, sig, dz, eh):
        self._bar[pd.Timestamp(arr['idx'][i])] = (float(arr['l'][i]), float(arr['h'][i]))  # 엔진 실제 검사봉
        return super()._step(i, arr, sig, dz, eh)


class LogKing(LogMixin, TBK.TrendStackImpatientKingBot): pass
class LogImp(LogMixin, BT.PinnedImpatientBot): pass
class LogPatient(LogMixin, TrendStackSignalBot): pass


def run_bot(bot, dd):
    bot.on_init({})
    for ts, o, h, l, c, v, oz in dd[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi_zscore_24h']].itertuples(index=False):
        oz = float(oz) if oz == oz else float('nan')
        bot.on_bar(MarketBar(ts=ts, o=o, h=h, l=l, c=c, v=v, aux={'oi_zscore': oz}))
    return bot


def measure(bot, m1):
    nf = tot = 0; gaps = []
    for t in bot._trades:
        r = str(t['reason'])
        if 'sl' not in r: continue
        e = float(t['exit']); xt = pd.Timestamp(t['exit_t'])
        if 'intrabar' in r:
            if xt not in m1.index: continue
            lo, hi = m1.at[xt, 'low'], m1.at[xt, 'high']         # 1분봉
        else:
            if xt not in bot._bar: continue
            lo, hi = bot._bar[xt]                                # 엔진 실제 7H봉
        tot += 1
        if not (lo <= e <= hi):
            nf += 1; gaps.append(((lo - e) if e < lo else (e - hi)) / e * 1e4)
    return nf, tot, gaps


if __name__ == "__main__":
    dd = BT.load(); print(f"data {len(dd)}")
    m1 = dd.set_index('timestamp')[['low', 'high']]
    anchors = {"R2_king": "led36_king.csv", "R1_imp": "led36_imp_pinned.csv"}
    for nm, mk in [("patient", LogPatient), ("R2_king", LogKing), ("R1_imp", LogImp)]:
        bot = run_bot(mk(), dd)
        trades = pd.DataFrame(bot._trades)
        rsum = float(trades['R'].sum()); ntr = len(trades)
        eqs = ""
        if nm in anchors:
            ak = pd.read_csv(os.path.join(HERE, anchors[nm]))
            eqs = f" | 동치(vs {anchors[nm]}): n={ntr}=={len(ak)} Rdif={abs(rsum-ak['R'].sum()):.2e} {'OK' if (ntr==len(ak) and abs(rsum-ak['R'].sum())<1e-9) else 'FAIL'}"
        else:
            eqs = f" | (confirmed stg6=264건 대비 설정확인 필요)"
        nf, tot, gaps = measure(bot, m1)
        g = np.array(gaps) if gaps else np.array([0.0])
        print(f"\n[{nm}] {ntr}거래{eqs}")
        print(f"  ★엔진 실제봉 기준 체결봉밖(환상) = {nf}/{tot} = {nf/tot*100:.1f}%  평균갭{g.mean():.0f}bp 최대{g.max():.0f}bp")
