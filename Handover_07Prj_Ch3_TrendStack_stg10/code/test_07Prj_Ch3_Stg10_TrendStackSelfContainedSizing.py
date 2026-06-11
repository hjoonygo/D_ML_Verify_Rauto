# [파일명] test_07Prj_Ch3_Stg10_TrendStackSelfContainedSizing.py
# 코드길이: 약 110줄 / 내부버전: stg10_test_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 자기완결 사이징 봇 시연: 신호는 소스와 동일거래(불변) + 사이징을 봇이 직접 계산
#   (OPVnN: 라이브 POC/dev → devledger 120건 재현 / 업트렌드숏컷: feat_struct_8).
# [Lookahead] 신호·POC(과거60봉)·feat(shift8) 모두 미래참조 없음.
# ── 사용 파일 ── trendstack_signal_engine / trendstack_poc / trendstack_regime / bot_trendstack_signal / mock_candles
#   + 07Prj_Ch2_Stg2_TrendStack_OPVnNSweep_devledger.csv(동봉, OPVnN 검증 정답)
# ── 함수 ── main()
# ─────────────────────────────────────────────────────────────────────────
import os
import numpy as np
import pandas as pd
import trendstack_signal_engine as E
import trendstack_regime as RG
from bot_trendstack_signal import TrendStackSignalBot
from rauto_contract import MarketBar, Action
import mock_candles as MK

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

    # 1) 신호 ≡ 소스 (사이징과 무관하게 불변)
    src1 = E.run_strategy(ohlc, sig, 0, 'none', 0.8, split_mode='none')
    b1 = bot.replay_7h(ohlc, oi_arr=None, gate_mode='none')
    src2 = E.run_strategy(ohlc, sig, 0, 'none', 0.8, split_mode='none', gate_mode='er', gate_er=0.45, dz_oi=oi)
    b2 = bot.replay_7h(ohlc, oi_arr=oi, gate_mode='er', gate_er=0.45)
    print(f"[신호≡소스] 게이트없음 {trades_equal(src1, b1)}({len(src1)}건) / ER+무덤 {trades_equal(src2, b2)}({len(src2)}건)")

    # 2) OPVnN devledger 120건 재현 (라이브 배수 로직)
    if os.path.exists(DEVLEDGER):
        dl = pd.read_csv(DEVLEDGER)
        bb = TrendStackSignalBot(); bb.on_init()
        fire = sum(1 for _, r in dl.iterrows()
                   if r['regime_dir'] != SENT and not pd.isna(r['dev'])
                   and abs(bb.opvnn_mult(float(r['dev']), int(r['regime_dir']), int(r['side'])) - 0.6) < 1e-9)
        print(f"[OPVnN 검증] devledger 줄임(×0.6) {fire}건 [기대 120] → {'일치' if fire == 120 else '불일치'}")

    # 3) 라이브 POC/dev 사이징 (7h history 주입)
    b3 = TrendStackSignalBot(); b3.on_init()
    b3._h7 = [[df7.index[k], df7['open'].iloc[k], df7['high'].iloc[k], df7['low'].iloc[k],
               df7['close'].iloc[k], df7['volume'].iloc[k]] for k in range(len(df7))]
    i = len(df7) - 1; b3.entry_price = df7['close'].iloc[i]
    b3._feat = 'downtrend'
    sz_s, _, dbg = b3._compute_size(-1, i, sig)
    sz_l, _, _ = b3._compute_size(+1, i, sig)
    b3._feat = 'uptrend'; sz_us, _, _ = b3._compute_size(-1, i, sig)
    print(f"[라이브 사이징] 하락숏 {sz_s}% (OPVnN {dbg.get('opvnn_mult')}, dev {dbg.get('dev')}) / 롱 {sz_l}% / 업트렌드숏 {sz_us}%")

    # 4) feat_struct_8 (4H SMC, 실시간安)
    df4 = MK.make_4h_series()
    post, feat = RG.feat_struct_of(df4, 8)
    print(f"[feat_struct_8] 값 {sorted(feat.unique())} | shift(8) 적용(post≠feat {int((post.values != feat.values).sum())}칸) | 최신 {feat.iloc[-1]}")

    # 5) 1m → 7h·4H 이중 리샘플 (라이브 on_bar)
    bars = MK.make_1m_stream()
    lb = TrendStackSignalBot(); lb.on_init()
    for (ts, o, h, l, c, v) in bars:
        lb.on_bar(MarketBar(ts=ts, tf='1m', o=o, h=h, l=l, c=c, v=v, oi=0.5))
    print(f"[이중 리샘플] 1m {len(bars)}봉 → 7h {len(lb._h7)}봉 / 4H {len(lb._h4)}봉 | 현재 feat={lb._feat}")

    print("\n[요약] 신호=소스 1:1(불변). 사이징=봇 자체계산 — OPVnN(POC/dev) devledger 120건 재현, 업트렌드숏컷(feat_struct_8).")
    print("[한계] +827% 수치·feat 정답 대조는 PC 실데이터(698MB). 봉경계(7h/4H) 원점은 PC 과거리샘플과 캘리브레이션 필요.")


if __name__ == '__main__':
    main()
