# [파일명] check_07Prj_Ch3_Stg9_TrendStackSignalBot.py
# 코드길이: 약 165줄 / 내부버전: stg9_check_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 진짜 TrendStack 신호봇을 11개 시나리오로 검증. 핵심: 봇 per-bar 상태머신이 소스
#        엔진(run_strategy)과 '동일 거래'(추정 0·1:1 이식). + 게이트/사이징/초기SL/리샘플/계약.
# [Lookahead] 신호는 진입봉까지 과거값.
# ── 사용 파일 ── trendstack_signal_engine / bot_trendstack_signal / rauto_contract / mock_candles
#  OUT(../00WorkHstr) <YYYYMMDDHHMM>.txt + 00WorkHstr_INDEX.txt(append)
# ── 함수 ── trades_equal / main(): 11 시나리오 PASS/FAIL + 기록
# ─────────────────────────────────────────────────────────────────────────
import os
from datetime import datetime
from collections import defaultdict
import numpy as np
import pandas as pd
import trendstack_signal_engine as E
from bot_trendstack_signal import TrendStackSignalBot
from rauto_contract import BotPlugin, MarketBar, Signal, Action, Side
import mock_candles as MK

BASE = "07Prj_Ch3_Stg9_TrendStackSignalBot"
OUT_DIR = os.path.join('..', '00WorkHstr')


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
    bot = TrendStackSignalBot(); bot.on_init()

    # S2 동일거래(게이트 없음)
    src1 = E.run_strategy(df, sig, 0, 'none', 0.8, split_mode='none')
    bot1 = bot.replay_7h(df, oi_arr=None, gate_mode='none')
    s2 = trades_equal(src1, bot1) and len(src1) > 0

    # S3 동일거래(ER게이트+무덤)
    src2 = E.run_strategy(df, sig, 0, 'none', 0.8, split_mode='none', gate_mode='er', gate_er=0.45, dz_oi=oi)
    bot2 = bot.replay_7h(df, oi_arr=oi, gate_mode='er', gate_er=0.45)
    s3 = trades_equal(src2, bot2)

    # S1 signal_engine 1:1 추출(함수·상수)
    s1 = (all(hasattr(E, f) for f in ('pivots_lr', 'pivot_supertrend', 'compute_signals',
                                      'compute_split_entry', 'run_strategy', 'short_blocked_combo'))
          and E.LEFT == 4 and E.RIGHT == 1 and E.ATR_FACTOR == 3.0 and E.SL_PCT == 1.0
          and E.FIB == (0.3, 0.5, 0.6) and (E.DZ_LO, E.DZ_HI) == (0.0, 1.0))

    # S4 게이트가 진입 실제 차단
    s4 = (len(src2) < len(src1))

    # S5 양방향 + 청산사유 ⊆ {sl, trend_flip}
    sides = set(t['side'] for t in src1); reasons = set(t['reason'] for t in src1)
    s5 = (sides == {1, -1} and reasons.issubset({'sl', 'trend_flip'}))

    # S6 초기 SL = 진입가 ±1% (진입봉까지 잘라 trailing 전 상태 확인)
    s6 = False
    if bot1:
        first = bot1[0]
        k = df.index.get_loc(first['entry_t'])
        b6 = TrendStackSignalBot(); b6.on_init()
        b6.replay_7h(df.iloc[:k + 1], oi_arr=None, gate_mode='none')
        if b6.pos != 0:
            d = b6.pos
            expect = b6.entry_price * (1 - d * E.SL_PCT / 100)
            s6 = abs(b6.sl - expect) < 1e-9

    # S7~S9 사이징
    bs = TrendStackSignalBot(); bs.on_init()
    s7 = (bs._compute_size(-1, regime='uptrend')[0] == 0.0)                       # 업트렌드 숏 컷
    s8 = (abs(bs._compute_size(-1, regime='range', dev=0.3, regime_dir=1)[0] - 7.0864 * 0.6) < 1e-9)  # OPVnN
    s9 = (abs(bs._compute_size(-1, regime='downtrend')[0] - 7.0864) < 1e-9)       # base

    # S10 1m→7h 리샘플 OHLC 정확
    bars, _ = MK.make_1m_stream()
    lb = TrendStackSignalBot(); lb.on_init()
    for (ts, o, h, l, c) in bars:
        lb.on_bar(MarketBar(ts=ts, tf='1m', o=o, h=h, l=l, c=c, oi=0.5))
    groups = defaultdict(list)
    for b in bars:
        groups[lb._bucket(b[0])].append(b)
    g = groups[sorted(groups)[0]]
    exp = (g[0][1], max(x[2] for x in g), min(x[3] for x in g), g[-1][4])
    s10 = (len(lb._h7) >= 1 and all(abs(a - b) < 1e-9 for a, b in zip(lb._h7[0][1:], exp)))

    # S11 BotPlugin 계약 준수 (on_bar는 Optional[Signal]: 7h 마감 전 None 정상, 마감 시 Signal)
    b11 = TrendStackSignalBot(); b11.on_init()
    r1 = b11.on_bar(MarketBar(ts=pd.Timestamp('2024-01-01 00:00'), o=1, h=1, l=1, c=1, oi=0.5))   # 첫 봉 → None
    r2 = b11.on_bar(MarketBar(ts=pd.Timestamp('2024-01-01 07:01'), o=1, h=1, l=1, c=1, oi=0.5))   # 7h 경계 → Signal
    s11 = (issubclass(TrendStackSignalBot, BotPlugin)
           and TrendStackSignalBot.META.get('name') == 'TrendStack'
           and TrendStackSignalBot.META.get('timeframe') == '7h'
           and callable(getattr(b11, 'on_fill', None))
           and r1 is None and isinstance(r2, Signal))

    checks = [
        ("S1 signal_engine 1:1 추출(함수·상수)", s1),
        ("S2 봇≡소스 동일거래(게이트 없음)", s2),
        ("S3 봇≡소스 동일거래(ER0.45+무덤[0,1))", s3),
        ("S4 OI무덤+ER게이트 진입 차단 동작", s4),
        ("S5 롱·숏 양방향 + 청산 ⊆ {sl,trend_flip}", s5),
        ("S6 초기 SL = 진입가 ±1%", s6),
        ("S7 사이징 업트렌드 숏컷 → 0", s7),
        ("S8 사이징 OPVnN → base×0.6", s8),
        ("S9 사이징 base(하락숏)", s9),
        ("S10 1m→7h 리샘플 OHLC 정확", s10),
        ("S11 BotPlugin 계약 준수", s11),
    ]
    n_pass = sum(1 for _, ok in checks if ok)
    all_ok = (n_pass == len(checks))

    print(f"=== {BASE} 검증 ({n_pass}/{len(checks)} PASS) ===")
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"동일거래: 게이트없음 소스{len(src1)}=봇{len(bot1)} / ER+무덤 소스{len(src2)}=봇{len(bot2)}")
    print(f"방향 {sorted(sides)} 청산 {sorted(reasons)} | 사이징 base 7.0864% × 22x, 업트렌드숏 0")
    print(f"종합: {'PASS ✅ 소스 1:1 동일거래 + 사이징/리샘플 검증. +827% 수치는 PC 실데이터 대조.' if all_ok else 'FAIL ⚠️ 미통과 확인'}")

    try:
        os.makedirs(OUT_DIR, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d%H%M')
        with open(os.path.join(OUT_DIR, f'{ts}.txt'), 'w', encoding='utf-8') as f:
            f.write(f"[{BASE}] 진짜 TrendStack 신호봇 검증 (소스 SpTrd_Fib_V1_Champion 1:1)\n")
            f.write(f"동일거래: 게이트없음 소스{len(src1)}=봇{len(bot1)} / ER+무덤 소스{len(src2)}=봇{len(bot2)}\n")
            f.write(f"방향 {sorted(sides)} 청산 {sorted(reasons)}\n\n")
            for name, ok in checks:
                f.write(f"  [{'PASS' if ok else 'FAIL'}] {name}\n")
            f.write(f"\n종합: {n_pass}/{len(checks)} {'PASS' if all_ok else 'FAIL'}\n")
            f.write("판정: 진입/청산 신호 코어는 소스와 동일거래, 사이징(업트렌드숏컷+OPVnN훅)은 봇 결정.\n")
            f.write("한계: +827% 복리 수치 재현은 PC 실데이터(Merged_Data_with_Regime_Features 698MB)로 대조 필요.\n")
        with open(os.path.join(OUT_DIR, '00WorkHstr_INDEX.txt'), 'a', encoding='utf-8') as f:
            f.write(f"{ts} | {BASE} | {n_pass}/{len(checks)} {'PASS' if all_ok else 'FAIL'} | "
                    f"신호코어=SpTrd_Fib_V1_Champion 1:1(동일거래 검증) · 사이징 업트렌드숏컷+OPVnN훅 · 1m→7h | "
                    f"+827%는 PC 실데이터 대조\n")
        print(f"[기록] ../00WorkHstr/{ts}.txt + INDEX append")
    except Exception as e:
        print(f"[기록 실패] {e}")


if __name__ == '__main__':
    main()
