# [파일명] check_07Prj_Ch3_Stg10_TrendStackSelfContainedSizing.py
# 코드길이: 약 175줄 / 내부버전: stg10_check_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 자기완결 사이징 봇 11 시나리오 검증. 핵심: 신호≡소스(불변) + OPVnN이 라이브 POC/dev로
#        devledger 120건 발동 재현 + 업트렌드숏컷(feat_struct_8) + 이중 리샘플 + 계약.
# [Lookahead] 신호·POC(과거60봉)·feat(shift8) 미래참조 없음.
# ── 사용 파일 ── trendstack_signal_engine / trendstack_poc / trendstack_regime / bot_trendstack_signal / mock_candles
#   + 07Prj_Ch2_Stg2_TrendStack_OPVnNSweep_devledger.csv(동봉)  / OUT(../00WorkHstr) <ts>.txt + INDEX
# ── 함수 ── trades_equal / main()
# ─────────────────────────────────────────────────────────────────────────
import os
from datetime import datetime
from collections import defaultdict
import numpy as np
import pandas as pd
import trendstack_signal_engine as E
import trendstack_poc as P
import trendstack_regime as RG
from bot_trendstack_signal import TrendStackSignalBot
from rauto_contract import BotPlugin, MarketBar, Signal, Action, Side
import mock_candles as MK

BASE = "07Prj_Ch3_Stg10_TrendStackSelfContainedSizing"
OUT_DIR = os.path.join('..', '00WorkHstr')
DEVLEDGER = "07Prj_Ch2_Stg2_TrendStack_OPVnNSweep_devledger.csv"
SENT = -9223372036854775808


def trades_equal(a, b):
    if len(a) != len(b):
        return False
    return all(x['entry_t'] == y['entry_t'] and x['exit_t'] == y['exit_t'] and x['side'] == y['side']
               and x['reason'] == y['reason'] and abs(x['R'] - y['R']) < 1e-12 for x, y in zip(a, b))


def main():
    df7, oi = MK.make_7h_series()
    ohlc = df7[['open', 'high', 'low', 'close']]
    sig = E.compute_signals(ohlc)
    bot = TrendStackSignalBot(); bot.on_init()

    # S2/S3 신호 ≡ 소스
    src1 = E.run_strategy(ohlc, sig, 0, 'none', 0.8, split_mode='none')
    b1 = bot.replay_7h(ohlc, oi_arr=None, gate_mode='none')
    s2 = trades_equal(src1, b1) and len(src1) > 0
    src2 = E.run_strategy(ohlc, sig, 0, 'none', 0.8, split_mode='none', gate_mode='er', gate_er=0.45, dz_oi=oi)
    b2 = bot.replay_7h(ohlc, oi_arr=oi, gate_mode='er', gate_er=0.45)
    s3 = trades_equal(src2, b2)

    # S1 3엔진 추출(함수·상수)
    s1 = (all(hasattr(E, f) for f in ('pivot_supertrend', 'compute_signals', 'run_strategy'))
          and hasattr(P, 'compute_poc') and P.POC_LB == 60 and P.POC_BINS == 50
          and all(hasattr(RG, f) for f in ('smc_structure', 'feat_struct_of')) and RG.SWING_LENS == [5, 8, 12])

    # S4 OPVnN devledger 120건 재현 (★핵심)
    fire = None
    if os.path.exists(DEVLEDGER):
        dl = pd.read_csv(DEVLEDGER)
        bb = TrendStackSignalBot(); bb.on_init()
        fire = sum(1 for _, r in dl.iterrows()
                   if r['regime_dir'] != SENT and not pd.isna(r['dev'])
                   and abs(bb.opvnn_mult(float(r['dev']), int(r['regime_dir']), int(r['side'])) - 0.6) < 1e-9)
    s4 = (fire == 120)

    # S5~S7 라이브 사이징 (7h history 주입)
    b3 = TrendStackSignalBot(); b3.on_init()
    b3._h7 = [[df7.index[k], df7['open'].iloc[k], df7['high'].iloc[k], df7['low'].iloc[k],
               df7['close'].iloc[k], df7['volume'].iloc[k]] for k in range(len(df7))]
    i = len(df7) - 1; b3.entry_price = df7['close'].iloc[i]
    b3._feat = 'downtrend'
    sz_s, _, dbg = b3._compute_size(-1, i, sig)         # OPVnN 역회귀 발동(이 봉 dev<0,rdir=+1,숏=−1 → ×0.6)
    sz_l, _, _ = b3._compute_size(+1, i, sig)           # 동일방향 → ×N(1.0)=base
    b3._feat = 'uptrend'; sz_us, _, _ = b3._compute_size(-1, i, sig)
    s5 = (abs(dbg.get('opvnn_mult', 0) - 0.6) < 1e-9 and abs(sz_s - 7.0864 * 0.6) < 1e-6)
    s6 = (sz_us == 0.0)
    s7 = (abs(sz_l - 7.0864) < 1e-6)

    # S8 feat_struct_8: 3상태 + shift(실시간安)
    df4 = MK.make_4h_series()
    post, feat = RG.feat_struct_of(df4, 8)
    s8 = (set(feat.unique()).issubset({'uptrend', 'downtrend', 'range'})
          and int((post.values != feat.values).sum()) > 0)

    # S9 1m → 7h·4H 이중 리샘플
    bars = MK.make_1m_stream()
    lb = TrendStackSignalBot(); lb.on_init()
    for (ts, o, h, l, c, v) in bars:
        lb.on_bar(MarketBar(ts=ts, tf='1m', o=o, h=h, l=l, c=c, v=v, oi=0.5))
    s9 = (len(lb._h7) >= 1 and len(lb._h4) >= 1)

    # S10 BotPlugin 계약 (on_bar Optional[Signal])
    b10 = TrendStackSignalBot(); b10.on_init()
    r1 = b10.on_bar(MarketBar(ts=pd.Timestamp('2024-01-01 00:00'), o=1, h=1, l=1, c=1, v=1, oi=0.5))
    r2 = b10.on_bar(MarketBar(ts=pd.Timestamp('2024-01-01 07:01'), o=1, h=1, l=1, c=1, v=1, oi=0.5))
    s10 = (issubclass(TrendStackSignalBot, BotPlugin) and TrendStackSignalBot.META.get('name') == 'TrendStack'
           and r1 is None and isinstance(r2, Signal))

    # S11 POC 미래참조 없음(과거60봉만): 코드 동작 — 앞 60봉 NaN, 이후 값
    h = df7['high'].values; l = df7['low'].values; m = (h + l) / 2; v = df7['volume'].values
    poc = P.compute_poc(h, l, m, v, P.POC_LB, P.POC_BINS)
    s11 = (np.isnan(poc[:P.POC_LB]).all() and (~np.isnan(poc[P.POC_LB:])).any())

    checks = [
        ("S1 3엔진 추출(신호·POC·regime 함수·상수)", s1),
        ("S2 신호≡소스 동일거래(게이트 없음)", s2),
        ("S3 신호≡소스 동일거래(ER0.45+무덤)", s3),
        ("S4 OPVnN 라이브배수 devledger 120건 재현", s4),
        ("S5 OPVnN 역회귀 발동 → ×0.6(하락숏)", s5),
        ("S6 업트렌드 숏컷 → size 0", s6),
        ("S7 동일방향 → ×N(1.0)=base(롱)", s7),
        ("S8 feat_struct_8 3상태 + shift(실시간安)", s8),
        ("S9 1m→7h·4H 이중 리샘플", s9),
        ("S10 BotPlugin 계약 준수", s10),
        ("S11 POC 과거60봉만(미래참조 없음)", s11),
    ]
    n_pass = sum(1 for _, ok in checks if ok)
    all_ok = (n_pass == len(checks))

    print(f"=== {BASE} 검증 ({n_pass}/{len(checks)} PASS) ===")
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"신호: no-gate 소스{len(src1)}=봇{len(b1)} / ER+무덤 소스{len(src2)}=봇{len(b2)} (동일거래)")
    print(f"OPVnN devledger 줄임 {fire}건 / 라이브 하락숏 {sz_s}% 롱 {sz_l}% 업트렌드숏 {sz_us}%")
    print(f"종합: {'PASS ✅ 신호=소스 + 사이징 자기완결(OPVnN 120건 재현·feat_struct8). +827%·feat정답은 PC.' if all_ok else 'FAIL ⚠️ 확인'}")

    try:
        os.makedirs(OUT_DIR, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d%H%M')
        with open(os.path.join(OUT_DIR, f'{ts}.txt'), 'w', encoding='utf-8') as f:
            f.write(f"[{BASE}] 자기완결 사이징 봇 검증\n")
            f.write(f"신호=SpTrd_Fib_V1_Champion 1:1(동일거래). 사이징=봇 자체계산.\n")
            f.write(f"OPVnN(POC/dev) devledger 줄임 {fire}건[기대120] / feat_struct_8(SMC swing8 shift8).\n\n")
            for name, ok in checks:
                f.write(f"  [{'PASS' if ok else 'FAIL'}] {name}\n")
            f.write(f"\n종합: {n_pass}/{len(checks)} {'PASS' if all_ok else 'FAIL'}\n")
            f.write("한계: +827% 수치·feat 정답 대조는 PC 실데이터(698MB). 봉경계(7h/4H) 원점 PC 캘리브레이션 필요.\n")
        with open(os.path.join(OUT_DIR, '00WorkHstr_INDEX.txt'), 'a', encoding='utf-8') as f:
            f.write(f"{ts} | {BASE} | {n_pass}/{len(checks)} {'PASS' if all_ok else 'FAIL'} | "
                    f"신호=소스1:1 동일거래 · 사이징 자기완결: OPVnN(POC60봉/dev) devledger120건재현 + 업트렌드숏컷(feat_struct8 SMC swing8) · 7h+4H 이중리샘플 | "
                    f"+827%·feat정답 PC\n")
        print(f"[기록] ../00WorkHstr/{ts}.txt + INDEX append")
    except Exception as e:
        print(f"[기록 실패] {e}")


if __name__ == '__main__':
    main()
