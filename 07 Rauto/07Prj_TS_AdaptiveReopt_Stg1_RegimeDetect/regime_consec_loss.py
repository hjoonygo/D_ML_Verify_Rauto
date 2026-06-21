# -*- coding: utf-8 -*-
# [regime_consec_loss.py] ★캡틴 의문 검증: "TS 연속패배가 장세변화 신호인가? 몇 회가 맞나?"
#   핵심: 성급왕 패율 66%(승률34%)면 연패 3회는 '그냥 흔함'일 수 있다.
#   장세변화 신호이려면 (A)랜덤(기하분포)보다 긴 연패가 더 잦아야 하고(클러스터링),
#   (B)연패 후 다음거래 패율이 base보다 높아야(=손실 지속=재최적화 가치) 한다.
#   둘 다 아니면 '연패=노이즈'→재최적화 트리거로 부적합. 검증 led36_king 무수정.
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
    win = (R > 0).astype(int); loss = 1 - win
    base_lossrate = loss.mean()
    print(f"거래 {len(R)} | 승률 {win.mean()*100:.1f}% | 패율 {base_lossrate*100:.1f}%")

    # ── (A) 연패 streak 길이 분포: 관측 vs 랜덤(기하분포) ──
    streaks = []; cur = 0
    for x in loss:
        if x: cur += 1
        elif cur: streaks.append(cur); cur = 0
    if cur: streaks.append(cur)
    streaks = np.array(streaks)
    maxk = int(streaks.max())
    p = base_lossrate
    # 랜덤이면 streak 길이 k의 기대 개수 ∝ 기하분포. 관측 streak수 N_s 기준 기대 = N_s * (1-p)*p^(k-1)
    Ns = len(streaks)
    print(f"\n=== (A) 연패 길이 분포 (관측 vs 랜덤 기하분포 p={p:.2f}) ===")
    print(f"{'연패길이':>6} {'관측수':>6} {'랜덤기대':>8} {'관측/기대':>9}")
    obs = {}; exp = {}
    for k in range(1, min(maxk, 15) + 1):
        o = int((streaks == k).sum()) if k < maxk else int((streaks >= k).sum())
        e = Ns * (1 - p) * (p ** (k - 1))
        obs[k] = o; exp[k] = e
        print(f"{k:>6} {o:>6} {e:>8.1f} {(o/e if e>0 else 0):>9.2f}")
    print(f"  최장 연패: {maxk}회")

    # ── (B) 연패 K회 후 '다음 거래' 패율 (손실 지속 = 재최적화 가치) ──
    print(f"\n=== (B) 'K회 연패 직후 다음거래' 결과 (base 패율 {base_lossrate*100:.0f}%) ===")
    print(f"{'직전연패K':>8} {'표본':>5} {'다음패율':>8} {'다음승률':>8} {'다음5거래 평균R':>14}")
    nextloss = {}
    for K in range(1, 11):
        idxs = []
        run = 0
        for i in range(len(R)):
            if run == K and i < len(R):
                idxs.append(i)   # i = K연패 직후 거래
            run = run + 1 if loss[i] else 0
        if not idxs: continue
        nl = np.mean([loss[i] for i in idxs]) * 100
        nw = 100 - nl
        fwd5 = np.mean([R[i:i+5].mean() for i in idxs if i+1 <= len(R)]) * 100
        nextloss[K] = nl
        print(f"{K:>8} {len(idxs):>5} {nl:>7.0f}% {nw:>7.0f}% {fwd5:>+13.2f}%")

    # ── 그래프 ──
    fig, ax = plt.subplots(1, 2, figsize=(14, 5.5))
    ks = list(obs.keys())
    ax[0].bar([k-0.2 for k in ks], [obs[k] for k in ks], width=0.4, label='Observed', color='#d62728')
    ax[0].bar([k+0.2 for k in ks], [exp[k] for k in ks], width=0.4, label='Random (geometric)', color='#7f7f7f')
    ax[0].set_xlabel('Loss streak length'); ax[0].set_ylabel('count'); ax[0].set_title('(A) Loss-streak: Observed vs Random'); ax[0].legend(); ax[0].grid(alpha=.3)
    kk = sorted(nextloss.keys())
    ax[1].plot(kk, [nextloss[k] for k in kk], 'o-', color='#1f77b4', label='Next-trade loss rate')
    ax[1].axhline(base_lossrate*100, color='red', ls='--', label=f'base {base_lossrate*100:.0f}%')
    ax[1].set_xlabel('Consecutive losses K'); ax[1].set_ylabel('Next-trade loss rate %'); ax[1].set_title('(B) Loss rate AFTER K consecutive losses'); ax[1].legend(); ax[1].grid(alpha=.3)
    plt.tight_layout(); fp = os.path.join(HERE, "regime_consec_loss.png")
    plt.savefig(fp, dpi=110); print(f"\n[그래프] {fp}")

    # 판정
    ratio_long = np.mean([obs[k]/exp[k] for k in obs if k >= 4 and exp[k] > 0.5])
    print(f"\n[판정 힌트] 연패4+ 관측/기대 평균 {ratio_long:.2f} (>1.3이면 클러스터링=장세신호 / ~1이면 노이즈)")
    print(f"           연패 후 다음패율이 base({base_lossrate*100:.0f}%)보다 뚜렷이 높아야 '손실지속=재최적화 가치'.")


if __name__ == "__main__":
    main()
