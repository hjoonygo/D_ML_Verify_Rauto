# -*- coding: utf-8 -*-
# [ab_local_replay.py] AWS 배포 전 로컬 사전검증 + 오프라인 A/B(기존=인내 vs 분기=인내심없는).
#   전체 7h 이력에서 두 봇을 같은 게이트(er0.45)·같은 노출로 replay_7h → 거래수·수익·MDD·진입타이밍 비교.
#   ※신호거래 R(lev=1) 기준의 1차 사전검증. 실 P&L(OPVnN·lev22·페이퍼엔진)은 배포 후 측정.
import os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BOTS = os.path.join(HERE, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import trendstack_signal_engine as E
from bot_trendstack_signal import TrendStackSignalBot
from bot_trendstack_impatient import TrendStackImpatientBot

DATA = r"D:\ML\Verify\Merged_Data.csv"
EXP = 1.559          # 베이스라인 확정 노출(비교용 동일 적용)
GATE_MODE = "er"; GATE_ER = 0.45


def mdd_ret(R, exp):
    if len(R) == 0: return 0.0, 0.0
    eq = np.cumprod(1.0 + np.asarray(R) * exp); pk = np.maximum.accumulate(eq)
    return float(((eq - pk) / pk).min()), float(eq[-1] - 1.0)


def summarize(name, trades):
    R = np.array([t['R'] for t in trades], float)
    bars = np.array([t['bars'] for t in trades], float)
    mdd, ret = mdd_ret(R, EXP)
    wr = float((R > 0).mean()) if len(R) else float('nan')
    flips = sum(1 for t in trades if t['reason'] == 'trend_flip')
    sls = sum(1 for t in trades if t['reason'] == 'sl')
    print(f"\n[{name}]")
    print(f"  거래수 {len(trades)} (sl {sls} / trend_flip {flips}) | 승률 {wr:.3f}")
    print(f"  sumR {R.sum():+.4f} meanR {R.mean() if len(R) else float('nan'):+.5f} | 보유봉 중앙 {np.median(bars) if len(bars) else float('nan'):.0f}")
    print(f"  EXP{EXP} 복리: 총수익 {ret*100:+.1f}% | MDD {mdd*100:.2f}%")
    return dict(n=len(trades), sl=sls, flip=flips, wr=wr, sumR=R.sum(),
                ret=ret, mdd=mdd, trades=trades)


def main():
    print("[ab_local_replay] 기존(인내) vs 분기(인내심없는) — 7h 오프라인 A/B")
    df = pd.read_csv(DATA, usecols=lambda c: c in
                     ('timestamp', 'open', 'high', 'low', 'close', 'oi_zscore_24h'))
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None); df = df.set_index('timestamp')
    df7 = E.resample_tf(df[['open', 'high', 'low', 'close']], E.TF_MIN)
    # oi z를 7h 종가에 정렬(마지막값)
    oiz = df['oi_zscore_24h'].resample(f"{E.TF_MIN}min", label='left', closed='left').last().reindex(df7.index).values
    print(f"[7h] {len(df7)}봉 | {df7.index.min()} ~ {df7.index.max()} | oi z 유효 {np.sum(~np.isnan(oiz))}/{len(oiz)}")

    base = TrendStackSignalBot(); base.on_init({})
    imp = TrendStackImpatientBot(); imp.on_init({})
    tb = base.replay_7h(df7, oi_arr=oiz, gate_mode=GATE_MODE, gate_er=GATE_ER)
    ti = imp.replay_7h(df7, oi_arr=oiz, gate_mode=GATE_MODE, gate_er=GATE_ER)

    sb = summarize("기존(인내=피벗대기)", tb)
    si = summarize("분기(인내심없는=즉시)", ti)

    print("\n" + "=" * 64)
    print("[A/B 요약]")
    print(f"  거래수 Δ = {si['n']-sb['n']:+d} (분기 {si['n']} vs 기존 {sb['n']})")
    print(f"  총수익 Δ = {(si['ret']-sb['ret'])*100:+.1f}%p (분기 {si['ret']*100:+.1f}% vs 기존 {sb['ret']*100:+.1f}%)")
    print(f"  MDD     = 분기 {si['mdd']*100:.2f}% vs 기존 {sb['mdd']*100:.2f}%  (-20% 절대선)")
    verdict = ("분기 우위(사전검증 PASS — 배포해 페이퍼 비교 가치)" if si['ret'] > sb['ret']
               else "분기 열위(오프라인상 '인내가 답' 신호 — 배포 전 캡틴 재검토 권고)")
    print(f"  판정(오프라인,참고): {verdict}")
    print(f"  ※절대선 점검: 분기 MDD {'위반!' if si['mdd'] < -0.20 else 'OK'} (-20%)")
    print("=" * 64)

    # 연도별 분해(장세 안정성)
    print("\n[연도별 총수익(EXP%s 복리)]" % EXP)
    for nm, tr in [("기존", tb), ("분기", ti)]:
        by = {}
        for t in tr:
            by.setdefault(t['year'], []).append(t['R'])
        cells = " ".join(f"{y}:{mdd_ret(by[y],EXP)[1]*100:+.0f}%(n{len(by[y])})" for y in sorted(by))
        print(f"  {nm}: {cells}")


if __name__ == "__main__":
    main()
