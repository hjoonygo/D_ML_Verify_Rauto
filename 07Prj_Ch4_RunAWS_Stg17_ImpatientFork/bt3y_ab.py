# -*- coding: utf-8 -*-
# [bt3y_ab.py] 3년(2023-05~2026-04) TS 단독 A/B: 기존(인내) vs 인내심없는(분기).
#   거래생성 = 검증된 replay_7h(동치True본) / 사이징 = 실 OPVnN(dev)+업트렌드숏컷(feat_struct_8) /
#   P&L = 검증된 rauto_paper_engine.resolve_replay(1m MAE·하드스탑·MMR·COST0.0014).
#   $10k 시작·lev22·k미적용(TS 단독, §9 +827~900% 대조검증용). 양 모델 동일 방식=공정 A/B.
#   [출력] ledger_base.csv / ledger_imp.csv / bt3y_summary.txt (00WorkHstr 아님, 본 폴더).
import os, sys, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); BOTS = os.path.join(HERE, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import trendstack_signal_engine as E
import trendstack_poc as P
import trendstack_regime as RG
import rauto_paper_engine as PE
from rauto_contract import Signal, Action, Side
from bot_trendstack_signal import TrendStackSignalBot
from bot_trendstack_impatient import TrendStackImpatientBot

DATA = r"D:\ML\Verify\Merged_Data.csv"
BASE_SIZE = 7.0864; LEV = 22.0; SH = 0.0; POC_LB = 60; POC_BINS = 50


def load():
    df = pd.read_csv(DATA, usecols=lambda c: c in
                     ('timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi_zscore_24h'))
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None)
    return df.set_index('timestamp')


def main():
    df = load()
    ohlc = df[['open', 'high', 'low', 'close']]
    df7 = E.resample_tf(ohlc, E.TF_MIN)
    vol7 = df['volume'].resample(f"{E.TF_MIN}min", label='left', closed='left').sum().reindex(df7.index).fillna(0.0)
    oi7 = df['oi_zscore_24h'].resample(f"{E.TF_MIN}min", label='left', closed='left').last().reindex(df7.index).values
    # POC/dev 재료(7h)
    h7 = df7['high'].values; l7 = df7['low'].values; c7 = df7['close'].values; mid7 = (h7 + l7) / 2.0
    atr7 = E.compute_atr(h7, l7, c7, E.ATR_PERIOD)
    poc7 = P.compute_poc(h7, l7, mid7, vol7.values, POC_LB, POC_BINS)
    # feat_struct_8 (4H, 1회 패스)
    df4 = E.resample_tf(ohlc, 240)
    try:
        _, featser = RG.feat_struct_of(df4, 8)
        featser.index = df4.index
    except Exception as e:
        print("[warn] feat_struct 실패 → 숏컷 미적용:", e); featser = pd.Series("range", index=df4.index)
    print(f"[7h] {len(df7)}봉 {df7.index.min()}~{df7.index.max()} | oi유효 {np.sum(~np.isnan(oi7))} | feat 4H {len(featser)}")

    # 1m을 MAE용으로 인덱싱
    m1 = df[['high', 'low']].copy()

    def run(bot, name):
        trades = bot.replay_7h(df7, oi7, gate_mode='er', gate_er=0.45)
        acct = PE.PaperAccount(start_balance=10000.0)
        t7 = df7.index.values
        rows = []
        for t in trades:
            et, xt, side = t['entry_t'], t['exit_t'], int(t['side'])
            bi = int(np.searchsorted(t7, np.datetime64(et)))
            dev, rdir = P.dev_rdir(t['entry'], poc7[bi], atr7[bi]) if (bi < len(poc7) and atr7[bi] > 0 and not np.isnan(poc7[bi])) else (np.nan, 0)
            mlt = bot.opvnn_mult(dev, rdir, side)
            feat = str(featser.asof(et)) if len(featser) else "range"
            cut = SH if (feat == "uptrend" and side == -1) else 1.0
            size = BASE_SIZE * mlt * cut
            # 1m MAE
            seg = m1.loc[et:xt]
            if len(seg):
                ext = seg['low'].values if side == 1 else seg['high'].values
                mae = float(np.min(side * (ext - t['entry']) / t['entry']))
            else:
                mae = 0.0
            sig = Signal(Action.ENTER, side=Side(side), size_pct=size, leverage=LEV)
            acct.open(sig, ts=et, price=t['entry'])
            p = acct.resolve_replay(R=t['R'], mae=mae, fund=t['fund'])
            rows.append(dict(entry_t=et, exit_t=xt, side=side, reason=t['reason'], year=t['year'],
                             feat=feat, dev=round(float(dev), 3) if not np.isnan(dev) else None,
                             opvnn_mult=mlt, size_pct=round(size, 4), exposure=round(size / 100 * LEV, 4),
                             R=round(float(t['R']), 6), mae=round(mae, 6), p=round(p or 0.0, 6),
                             bal=round(acct.bal, 2), liq=acct.trades[-1]['liq']))
        led = pd.DataFrame(rows)
        led.to_csv(os.path.join(HERE, f"ledger_{name}.csv"), index=False, encoding='utf-8-sig')
        ret, mdd, cal = acct.metrics()
        print(f"\n[{name}] 거래 {len(led)} | 잔고 ${acct.bal:,.0f} (수익 {ret:+.1f}%) | MDD {mdd:.2f}% | Calmar {cal:.1f} | 강제청산 {acct.n_liq}")
        return led, acct

    base_bot = TrendStackSignalBot(); base_bot.on_init({})
    imp_bot = TrendStackImpatientBot(); imp_bot.on_init({})
    lb, ab = run(base_bot, "base")
    li, ai = run(imp_bot, "imp")

    # ── 분해 요약 ──
    def pf(s):
        g = s[s > 0].sum(); b = -s[s < 0].sum()
        return (g / b) if b > 0 else float('inf')

    def breakdown(led, label):
        out = [f"\n===== [{label}] ====="]
        out.append(f"총거래 {len(led)} | 승률 {(led['p']>0).mean():.3f} | PF {pf(led['p']):.2f} | 최종잔고 ${10000*(1+led['p']).prod():,.0f}")
        # 롱숏
        for sd, nm in [(1, "LONG"), (-1, "SHORT")]:
            s = led[led['side'] == sd]
            if len(s):
                out.append(f"  {nm}: n{len(s)} 승률{(s['p']>0).mean():.3f} PF{pf(s['p']):.2f} 수익기여{(1+s['p']).prod()-1:+.2%}")
        # 연도
        for y in sorted(led['year'].unique()):
            s = led[led['year'] == y]
            out.append(f"  {y}: n{len(s)} 승률{(s['p']>0).mean():.3f} PF{pf(s['p']):.2f} 수익기여{(1+s['p']).prod()-1:+.2%}")
        # 장세(feat)
        for r in sorted(led['feat'].dropna().unique()):
            s = led[led['feat'] == r]
            out.append(f"  [{r}]: n{len(s)} 승률{(s['p']>0).mean():.3f} PF{pf(s['p']):.2f} 수익기여{(1+s['p']).prod()-1:+.2%}")
        return "\n".join(out)

    txt = []
    txt.append("3년 TS 단독 A/B (기존=인내 vs 인내심없는=분기) | $10k·lev22·k미적용 | replay_7h(동치)+실OPVnN+resolve_replay")
    rb, mb, cb = ab.metrics(); ri, mi, ci = ai.metrics()
    txt.append(f"기존  : 거래{len(lb)} 잔고${ab.bal:,.0f}({rb:+.1f}%) MDD{mb:.2f}% Calmar{cb:.1f} PF{pf(lb['p']):.2f} 청산{ab.n_liq}")
    txt.append(f"분기  : 거래{len(li)} 잔고${ai.bal:,.0f}({ri:+.1f}%) MDD{mi:.2f}% Calmar{ci:.1f} PF{pf(li['p']):.2f} 청산{ai.n_liq}")
    txt.append(f"§9대조: 기존이 +827~900% 근방이면 파이프라인 정상(절대일치 아님=재구성근사).")
    txt.append(breakdown(lb, "기존(인내)"))
    txt.append(breakdown(li, "분기(인내심없는)"))
    body = "\n".join(txt)
    print("\n" + body)
    with open(os.path.join(HERE, "bt3y_summary.txt"), "w", encoding="utf-8") as f:
        f.write(body + "\n")


if __name__ == "__main__":
    main()
