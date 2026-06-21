# -*- coding: utf-8 -*-
# [pullback_quality_poc.py] 챗GPT5.5 '눌림목 품질(Order Flow)' 가설을 우리 데이터로 1차 검증.
#   질문: 성급왕(king) 668거래 중, 진입 시점의 OI변화·CVD·거래량수축 같은 '눌림 품질' 피처가
#         실제 거래 결과(R)를 가르는가? = 챗GPT의 PQS/Order Flow Score가 알파 단서가 되는가?
#   ★방법(§15 준수): 검증된 led36_king.csv(앵커 +11397%) 무수정 사용 + Merged_Data 피처를
#     진입결정시점(entry_t+420분, 봉마감)으로 asof 정렬(룩어헤드 없음). 봇 재구현 없음.
#   ★주의: 이건 IN-SAMPLE '조건부 결과' 스크리닝(피처가 결과와 관계있나)이지 검증된 전략 아님.
#     신호 발견 시 → 게이트/사이징으로 구현 후 CPCV 표준6 통과해야 '채택'(§5.6/5.7).
import os, sys
import numpy as np, pandas as pd
STG17 = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork"
LED = os.path.join(STG17, "led36_king.csv")
DATA = r"D:\ML\Verify\Merged_Data.csv"
TF = 420  # 7H

FCOLS = ['volume', 'taker_buy_volume', 'oi_change_5m_pct', 'oi_change_15m_pct',
         'oi_change_1h_pct', 'oi_zscore_24h', 'taker_imbalance_5m_avg',
         'oi_drop_after_spike', 'taker_flip_15m', 'top_retail_divergence']


def load():
    led = pd.read_csv(LED, parse_dates=['entry_t', 'exit_t'])
    led['entry_t'] = pd.to_datetime(led['entry_t'], utc=True).dt.tz_convert(None)
    use = ['timestamp'] + FCOLS
    df = pd.read_csv(DATA, usecols=lambda c: c in use)
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None)
    df = df.sort_values('timestamp').reset_index(drop=True).set_index('timestamp')
    # 파생: CVD(net taker = taker_buy - taker_sell), 거래량 수축
    df['net_taker'] = 2.0 * df['taker_buy_volume'] - df['volume']
    df['cvd_60m'] = df['net_taker'].rolling(60, min_periods=30).sum()
    df['cvd_7h'] = df['net_taker'].rolling(TF, min_periods=200).sum()
    df['vol_7h'] = df['volume'].rolling(TF, min_periods=200).sum()
    df['vol_base'] = df['vol_7h'].rolling(TF * 8, min_periods=TF).mean()
    df['vol_contraction'] = df['vol_7h'] / df['vol_base']  # <1 = 수축(거래량 줄어든 눌림)
    return led, df


FEATS = ['oi_change_5m_pct', 'oi_change_15m_pct', 'oi_change_1h_pct', 'oi_zscore_24h',
         'taker_imbalance_5m_avg', 'cvd_60m', 'cvd_7h', 'vol_contraction']


def main():
    led, df = load()
    # 진입 결정시점 = 봉마감 = entry_t + 420분 (label='left'이라 봉시작+TF가 마감)
    led['dt'] = led['entry_t'] + pd.Timedelta(minutes=TF)
    led = led.sort_values('dt').reset_index(drop=True)
    feat = df[FEATS].sort_index()
    led = pd.merge_asof(led, feat, left_on='dt', right_index=True, direction='backward')
    led['win'] = (led['R'] > 0).astype(int)
    n = len(led)
    print(f"trades {n} | feat 결측 점검: " + ", ".join(f"{f}:{int(led[f].isna().sum())}" for f in FEATS))

    def bucket_stats(sub):
        pv = sub['R'].values
        g = pv[pv > 0].sum(); b = -pv[pv < 0].sum()
        pf = g / b if b > 0 else float('inf')
        wr = (pv > 0).mean() * 100
        exp = pv.mean() * 100  # 기대값(거래당 R%)
        return len(pv), pf, wr, exp

    print("\n=== (1) IC: 진입시점 피처 vs 거래R (Spearman) — 전체/롱/숏 ===")
    print(f"{'feature':20s} {'IC_all':>8s} {'IC_long':>8s} {'IC_short':>8s}")
    ic_tab = []
    for f in FEATS:
        s = led.dropna(subset=[f])
        ic = s[f].corr(s['R'], method='spearman')
        il = s[s.side == 1][f].corr(s[s.side == 1]['R'], method='spearman')
        ish = s[s.side == -1][f].corr(s[s.side == -1]['R'], method='spearman')
        ic_tab.append((f, ic, il, ish))
        print(f"{f:20s} {ic:>+8.3f} {il:>+8.3f} {ish:>+8.3f}")

    print("\n=== (2) 핵심가설 검증: OI변화(1h) 3분위 → 기대값 ===")
    print("  챗GPT 주장: 진입 직전 OI 하락(롱/숏 약손 청산)=좋은 눌림 → 기대값↑ 이어야 함")
    for side_name, mask in [('전체', led['side'].notna()), ('롱', led.side == 1), ('숏', led.side == -1)]:
        sub = led[mask].dropna(subset=['oi_change_1h_pct'])
        if len(sub) < 30: continue
        sub = sub.copy()
        sub['q'] = pd.qcut(sub['oi_change_1h_pct'], 3, labels=['OI하락(Q1)', '중간(Q2)', 'OI상승(Q3)'])
        print(f"  [{side_name}] n={len(sub)}")
        for q in ['OI하락(Q1)', '중간(Q2)', 'OI상승(Q3)']:
            nn, pf, wr, exp = bucket_stats(sub[sub.q == q])
            print(f"     {q:12s} n={nn:3d} PF={pf:5.2f} 승률={wr:4.0f}% 기대값={exp:+.2f}%")

    print("\n=== (3) PQS-lite PoC: 신호 보이는 피처만 부호정렬 합산 → 3분위 기대값 ===")
    # 부호: 가설상 '좋은 눌림' 방향 = OI하락(-oi_change), 거래량수축(-vol_contraction 즉 낮을수록 좋음)
    #       cvd/ taker_imbalance는 데이터 IC 부호 따라 자동 정렬(in-sample이라 참고용).
    s = led.dropna(subset=['oi_change_1h_pct', 'vol_contraction']).copy()
    def z(x):
        x = (x - x.mean()) / (x.std() + 1e-9); return x.clip(-3, 3)
    # 가설 기반 고정부호 점수(데이터 스누핑 최소화): OI 적게/하락 + 거래량 수축
    s['pqs'] = (-z(s['oi_change_1h_pct'])) + (-z(s['vol_contraction']))
    s['q'] = pd.qcut(s['pqs'], 3, labels=['저PQS', '중PQS', '고PQS(좋은눌림)'])
    print("  PQS = (-OI변화1h z) + (-거래량수축 z)  [가설 고정부호, 데이터스누핑 회피]")
    for q in ['저PQS', '중PQS', '고PQS(좋은눌림)']:
        nn, pf, wr, exp = bucket_stats(s[s.q == q])
        print(f"     {q:16s} n={nn:3d} PF={pf:5.2f} 승률={wr:4.0f}% 기대값={exp:+.2f}%")
    base_n, base_pf, base_wr, base_exp = bucket_stats(led)
    print(f"\n  [기준=전체] n={base_n} PF={base_pf:.2f} 승률={base_wr:.0f}% 기대값={base_exp:+.2f}%")

    led.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "king_trades_pullback_feat.csv"),
               index=False, encoding="utf-8-sig")
    print("\n저장: king_trades_pullback_feat.csv")


if __name__ == "__main__":
    main()
