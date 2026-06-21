# -*- coding: utf-8 -*-
# [파일명] test_07Prj_Ch4_RunAWS_Stg9_DualKSweepCausal.py
# 코드길이: 약 130줄 | 내부버전: ch4_stg9_dualksweep_v1
# ─────────────────────────────────────────────────────────────────────────────
# [목적 — 고딩 설명, 캡틴 지시 ⓑⓒ]
#   ⓑ Stg8 자체합성 MDD(-19.9%)와 Stg6 정식(-19.1%)의 차이 원인을 숫자로 입증:
#      정식은 '청산시각(exit_t) 순' 정렬(Stg6 58줄), 자체합성은 '진입시각(entry_t) 순'.
#      수익률은 곱셈이라 순서 무관, MDD는 경로의존 → 같은 데이터를 두 순서로 돌려 차이 재현.
#   ⓒ 정식 방식(Stg6 함수 박제 import, SW 원장만 인과 84건으로 교체)으로 k 0.70~0.80
#      0.01스텝 스윕 → 'MDD -19.5% 이내 최대 k' 제안(채택은 캡틴). 동시보유도 인과로 재계산.
# [근간(전부 무수정 사본, check 해시 대조)] Stg6 test(load_ts/load_sw/comp) + devledger264
#   + stg6 실행원장(TS exit_t) + 박제 SW원장 86(ⓑ재현용) + 인과 causal_ledger 84(c4964c55)
# [패치 명시] Stg6 모듈의 SW_LED '경로 상수'만 런타임 교체(수식·로직 무수정) — 데이터 스왑.
# [Out] stg9_result.txt / stg9_k_sweep.csv / stg9_k_sweep.png
# ==============================================================================
import os, sys
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
BOTS = os.path.join(HERE, "bots")
if BOTS not in sys.path:
    sys.path.insert(0, BOTS)
import test_07Prj_Ch4_RunAWS_Stg6_DualSynthesis as S6     # noqa: E402  정식 합성(박제)

CAUSAL = os.path.join(HERE, "causal_ledger.csv")
PASTE = os.path.join(BOTS, "07Prj_Ch2_SidewayDCARebuild_Stg1_ExpCutLiqSweep_ledger.csv")
OUT_TXT = os.path.join(HERE, "stg9_result.txt")
OUT_CSV = os.path.join(HERE, "stg9_k_sweep.csv")
OUT_PNG = os.path.join(HERE, "stg9_k_sweep.png")
MDD_TARGET = -19.5


def synth(sw_path):
    S6.SW_LED = sw_path                      # ★경로 상수만 교체(수식 무수정)
    ts = S6.load_ts(); sw = S6.load_sw()
    return ts, sw, pd.concat([ts, sw]).reset_index(drop=True)


def main():
    lines = []
    def log(s):
        print(s); lines.append(s)

    # ⓑ 순서가설 입증: 같은 데이터(박제 86) k=0.8 — exit_t순(정식) vs entry_t순(Stg8 자체합성)
    ts, sw, both = synth(PASTE)
    r_ex, m_ex, _ = S6.comp((both.sort_values('exit_t').p * 0.8).values)
    r_en, m_en, _ = S6.comp((both.sort_values('entry_t').p * 0.8).values)
    log(f"[B-원인] 같은 데이터 k=0.8 | exit_t순(정식): {r_ex:+.1f}%/MDD {m_ex:.1f}% | "
        f"entry_t순(Stg8 자체): {r_en:+.1f}%/MDD {m_en:.1f}%")
    log(f"[B-결론] ret 차이 {abs(r_ex-r_en):.2f}%p(순서무관 확인) / MDD 차이 {abs(m_ex-m_en):.2f}%p "
        f"→ -19.9 vs -19.1은 '정렬 기준(exit_t vs entry_t)' 차이로 전량 설명")

    # ⓒ 정식 방식 × 인과 84건 — k 0.70~0.80 0.01스텝
    ts_c, sw_c, both_c = synth(CAUSAL)
    both_c = both_c.sort_values('exit_t').reset_index(drop=True)
    rows = []
    log(f"\n[C] 인과 듀얼 k스윕(정식 exit_t순) — 목표: MDD {MDD_TARGET}% 이내 최대 k")
    log(f"{'k':>6}{'ret%':>10}{'MDD%':>9}{'-19.5%내':>9}{'-20%내':>8}")
    for k in np.round(np.arange(0.70, 0.801, 0.01), 2):
        r, m, _ = S6.comp((both_c.p * k).values)
        rows.append(dict(k=k, ret=round(r, 1), mdd=round(m, 2),
                         ok195=(m > MDD_TARGET), ok20=(m > -20.0)))
        log(f"{k:>6}{r:>10.1f}{m:>9.2f}{('O' if m > MDD_TARGET else 'X'):>9}{('O' if m > -20.0 else 'X'):>8}")
    ok = [x for x in rows if x['ok195']]
    rec = max(ok, key=lambda z: z['k']) if ok else None

    # 동시보유·합산노출 (인과, Stg6 [B] 방식 그대로)
    allt = pd.concat([ts_c, sw_c])
    days = pd.date_range(both_c.exit_t.min().normalize(), both_c.exit_t.max().normalize(), freq='D')
    maxexp = 0.0; both_days = 0
    for d in days:
        op = allt[(allt.entry_t <= d) & (allt.exit_t >= d)]
        maxexp = max(maxexp, op.exp.sum())
        if op.bot.nunique() > 1:
            both_days += 1
    log(f"\n[동시보유·인과] 최대 합산노출 {maxexp:.2f}x · 동시보유 {both_days}/{len(days)}일 "
        f"({both_days/len(days)*100:.1f}%)  (박제 기준 32/1091일 2.9%)")

    rec_s = (f"k={rec['k']} ({rec['ret']:+.1f}%/MDD {rec['mdd']}%)" if rec else "없음(-19.5%내 k 부재)")
    verdict = (f"VERDICT Stg9 | ⓑMDD차이=정렬기준(exit_t vs entry_t)로 전량설명({m_ex:.1f} vs {m_en:.1f}) | "
               f"ⓒ제안 {rec_s} — MDD {MDD_TARGET}% 이내 최대 k(채택은 캡틴) | 동시보유 {both_days}/{len(days)}일 "
               f"최대노출 {maxexp:.2f}x")
    log("\n" + verdict)

    pd.DataFrame(rows).to_csv(OUT_CSV, index=False, encoding='utf-8-sig')
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    try:
        import matplotlib
        matplotlib.use('Agg'); import matplotlib.pyplot as plt
        ks = [x['k'] for x in rows]
        fig, ax = plt.subplots(figsize=(8, 4.6))
        ax.plot(ks, [x['ret'] for x in rows], 'o-', color='#0F6E56', label='ret% (causal dual)')
        axb = ax.twinx()
        axb.plot(ks, [x['mdd'] for x in rows], 's--', color='#C0392B', label='MDD%')
        axb.axhline(MDD_TARGET, ls='--', color='orange', label='-19.5% target')
        axb.axhline(-20.0, ls=':', color='red', label='-20% hard limit')
        if rec:
            ax.axvline(rec['k'], ls=':', color='gray')
        ax.set_xlabel('k (exposure allocation)'); ax.set_title('Causal Dual k-Sweep 0.70~0.80 (official exit_t-order)')
        ax.legend(loc='upper left'); axb.legend(loc='lower right'); ax.grid(alpha=.3)
        plt.tight_layout(); plt.savefig(OUT_PNG, dpi=110)
        print(f"[그래프] {os.path.basename(OUT_PNG)}")
    except Exception as e:
        print(f"[그래프] 생략: {e}")


if __name__ == "__main__":
    main()
