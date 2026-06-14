# -*- coding: utf-8 -*-
# [파일명] scan_lead_indicators.py — 04 IDEA4Concept: BTC 선행지표 후보 로컬 실측 스캔
# 코드길이: 약 175줄 | 내부버전: idea_leadscan_v1 (2026-06-12)
# [목적] 딥리서치(2026-06-12, 104에이전트)가 추린 '로컬 검증 가능' 후보 3축을
#   36개월 실데이터($ 아님 — 수익률/확률 측정)로 단계 검증:
#   A. 펀딩비 극단 → 이후 1d/3d/7d 수익률 (문헌: '극단 펀딩이 가격 선행' 주장은 반증 0-3)
#   B. OI z-score 극단 → 이후 3d/7d 수익률 + 3d 최대낙폭(폭락 선행성)
#   C. 파이사이클(111DMA vs 2x350DMA) — 기술적 계열 대표를 보유 구간에서 점검
# [데이터] Merged_Data.csv(1m, 2023-05~2026-04) + BTCUSDT_funding_history_8h.csv(3,288건)
# [Out] lead_scan_report.txt / tbl_*.csv / fig_*.png (전부 영문 라벨)
# ==============================================================================
import os, sys
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
UP = os.path.dirname(HERE)
OUT = lambda n: os.path.join(HERE, n)
lines = []
def log(s):
    print(s); lines.append(s)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ── 데이터 ──
df = pd.read_csv(os.path.join(UP, "Merged_Data.csv"),
                 usecols=['timestamp', 'close', 'oi_zscore_24h'],
                 index_col='timestamp', parse_dates=True).sort_index()
df.index = df.index.tz_localize(None)
px_h = df['close'].resample('1h').last().dropna()          # 시간봉 종가
px_d = df['close'].resample('1D').last().dropna()          # 일봉 종가
log(f"[데이터] 1m {len(df):,}행({df.index.min().date()}~{df.index.max().date()}) | 1h {len(px_h)} | 1D {len(px_d)}")

def fwd_ret(px, hours):
    return px.shift(-hours) / px - 1.0

# ══ A. 펀딩비 ══════════════════════════════════════════════════════════════
fu = pd.read_csv(os.path.join(UP, "BTCUSDT_funding_history_8h.csv"),
                 usecols=['fundingTime', 'fundingRate'])
fu['fundingTime'] = pd.to_datetime(fu['fundingTime'], utc=True, format='mixed')
fu['ts'] = fu['fundingTime'].dt.tz_localize(None).dt.floor('h')
fu = fu.set_index('ts')['fundingRate'].astype(float)
A = pd.DataFrame({'fr': fu})
for h, tag in [(24, '1d'), (72, '3d'), (168, '7d')]:
    A[f'r{tag}'] = fwd_ret(px_h, h).reindex(A.index)
A = A.dropna()
q = A['fr'].rank(pct=True)
A['bucket'] = np.select([q <= .05, q <= .25, q <= .75, q <= .95],
                        ['p0-5(extreme neg)', 'p5-25', 'p25-75(mid)', 'p75-95'], 'p95-100(extreme pos)')
order = ['p0-5(extreme neg)', 'p5-25', 'p25-75(mid)', 'p75-95', 'p95-100(extreme pos)']
ta = A.groupby('bucket')[['r1d', 'r3d', 'r7d']].agg(['mean', 'median', 'count']).reindex(order)
ta.columns = ['_'.join(c) for c in ta.columns]
(ta * 1).round(5).to_csv(OUT("tbl_A_funding_buckets.csv"), encoding='utf-8-sig')
log("\n[A 펀딩비 분위수 → 이후 수익률 평균%] (n=" + str(len(A)) + ")")
for b in order:
    r = ta.loc[b]
    log(f"  {b:>22}: 1d {r['r1d_mean']*100:+.2f}% | 3d {r['r3d_mean']*100:+.2f}% | 7d {r['r7d_mean']*100:+.2f}% (n={int(r['r1d_count'])})")
base3 = A['r3d'].mean() * 100
sep_a = abs(ta.loc[order[0], 'r3d_mean'] - ta.loc[order[-1], 'r3d_mean']) * 100
log(f"  → 전체 3d 평균 {base3:+.2f}% | 양극단 3d 격차 {sep_a:.2f}%p")

fig, ax = plt.subplots(figsize=(9, 4.2))
x = np.arange(len(order)); w = 0.27
for i, (c, lab) in enumerate([('r1d', 'fwd 1d'), ('r3d', 'fwd 3d'), ('r7d', 'fwd 7d')]):
    ax.bar(x + (i - 1) * w, ta[f'{c}_mean'] * 100, w, label=lab)
ax.axhline(0, color='k', lw=.8); ax.set_xticks(x); ax.set_xticklabels(order, fontsize=7)
ax.set_ylabel('mean forward return %'); ax.set_title('A. Funding-rate percentile buckets vs forward BTC returns (2023-05~2026-04)')
ax.legend(); ax.grid(alpha=.3); plt.tight_layout(); plt.savefig(OUT("fig_A_funding.png"), dpi=110); plt.close()

# ══ B. OI z-score ═════════════════════════════════════════════════════════
oz_h = df['oi_zscore_24h'].resample('1h').last()
B = pd.DataFrame({'z': oz_h})
B['r3d'] = fwd_ret(px_h, 72); B['r7d'] = fwd_ret(px_h, 168)
lo3 = px_h.rolling(72).min().shift(-72)                     # 이후 3d 최저가
B['dd3d'] = lo3 / px_h - 1.0                                # 이후 3d 최대낙폭
B = B.dropna()
bins = [-np.inf, -2, -1, 0, 1, 2, np.inf]
labs = ['z<-2', '-2~-1', '-1~0', '0~1', '1~2', 'z>2']
B['bucket'] = pd.cut(B['z'], bins, labels=labs)
crash = B['dd3d'] <= -0.05                                  # '폭락' 정의: 3d 내 -5% 터치
tb = B.groupby('bucket', observed=True).agg(
    r3d_mean=('r3d', 'mean'), r7d_mean=('r7d', 'mean'),
    dd3d_mean=('dd3d', 'mean'), crash5_rate=('dd3d', lambda s: float((s <= -0.05).mean())),
    n=('r3d', 'size'))
tb.round(5).to_csv(OUT("tbl_B_oiz_buckets.csv"), encoding='utf-8-sig')
log(f"\n[B OI z 버킷 → 이후 수익/낙폭] (시간봉 n={len(B)}, 폭락정의=3d내 -5%터치, 기저율 {crash.mean()*100:.1f}%)")
for b in labs:
    if b in tb.index:
        r = tb.loc[b]
        log(f"  {b:>6}: 3d {r['r3d_mean']*100:+.2f}% | 7d {r['r7d_mean']*100:+.2f}% | 3d낙폭 {r['dd3d_mean']*100:+.2f}% | 폭락확률 {r['crash5_rate']*100:.1f}% (n={int(r['n'])})")

fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
tt = tb.reindex(labs)
ax[0].bar(labs, tt['r3d_mean'] * 100, color='#0F6E56'); ax[0].axhline(0, color='k', lw=.8)
ax[0].set_title('B1. OI z bucket vs fwd 3d return %'); ax[0].grid(alpha=.3)
ax[1].bar(labs, tt['crash5_rate'] * 100, color='#C0392B')
ax[1].axhline(crash.mean() * 100, ls='--', color='gray', label=f'base rate {crash.mean()*100:.1f}%')
ax[1].set_title('B2. P(crash: -5% touched within 3d) %'); ax[1].legend(); ax[1].grid(alpha=.3)
plt.tight_layout(); plt.savefig(OUT("fig_B_oiz.png"), dpi=110); plt.close()

# ══ C. 파이사이클 (111DMA vs 2x350DMA) ════════════════════════════════════
C = pd.DataFrame({'close': px_d})
C['dma111'] = C['close'].rolling(111).mean()
C['dma350x2'] = C['close'].rolling(350).mean() * 2
C = C.dropna()
cross_up = (C['dma111'] > C['dma350x2']) & (C['dma111'].shift(1) <= C['dma350x2'].shift(1))
n_sig = int(cross_up.sum())
log(f"\n[C 파이사이클] 유효구간 {C.index.min().date()}~{C.index.max().date()}({len(C)}일) | 천장신호(111DMA 상향돌파 2x350DMA) {n_sig}건")
if n_sig:
    for t in C.index[cross_up]:
        after = px_d.loc[t:t + pd.Timedelta(days=90)]
        log(f"    신호 {t.date()}: 당시 {C.loc[t,'close']:,.0f} → 90d후 {after.iloc[-1]:,.0f} ({(after.iloc[-1]/C.loc[t,'close']-1)*100:+.1f}%) | 90d최대낙폭 {(after.min()/C.loc[t,'close']-1)*100:+.1f}%")
fig, ax = plt.subplots(figsize=(10, 4.4))
ax.plot(C.index, C['close'], color='#5D6D7E', lw=1, label='BTC daily close')
ax.plot(C.index, C['dma111'], color='#0F6E56', lw=1.2, label='111 DMA')
ax.plot(C.index, C['dma350x2'], color='#C0392B', lw=1.2, label='2 x 350 DMA')
for t in C.index[cross_up]:
    ax.axvline(t, color='orange', ls=':', lw=1.5)
ax.set_yscale('log'); ax.set_title(f'C. Pi Cycle Top in local window ({n_sig} signal(s))'); ax.legend(); ax.grid(alpha=.3)
plt.tight_layout(); plt.savefig(OUT("fig_C_picycle.png"), dpi=110); plt.close()

with open(OUT("lead_scan_report.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("\n[저장] tbl_A/B + fig_A/B/C + lead_scan_report.txt")
