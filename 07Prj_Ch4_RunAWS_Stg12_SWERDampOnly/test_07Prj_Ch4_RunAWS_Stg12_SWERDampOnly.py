# -*- coding: utf-8 -*-
# [파일명] test_07Prj_Ch4_RunAWS_Stg12_SWERDampOnly.py
# 코드길이: 약 150줄 | 내부버전: ch4_stg12_swerdamp_v1
# ─────────────────────────────────────────────────────────────────────────────
# [목적 — 고딩 설명, 캡틴 확정]
#   Stg11 분해 회신 반영: TS dead_range 댐핑 폐기(라벨 환상 3차 확인)·겹침캡 폐기(알짜).
#   살아남은 SW ER 댐핑(실시간 인과 신호 — 라이브 적격)만 단독 측정:
#   ① SW ER>=0.40 → ×0.5 (TS 무댐핑) × k 0.85~1.00(0.01스텝) → 'MDD -19.5% 이내 최대 k'
#      와 ret (캡틴 예상 +1650%± 검증)
#   ② 최적점 CPCV: 연도 4그룹(2023~2026) leave-2 6경로(주문) + 표준 6그룹 15경로(참고)
#      — p25>0 및 폴드별 MDD. 비견고면 '기각, k=0.77 유지'.
# [근간] Stg11과 동일(Stg6 합성 박제 / devledger264 / causal_ledger §8 / TE엔진 §8 — ER 산출)
# [Out] stg12_result.txt / stg12_k_sweep.csv / stg12_cpcv.csv / stg12_sweep.png
# ==============================================================================
import os, sys, itertools
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
BOTS = os.path.join(HERE, "bots")
if BOTS not in sys.path:
    sys.path.insert(0, BOTS)
import test_07Prj_Ch4_RunAWS_Stg6_DualSynthesis as S6     # noqa: E402
import trendstack_signal_engine as TE                      # noqa: E402

CAUSAL = os.path.join(HERE, "causal_ledger.csv")
ER_TREND = 0.40
W_DAMP = 0.5
MDD_TARGET = -19.5
K_BASE = 0.77
OUT_TXT = os.path.join(HERE, "stg12_result.txt")
OUT_CSV = os.path.join(HERE, "stg12_k_sweep.csv")
OUT_CPCV = os.path.join(HERE, "stg12_cpcv.csv")
OUT_PNG = os.path.join(HERE, "stg12_sweep.png")


def er_series_7h():
    for d in [os.path.dirname(HERE), r"D:\ML\verify"]:
        p = os.path.join(d, "Merged_Data_with_Regime_Features.csv")
        if os.path.exists(p):
            break
    df = pd.read_csv(p, usecols=['timestamp', 'open', 'high', 'low', 'close'],
                     index_col='timestamp', parse_dates=True).sort_index()
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    df7 = df.resample('420min', label='left', closed='left').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
    sig = TE.compute_signals(df7)
    return pd.Series(np.asarray(sig['er'], float), index=df7.index + pd.Timedelta(minutes=420))


def comp_mdd(p):
    r, m, _ = S6.comp(p)
    return r, m


def main():
    lines = []
    def log(s):
        print(s); lines.append(s)

    S6.SW_LED = CAUSAL
    ts = S6.load_ts(); sw = S6.load_sw()
    er7 = er_series_7h()
    ents = pd.to_datetime(sw['entry_t'].values)
    pos_idx = er7.index.searchsorted(ents, side='right') - 1
    er_at = np.where(pos_idx >= 0, er7.values[np.clip(pos_idx, 0, None)], np.nan)
    w_sw = np.where(np.nan_to_num(er_at, nan=0.0) >= ER_TREND, W_DAMP, 1.0)
    log(f"[B변형] SW ER>={ER_TREND}×{W_DAMP} 발동 {int((w_sw < 1).sum())}/{len(sw)}건 (TS 무댐핑) — 실시간 인과 신호")

    both = pd.concat([ts.assign(w=1.0), sw.assign(w=w_sw)]).sort_values('exit_t').reset_index(drop=True)
    p_w = (both.p * both.w).values

    # ① k 스윕
    rb, mb = comp_mdd(both.p.values * K_BASE)
    log(f"[기준] 무댐핑 k={K_BASE}: {rb:+.1f}%/MDD {mb:.2f}%")
    rows = []
    log(f"\n{'k':>6}{'ret%':>10}{'MDD%':>9}{'-19.5%내':>9}")
    for k in np.round(np.arange(0.85, 1.001, 0.01), 2):
        r, m = comp_mdd(p_w * k)
        rows.append(dict(k=k, ret=round(r, 1), mdd=round(m, 2), ok=(m > MDD_TARGET)))
        log(f"{k:>6}{r:>10.1f}{m:>9.2f}{('O' if m > MDD_TARGET else 'X'):>9}")
    ok = [x for x in rows if x['ok']]
    rec = max(ok, key=lambda z: z['k']) if ok else None
    if rec is None:
        log("[결과] -19.5% 이내 k 없음(0.85~1.00) → 기각, k=0.77 유지")
        verdict = "VERDICT Stg12 | -19.5%내 k 없음 → 기각, k=0.77 유지"
    else:
        log(f"\n[제안점] k={rec['k']} → ret {rec['ret']}% / MDD {rec['mdd']}% "
            f"(캡틴 예상 +1650%± 대조: {'부합' if abs(rec['ret']-1650) <= 200 else '괴리 — 본문 수치 우선'})")

        # ② CPCV — 연도 4그룹 leave-2 6경로(주문) + 표준 6그룹 15경로(참고)
        cpcv_rows = []
        def cpcv(groups_idx, tag):
            rets, mdds = [], []
            for combo in itertools.combinations(range(len(groups_idx)), 2):
                idx = np.sort(np.concatenate([groups_idx[g] for g in combo]))
                r, m = comp_mdd(p_w[idx] * rec['k'])
                rets.append(r); mdds.append(m)
                cpcv_rows.append(dict(mode=tag, fold="+".join(map(str, combo)), ret=round(r, 1), mdd=round(m, 2)))
            p25 = float(np.percentile(rets, 25))
            return p25, min(mdds), sum(1 for m in mdds if m <= -20.0), len(rets)

        years = both.exit_t.dt.year.values
        ygroups = [np.where(years == y)[0] for y in [2023, 2024, 2025, 2026]]
        p25y, wmy, bry, ny = cpcv(ygroups, "year4")
        g6 = np.array_split(np.arange(len(p_w)), 6)
        p25s, wms, brs, ns = cpcv(g6, "std6")
        log(f"\n[CPCV 연도4그룹 {ny}경로] p25 {p25y:+.1f}% | 최악폴드MDD {wmy:.2f}% | -20%위반 {bry}")
        log(f"[CPCV 표준6그룹 {ns}경로(참고)] p25 {p25s:+.1f}% | 최악폴드MDD {wms:.2f}% | -20%위반 {brs}")
        pd.DataFrame(cpcv_rows).to_csv(OUT_CPCV, index=False, encoding='utf-8-sig')

        robust = (p25y > 0) and (bry == 0)
        if robust:
            verdict = (f"VERDICT Stg12 | PASS — SW ER댐핑 단독 k={rec['k']}: {rec['ret']:+.1f}%/MDD {rec['mdd']}% "
                       f"| CPCV연도4 p25 {p25y:+.1f}%>0·위반0 (참고 표준6: p25 {p25s:+.1f}% 위반{brs}) "
                       f"| §9 갱신안 선보고(채택은 캡틴)")
        else:
            verdict = (f"VERDICT Stg12 | 기각, k=0.77 유지 — CPCV 비견고(연도4 p25 {p25y:+.1f}% 위반{bry})")
    log("\n" + verdict)
    pd.DataFrame(rows).to_csv(OUT_CSV, index=False, encoding='utf-8-sig')
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    try:
        import matplotlib
        matplotlib.use('Agg'); import matplotlib.pyplot as plt
        ks = [x['k'] for x in rows]
        fig, ax = plt.subplots(figsize=(8.5, 4.6))
        ax.plot(ks, [x['ret'] for x in rows], 'o-', color='#0F6E56', label='ret% (SW-ER-damp only)')
        axb = ax.twinx()
        axb.plot(ks, [x['mdd'] for x in rows], 's--', color='#C0392B', label='MDD%')
        axb.axhline(MDD_TARGET, ls='--', color='orange', label='-19.5% target')
        axb.axhline(-20.0, ls=':', color='red')
        if rec:
            ax.axvline(rec['k'], ls=':', color='gray')
        ax.set_xlabel('k'); ax.set_title('Stg12 SW-ER-Damp-Only k-Sweep 0.85~1.00 (causal dual)')
        ax.legend(loc='upper left'); axb.legend(loc='lower right'); ax.grid(alpha=.3)
        plt.tight_layout(); plt.savefig(OUT_PNG, dpi=110)
        print(f"[그래프] {os.path.basename(OUT_PNG)}")
    except Exception as e:
        print(f"[그래프] 생략: {e}")


if __name__ == "__main__":
    main()
