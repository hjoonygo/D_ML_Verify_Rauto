# -*- coding: utf-8 -*-
# [파일명] test_07Prj_Ch4_RunAWS_Stg10_OverlapCapSweep.py
# 코드길이: 약 150줄 | 내부버전: ch4_stg10_overlapcap_v1
# ─────────────────────────────────────────────────────────────────────────────
# [목적 — 고딩 설명, 캡틴 지시]
#   인과 듀얼 합성(Stg9 정식 방식, exit_t순)에서 '두 봇 동시보유일'에만 합산노출을 C로 캡:
#   C=3.0/3.5/4.0/4.5 × 평시 k=0.80~1.00(0.05) 2차원 스윕 → ret/MDD 표 +
#   'MDD -19.5% 이내 최대 ret' 조합 제안. 겹침일 손익분포(캡이 알짜를 깎는지) 별도 보고.
# [★가정 명시 — §2] 거래 손익은 보유일에 균등 귀속된다고 보고(일중 경로 없음),
#   거래별 캡 배율 = 보유일별 배율의 평균(겹침·캡일은 C/E_day, 그 외 1.0). E_day = 그날
#   열려있는 모든 거래의 exp×k 합. 캡은 '양 봇 동시보유일'에만 적용(캡틴 명세).
# [근간] Stg6 test(합성·박제) + devledger264 + stg6실행원장(TS exit_t) + causal_ledger(§8)
# [Out] stg10_result.txt / stg10_cap_sweep.csv / stg10_overlap_pnl.csv / stg10_heatmap.png
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
import test_07Prj_Ch4_RunAWS_Stg6_DualSynthesis as S6     # noqa: E402

CAUSAL = os.path.join(HERE, "causal_ledger.csv")
C_GRID = [3.0, 3.5, 4.0, 4.5]
K_GRID = [0.80, 0.85, 0.90, 0.95, 1.00]
MDD_TARGET = -19.5
OUT_TXT = os.path.join(HERE, "stg10_result.txt")
OUT_CSV = os.path.join(HERE, "stg10_cap_sweep.csv")
OUT_OVL = os.path.join(HERE, "stg10_overlap_pnl.csv")
OUT_PNG = os.path.join(HERE, "stg10_heatmap.png")


def main():
    lines = []
    def log(s):
        print(s); lines.append(s)

    S6.SW_LED = CAUSAL
    ts = S6.load_ts(); sw = S6.load_sw()
    allt = pd.concat([ts, sw]).reset_index(drop=True)

    # 정식(Stg6 [B]) 정의 그대로: d=자정 시점에 entry_t<=d & exit_t>=d 인 거래가 '열림'
    days = pd.date_range(allt.exit_t.min().normalize(), allt.exit_t.max().normalize(), freq='D')
    nD = len(days); nT = len(allt)
    e_ns = allt.entry_t.values.astype('datetime64[ns]')
    x_ns = allt.exit_t.values.astype('datetime64[ns]')
    d_ns = days.values
    open_m = (e_ns[:, None] <= d_ns[None, :]) & (x_ns[:, None] >= d_ns[None, :])
    is_ts = (allt.bot == 'TS').values
    both_day = open_m[is_ts].any(axis=0) & open_m[~is_ts].any(axis=0)
    log(f"[겹침] 동시보유 {int(both_day.sum())}/{nD}일")

    exp = allt.exp.values
    order = np.argsort(allt.exit_t.values, kind='stable')   # 정식 exit_t순

    def run(C, k):
        E_day = (open_m * (exp * k)[:, None]).sum(axis=0)            # 그날 합산노출
        f_day = np.ones(nD)
        capped = both_day & (E_day > C)
        f_day[capped] = C / E_day[capped]
        # 거래별 배율 = 보유일 배율 평균(균등귀속 가정)
        held_n = open_m.sum(axis=1).astype(float)
        scale = np.where(held_n > 0, (open_m * f_day[None, :]).sum(axis=1) / np.maximum(held_n, 1), 1.0)
        # held_n=0 = 자정을 안 넘긴 당일거래 → 자정샘플링상 노출일 없음 → 캡 미적용(1.0)
        p = allt.p.values * k * scale
        r, m, _ = S6.comp(p[order])
        return r, m, int(capped.sum())

    rows = []
    log(f"\n[2D 스윕] C(겹침일 합산노출 캡) × k(평시 노출)  — ret% / MDD%")
    hdr = "  C\\k " + "".join(f"{k:>16}" for k in K_GRID)
    log(hdr)
    for C in C_GRID:
        cells = []
        for k in K_GRID:
            r, m, ncap = run(C, k)
            rows.append(dict(C=C, k=k, ret=round(r, 1), mdd=round(m, 2), cap_days=ncap,
                             ok=(m > MDD_TARGET)))
            cells.append(f"{r:7.0f}/{m:6.2f}{'*' if m > MDD_TARGET else ' '}")
        log(f"{C:>5} " + "".join(f"{c:>16}" for c in cells))
    log("  (*=MDD -19.5% 이내)")
    ok = [x for x in rows if x['ok']]
    rec = max(ok, key=lambda z: z['ret']) if ok else None
    base_r, base_m, _ = run(99.0, 0.77)   # 캡 사실상 없음 + k=0.77 = 기준 재현 체크
    log(f"\n[재현체크] 캡없음·k0.77 = {base_r:+.1f}%/{base_m:.2f}% (Stg9 기준 +1059.6/-19.33 대조)")
    rec_s = f"C={rec['C']}·k={rec['k']} → {rec['ret']:+.1f}%/MDD {rec['mdd']}% (캡발동 {rec['cap_days']}일)" if rec else "없음"
    log(f"[제안] MDD {MDD_TARGET}% 이내 최대 ret: {rec_s} (채택은 캡틴)")

    # 겹침일 손익분포 — 캡이 알짜 수익을 깎는지
    ovl_trades = allt[open_m[:, both_day].any(axis=1)]
    n_o = len(ovl_trades); p_o = ovl_trades.p.sum(); p_all = allt.p.sum()
    pos = ovl_trades[ovl_trades.p > 0]; neg = ovl_trades[ovl_trades.p <= 0]
    log(f"\n[겹침일 손익분포] 겹침 관여 거래 {n_o}/{len(allt)}건 | p합 {p_o*100:+.1f}%p "
        f"(전체 {p_all*100:+.1f}%p의 {p_o/p_all*100:.1f}%) | 수익 {len(pos)}건 {pos.p.sum()*100:+.1f}%p "
        f"/ 손실 {len(neg)}건 {neg.p.sum()*100:+.1f}%p")
    by_bot = ovl_trades.groupby('bot').p.agg(['count', 'sum'])
    for b, r2 in by_bot.iterrows():
        log(f"  {b}: {int(r2['count'])}건 p합 {r2['sum']*100:+.1f}%p")
    ovl_trades[['entry_t', 'exit_t', 'bot', 'p']].to_csv(OUT_OVL, index=False, encoding='utf-8-sig')

    verdict = (f"VERDICT Stg10 | 겹침 {int(both_day.sum())}/{nD}일 | 제안 {rec_s} | "
               f"겹침관여 p합 {p_o*100:+.1f}%p({p_o/p_all*100:.0f}% of total, 수익{len(pos)}/손실{len(neg)}) | "
               f"가정: 보유일 균등귀속(일중 경로 없음)")
    log("\n" + verdict)
    pd.DataFrame(rows).to_csv(OUT_CSV, index=False, encoding='utf-8-sig')
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    try:
        import matplotlib
        matplotlib.use('Agg'); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 2, figsize=(12, 4.4))
        retm = np.array([[next(x['ret'] for x in rows if x['C'] == C and x['k'] == k)
                          for k in K_GRID] for C in C_GRID])
        mddm = np.array([[next(x['mdd'] for x in rows if x['C'] == C and x['k'] == k)
                          for k in K_GRID] for C in C_GRID])
        for a, M, ttl in [(ax[0], retm, 'Return % (causal dual, overlap-capped)'),
                          (ax[1], mddm, 'MDD % (red text = breaches -19.5%)')]:
            im = a.imshow(M, cmap='RdYlGn' if ttl.startswith('Return') else 'RdYlGn_r', aspect='auto')
            a.set_xticks(range(len(K_GRID))); a.set_xticklabels(K_GRID)
            a.set_yticks(range(len(C_GRID))); a.set_yticklabels(C_GRID)
            a.set_xlabel('k (normal exposure)'); a.set_ylabel('C (overlap cap)')
            a.set_title(ttl)
            for i in range(len(C_GRID)):
                for j in range(len(K_GRID)):
                    bad = mddm[i, j] <= MDD_TARGET
                    a.text(j, i, f"{M[i, j]:.0f}", ha='center', va='center',
                           fontsize=8, color='red' if bad else 'black')
        fig.suptitle('Stg10 Overlap-Cap 2D Sweep')
        plt.tight_layout(); plt.savefig(OUT_PNG, dpi=110)
        print(f"[그래프] {os.path.basename(OUT_PNG)}")
    except Exception as e:
        print(f"[그래프] 생략: {e}")


if __name__ == "__main__":
    main()
