# -*- coding: utf-8 -*-
# [rolling_edge.py] ★ChatGPT 토론 핵심전제 검증: "우리 봇의 엣지 E[R]이 실제로 붕괴(≤0)한 적이 있나?"
#   ChatGPT가 SPRT/CUSUM으로 '엣지붕괴'를 잡자는데 — 붕괴가 애초에 없으면 그 machinery 전체가 불필요(LSI 전철).
#   롤링 N거래 평균R + 부호, 연도별/장세별 E[R] 안정성. 검증 led36_king 무수정.
import os, sys
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
STG17 = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork"
BOTS = os.path.join(STG17, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import trendstack_signal_engine as E
HERE = os.path.dirname(os.path.abspath(__file__))
LED = os.path.join(STG17, "led36_king.csv")
DATA = r"D:\ML\Verify\Merged_Data.csv"


def main():
    led = pd.read_csv(LED, parse_dates=['entry_t', 'exit_t']).sort_values('entry_t').reset_index(drop=True)
    for c in ('entry_t', 'exit_t'): led[c] = pd.to_datetime(led[c], utc=True).dt.tz_convert(None)
    R = led['R'].values
    print(f"거래 {len(R)} | 전체 E[R] {R.mean()*100:+.3f}% (이게 양수=엣지존재)")

    # 롤링 E[R] (N=30, 50)
    print("\n=== 롤링 평균R 부호 (엣지붕괴=음수구간 존재 여부) ===")
    for N in (20, 30, 50):
        roll = pd.Series(R).rolling(N).mean().dropna().values
        neg = (roll <= 0).mean() * 100
        worst = roll.min() * 100
        print(f"  롤링{N}거래: 평균R 음수인 구간 {neg:.1f}% · 최저 평균R {worst:+.3f}% · (전체기간 {len(roll)}창)")

    # 연도별 E[R]
    print("\n=== 연도별 E[R] (엣지가 특정 연도에 죽나) ===")
    for y in (2023, 2024, 2025, 2026):
        sub = led[led['entry_t'].dt.year == y]['R'].values
        if len(sub): print(f"  {y}: E[R] {sub.mean()*100:+.3f}% · 거래 {len(sub)} · 승률 {(sub>0).mean()*100:.0f}%")

    # 장세별 E[R] (ER 기준)
    df = pd.read_csv(DATA, usecols=lambda c: c in ('timestamp', 'open', 'high', 'low', 'close'))
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None); df = df.set_index('timestamp')
    df7 = E.resample_tf(df, E.TF_MIN); er7 = pd.Series(E.compute_signals(df7)['er'], index=df7.index)
    led['er'] = led['entry_t'].map(lambda t: er7.asof(t))
    print("\n=== 장세(ER 3분위)별 E[R] ===")
    led['erq'] = pd.qcut(led['er'].fillna(led['er'].median()), 3, labels=['저ER(횡보)', '중', '고ER(추세)'])
    for q in ['저ER(횡보)', '중', '고ER(추세)']:
        sub = led[led['erq'] == q]['R'].values
        print(f"  {q}: E[R] {sub.mean()*100:+.3f}% · 거래 {len(sub)} · 승률 {(sub>0).mean()*100:.0f}%")

    # 그래프: 롤링30 E[R] 시계열 + 0선
    roll30 = pd.Series(R, index=led['exit_t']).rolling(30).mean()
    fig, ax = plt.subplots(figsize=(13, 5))
    ax.plot(roll30.index, roll30.values * 100, color='#1f77b4', lw=1.3)
    ax.axhline(0, color='red', ls='--', label='Edge collapse line (E[R]=0)')
    ax.axhline(R.mean() * 100, color='green', ls=':', label=f'overall +{R.mean()*100:.2f}%')
    ax.fill_between(roll30.index, roll30.values * 100, 0, where=(roll30.values <= 0), color='red', alpha=.3)
    ax.set_title('Rolling 30-trade E[R] over 36 months — does edge ever collapse below 0?')
    ax.set_ylabel('Rolling mean R %'); ax.legend(); ax.grid(alpha=.3)
    plt.tight_layout(); fp = os.path.join(HERE, "rolling_edge.png"); plt.savefig(fp, dpi=110)
    print(f"\n[그래프] {fp}")


if __name__ == "__main__":
    main()
