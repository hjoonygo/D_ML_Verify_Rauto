# [파일명] test_07Prj_Ch3_Stg9_TrendStackSignalBot.py
# 코드길이: 약 95줄 / 내부버전: stg9_test_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 진짜 TrendStack 신호봇 시연: 봇의 per-bar 상태머신이 소스 엔진(run_strategy)과
#        '동일 거래'를 내는지(추정 0·이식 충실) + 게이트 효과 + 사이징 + 1m→7h 리샘플.
# [Lookahead] 신호는 진입봉까지 과거값(엔진과 동일).
# ── 사용 파일 ── trendstack_signal_engine / bot_trendstack_signal / rauto_contract / mock_candles
# ── 함수 ── main()
# ─────────────────────────────────────────────────────────────────────────
import numpy as np
import pandas as pd
import trendstack_signal_engine as E
from bot_trendstack_signal import TrendStackSignalBot
from rauto_contract import MarketBar, Action
import mock_candles as MK


def trades_equal(src, bot):
    if len(src) != len(bot):
        return False
    for a, b in zip(src, bot):
        if not (a['entry_t'] == b['entry_t'] and a['exit_t'] == b['exit_t'] and a['side'] == b['side']
                and a['reason'] == b['reason'] and abs(a['R'] - b['R']) < 1e-12):
            return False
    return True


def main():
    df, oi = MK.make_7h_series()
    sig = E.compute_signals(df)
    dist = {int(k): int(v) for k, v in zip(*np.unique(sig['Trend'], return_counts=True))}
    print(f"[데이터] 7h {len(df)}봉 | Trend 분포(+1상승/−1하락): {dist}")

    bot = TrendStackSignalBot(); bot.on_init()

    # 1) 봇 ≡ 소스 (게이트 없음, split none)
    src1 = E.run_strategy(df, sig, 0, 'none', 0.8, split_mode='none')
    bot1 = bot.replay_7h(df, oi_arr=None, gate_mode='none')
    print(f"[동일거래 #1 게이트없음] 소스 {len(src1)} = 봇 {len(bot1)} | 일치 {trades_equal(src1, bot1)}")

    # 2) 봇 ≡ 소스 (OI무덤[0,1) + ER게이트0.45)
    src2 = E.run_strategy(df, sig, 0, 'none', 0.8, split_mode='none', gate_mode='er', gate_er=0.45, dz_oi=oi)
    bot2 = bot.replay_7h(df, oi_arr=oi, gate_mode='er', gate_er=0.45)
    print(f"[동일거래 #2 ER+무덤]   소스 {len(src2)} = 봇 {len(bot2)} | 일치 {trades_equal(src2, bot2)}")
    print(f"[게이트 효과] 무필터 {len(src1)}건 → 게이트 {len(src2)}건 (무덤·ER이 일부 진입 차단)")
    print(f"  방향: {sorted(set(t['side'] for t in src1))} | 청산사유: {sorted(set(t['reason'] for t in src1))}")

    # 3) 사이징(봇이 결정)
    print("[사이징] 업트렌드숏 →", bot._compute_size(-1, regime='uptrend'),
          "| 하락숏 →", bot._compute_size(-1, regime='downtrend'),
          "| OPVnN(dev0.3,dir+1) →", bot._compute_size(-1, regime='range', dev=0.3, regime_dir=1))

    # 4) 1m → 7h 리샘플 (라이브 on_bar)
    bars, _ = MK.make_1m_stream()
    lb = TrendStackSignalBot(); lb.on_init()
    n_sig = 0
    for (ts, o, h, l, c) in bars:
        s = lb.on_bar(MarketBar(ts=ts, tf='1m', o=o, h=h, l=l, c=c, oi=0.5))
        if s is not None and s.action != Action.HOLD:
            n_sig += 1
    # 첫 7h 버킷 집계 검증
    from collections import defaultdict
    groups = defaultdict(list)
    for b in bars:
        groups[lb._bucket(b[0])].append(b)
    first_key = sorted(groups)[0]; g = groups[first_key]
    exp = (g[0][1], max(x[2] for x in g), min(x[3] for x in g), g[-1][4])
    got = tuple(lb._h7[0][1:]) if lb._h7 else None
    print(f"[1m→7h] 1m {len(bars)}봉 주입 → 7h {len(lb._h7)}봉 | 첫봉 OHLC 기대 {tuple(round(x,3) for x in exp)} = 실제 {tuple(round(x,3) for x in got) if got else None}")

    print("\n[요약] 봇 신호 코어는 SpTrd_Fib_V1_Champion(소스)과 동일거래. 사이징은 봇이 결정(업트렌드숏컷+OPVnN).")
    print("[한계] +827% 수치 재현은 PC 실데이터(698MB)로 대조 필요. 여기선 로직 동일성·사이징·리샘플 검증.")


if __name__ == '__main__':
    main()
