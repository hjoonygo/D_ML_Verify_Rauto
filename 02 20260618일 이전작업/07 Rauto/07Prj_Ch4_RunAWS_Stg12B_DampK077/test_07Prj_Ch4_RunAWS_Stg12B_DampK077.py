# -*- coding: utf-8 -*-
# [파일명] test_07Prj_Ch4_RunAWS_Stg12B_DampK077.py
# 코드길이: 약 165줄 | 내부버전: ch4_stg12b_dampk077_v1
# ─────────────────────────────────────────────────────────────────────────────
# [목적 — 캡틴 회신(2026-06-12) 반영]
#   Stg12 k=0.93 기각(표준6 CPCV 2위반 = 라이브 시작일 리스크, 연도4 PASS는 잣대 편향).
#   ER댐핑은 '쿠션 용도'로 재실측: k=0.77 고정 + SW ER>=0.40×0.5 (TS 무댐핑)
#   ① 실경로 ret/MDD ② 표준6 CPCV(본선): 최악폴드MDD·-20%위반수 ③ 무댐핑 k=0.77 동일잣대
#   대조(사과대사과). 회의실 추정 +1085%/-16.2%/최악폴드 -20.3 부근과 대조.
#   [채택 게이트] 댐핑판 최악폴드가 무댐핑판 대비 개선 AND 역대 허용선 -20.2% 이내(>=)
#   → 충족 시 §9 갱신안: '듀얼 확정 = k0.77 + SW ER>=0.40×0.5' (채택은 캡틴 승인 후).
#   잣대 규칙(캡틴 확정): 이후 CPCV는 표준6그룹=본선, 연도4그룹=참고.
# [근간] Stg12와 동일(Stg6 합성 박제 bots/ + causal_ledger §8 + TE엔진 §8 — ER 산출)
# [Out] stg12b_result.txt / stg12b_cpcv.csv / stg12b_curve.png
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
K_FIX = 0.77                 # 캡틴 확정: k 상향 없이 쿠션 용도
WORST_ALLOW = -20.2          # 역대 허용선(Stg3 NMultSweep CPCV 최악MDD -20.2%)
EST = dict(ret=1085.0, mdd=-16.2, worst=-20.3)   # 회의실 추정(대조용)
OUT_TXT = os.path.join(HERE, "stg12b_result.txt")
OUT_CPCV = os.path.join(HERE, "stg12b_cpcv.csv")
OUT_PNG = os.path.join(HERE, "stg12b_curve.png")


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
    log(f"[댐핑정의] SW ER>={ER_TREND}×{W_DAMP} 발동 {int((w_sw < 1).sum())}/{len(sw)}건 (TS 무댐핑·실시간 인과 신호)")
    log(f"[잣대] CPCV 표준6그룹 15경로=본선 / 연도4그룹 6경로=참고 (캡틴 확정 2026-06-12)")

    both = pd.concat([ts.assign(w=1.0), sw.assign(w=w_sw)]).sort_values('exit_t').reset_index(drop=True)
    p_nodamp = both.p.values * K_FIX
    p_damp = (both.p * both.w).values * K_FIX

    cpcv_rows = []
    def cpcv(p_arr, groups_idx, tag):
        rets, mdds = [], []
        for combo in itertools.combinations(range(len(groups_idx)), 2):
            idx = np.sort(np.concatenate([groups_idx[g] for g in combo]))
            r, m = comp_mdd(p_arr[idx])
            rets.append(r); mdds.append(m)
            cpcv_rows.append(dict(mode=tag, fold="+".join(map(str, combo)), ret=round(r, 1), mdd=round(m, 2)))
        p25 = float(np.percentile(rets, 25))
        return p25, min(mdds), sum(1 for m in mdds if m <= -20.0), len(rets)

    g6 = np.array_split(np.arange(len(both)), 6)
    years = both.exit_t.dt.year.values
    ygroups = [np.where(years == y)[0] for y in [2023, 2024, 2025, 2026]]

    res = {}
    for name, p_arr in [("A_무댐핑", p_nodamp), ("B_댐핑", p_damp)]:
        r_full, m_full = comp_mdd(p_arr)
        p25s, wms, brs, ns = cpcv(p_arr, g6, f"{name}_std6")
        p25y, wmy, bry, ny = cpcv(p_arr, ygroups, f"{name}_year4")
        res[name] = dict(ret=r_full, mdd=m_full, p25s=p25s, wms=wms, brs=brs,
                         p25y=p25y, wmy=wmy, bry=bry)
        log(f"\n[{name} k={K_FIX}] 실경로 {r_full:+.1f}% / MDD {m_full:.2f}%")
        log(f"  CPCV 표준6({ns}경로·본선): p25 {p25s:+.1f}% | 최악폴드MDD {wms:.2f}% | -20%위반 {brs}")
        log(f"  CPCV 연도4({ny}경로·참고): p25 {p25y:+.1f}% | 최악폴드MDD {wmy:.2f}% | -20%위반 {bry}")

    A, B = res["A_무댐핑"], res["B_댐핑"]
    log(f"\n[회의실 추정 대조] 추정 {EST['ret']:+.0f}%/{EST['mdd']}%/최악 {EST['worst']} vs "
        f"실측 {B['ret']:+.1f}%/{B['mdd']:.2f}%/최악 {B['wms']:.2f} → "
        f"ret {'부합' if abs(B['ret']-EST['ret']) <= 150 else '괴리 — 본문 수치 우선'}")

    improve = B['wms'] > A['wms']
    within = B['wms'] >= WORST_ALLOW
    log(f"\n[채택 게이트] ①최악폴드 개선(B {B['wms']:.2f} > A {A['wms']:.2f}): {'충족' if improve else '미충족'}"
        f" | ②역대 허용선 {WORST_ALLOW}% 이내: {'충족' if within else '미충족'}")
    if improve and within:
        verdict = (f"VERDICT Stg12B | 게이트 충족 — §9 갱신안 적합: 듀얼 확정 = k{K_FIX} + SW ER>={ER_TREND}×{W_DAMP} "
                   f"| 실경로 {B['ret']:+.1f}%/MDD {B['mdd']:.2f}% | 표준6 p25 {B['p25s']:+.1f}% 최악 {B['wms']:.2f}% 위반{B['brs']} "
                   f"(무댐핑 최악 {A['wms']:.2f}% 위반{A['brs']}) | 채택은 캡틴")
    else:
        verdict = (f"VERDICT Stg12B | 게이트 미충족 — 기각, 무댐핑 k=0.77 유지 "
                   f"| 댐핑 최악 {B['wms']:.2f}%(개선 {improve}/허용선내 {within}) vs 무댐핑 {A['wms']:.2f}%")
    log("\n" + verdict)

    pd.DataFrame(cpcv_rows).to_csv(OUT_CPCV, index=False, encoding='utf-8-sig')
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    try:
        import matplotlib
        matplotlib.use('Agg'); import matplotlib.pyplot as plt
        _, _, ca = S6.comp(p_nodamp); _, _, cb = S6.comp(p_damp)
        fig, ax = plt.subplots(figsize=(9, 4.6))
        ax.plot(ca, color='#5D6D7E', label=f"A no-damp k0.77 ({A['ret']:+.0f}%/{A['mdd']:.1f}%)")
        ax.plot(cb, color='#0F6E56', lw=2, label=f"B ER-damp k0.77 ({B['ret']:+.0f}%/{B['mdd']:.1f}%)")
        ax.set_yscale('log'); ax.set_title('Stg12B Cushion Check: k=0.77 no-damp vs SW-ER-damp ($10k compound)')
        ax.legend(); ax.grid(alpha=.3)
        plt.tight_layout(); plt.savefig(OUT_PNG, dpi=110)
        print(f"[그래프] {os.path.basename(OUT_PNG)}")
    except Exception as e:
        print(f"[그래프] 생략: {e}")


if __name__ == "__main__":
    main()
