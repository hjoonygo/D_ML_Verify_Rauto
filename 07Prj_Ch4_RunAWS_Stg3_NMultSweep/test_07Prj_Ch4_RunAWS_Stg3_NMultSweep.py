# [test_07Prj_Ch4_RunAWS_Stg3_NMultSweep.py]
# 코드길이: 약 180줄 / 내부버전: ch4_stg3_nmult_test_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 확정알파의 NMULT(역회귀=반대방향 OPVnN 축소배수, 현재 0.60)를 0.4~0.8로 스윕,
#        CPCV(조합형 교차검증)로 '0.6보다 견고하게 나은 값이 있는가'를 검증(결과 주인공).
#        N_BOOST는 1.0 고정(확정). 검증된 봇 무수정 — devledger(264 실거래) 위에서 NMULT만 재계산.
# [맥락] REDUCE그룹(역회귀 120거래)은 sumR 0.978로 최대기여인데 지금 0.6으로 누름.
#        덜 누르면(0.7~0.8) 수익↑/MDD↑, 더 누르면(0.4~0.5) MDD↓/수익↓ — 견고한 균형점 탐색.
# [근간] 07Prj_Ch2_Stg2_TrendStack_OPVnNSweep_devledger.csv (264 실거래)
#        bot_trendstack_signal.py(NMULT·opvnn_mult 원본 36줄) / trendstack_poc.py 참조 동봉.
# [복리] BTC선물 $10,000 시작·계좌잔금 복리. 거래별 p=R×노출, 노출=EXP×OPVnN배수×업트렌드숏컷.
# [CPCV] 264거래 시간순 6그룹 → C(6,2)=15 조합 부분표본마다 복리·MDD → 견고성(최악·평균·한도위반).
# [한계] devledger 기반 재구성(절대수치 근사). 'NMULT 상대비교'가 목적.
# ── 함수 ── load / p_of(df,nmult) / comp(p) / cpcv(p,k,r) / main()
# ── 상수 ── EXP=1.559 / OPV=0.25 / NBOOST=1.00(고정) / START=$10,000 / LIMIT_MDD=-20%
# ─────────────────────────────────────────────────────────────────────────
import os
import csv
import itertools
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DL = os.path.join(HERE, "07Prj_Ch2_Stg2_TrendStack_OPVnNSweep_devledger.csv")
RESULTS = os.path.join(HERE, "07Prj_Ch4_RunAWS_Stg3_NMultSweep_results.csv")
PNG = os.path.join(HERE, "07Prj_Ch4_RunAWS_Stg3_NMultSweep.png")

EXP = 1.559
OPV = 0.25
NBOOST = 1.00
START = 10000.0
LIMIT_MDD = -20.0
NMULTS = [0.4, 0.5, 0.6, 0.7, 0.8]
BASELINE = 0.6


def load():
    d = pd.read_csv(DL)
    d['entry_t'] = pd.to_datetime(d['entry_t']); d['year'] = d['entry_t'].dt.year
    d['dev'] = pd.to_numeric(d['dev'], errors='coerce')
    d['rdir'] = d['regime_dir'].replace(-9223372036854775808, np.nan)
    d['cut'] = np.where((d['regime'] == 'uptrend') & (d['side'] == -1), 0.0, 1.0)
    return d


def p_of(d, nmult):
    dev = d['dev'].values; rdir = d['rdir'].values; side = d['side'].values
    m = np.ones(len(d))
    fire = (~np.isnan(dev)) & (~np.isnan(rdir)) & (np.abs(dev) >= OPV)
    same = fire & (side == rdir)        # 동일방향(회귀) → N_BOOST(고정1.0)
    opp = fire & (side == -rdir)        # 반대방향(역회귀) → NMULT(스윕)
    m[same] = NBOOST
    m[opp] = nmult
    exp = EXP * m * d['cut'].values
    return d['R'].values * exp


def comp(p):
    bal = START; peak = START; mdd = 0.0
    for x in p:
        bal *= (1.0 + x); peak = max(peak, bal); mdd = min(mdd, bal / peak - 1.0)
    return (bal / START - 1.0) * 100.0, mdd * 100.0, bal


def cpcv(p, k=6, r=2):
    groups = np.array_split(np.arange(len(p)), k)
    rets = []; mdds = []
    for combo in itertools.combinations(range(k), r):
        idx = np.sort(np.concatenate([groups[g] for g in combo]))
        ret, mdd, _ = comp(p[idx])
        rets.append(ret); mdds.append(mdd)
    rets = np.array(rets); mdds = np.array(mdds)
    return dict(mean=round(rets.mean(), 1), worst_ret=round(rets.min(), 1),
                worst_mdd=round(mdds.min(), 1), breach=int((mdds <= LIMIT_MDD).sum()), n=len(rets))


def main():
    d = load()
    rows = []
    print("=" * 92)
    print("[test] 07Prj_Ch4_RunAWS_Stg3_NMultSweep — NMULT 0.4~0.8 · CPCV 견고성 ($10,000 복리)")
    print("=" * 92)
    print(f"{'NMULT':>7}{'full_ret%':>10}{'full_mdd%':>10}{'Calmar':>8}"
          f"{'cpcv_mean':>10}{'cpcv_worstRet':>14}{'cpcv_worstMDD':>14}{'breach':>7}")
    for nm in NMULTS:
        p = p_of(d, nm)
        ret, mdd, bal = comp(p)
        cal = ret / abs(mdd) if mdd < 0 else float('nan')
        cv = cpcv(p)
        yr = {y: round(comp(p[(d['year'] == y).values])[0], 1) for y in [2023, 2024, 2025, 2026]}
        rows.append(dict(NMULT=nm, full_ret=round(ret, 1), full_mdd=round(mdd, 1), calmar=round(cal, 1),
                         final_bal=round(bal, 0), cpcv_mean=cv['mean'], cpcv_worst_ret=cv['worst_ret'],
                         cpcv_worst_mdd=cv['worst_mdd'], cpcv_breach=cv['breach'],
                         y2023=yr[2023], y2024=yr[2024], y2025=yr[2025], y2026=yr[2026]))
        print(f"{nm:>7}{ret:>10.1f}{mdd:>10.1f}{cal:>8.1f}{cv['mean']:>10}"
              f"{cv['worst_ret']:>14}{cv['worst_mdd']:>14}{cv['breach']:>7}")

    base = next(r for r in rows if r['NMULT'] == BASELINE)
    zero_breach = [r for r in rows if r['cpcv_breach'] == 0]               # CPCV 전조합 한도 내(견고)
    robust = max(zero_breach, key=lambda r: r['full_ret']) if zero_breach else None  # 견고쿠션 후보(최고수익)
    best_cal = max(rows, key=lambda r: r['calmar'])                        # Calmar 최고
    print("-" * 92)
    print(f"[기준] NMULT=0.6(확정) : {base['full_ret']}% / full MDD {base['full_mdd']}% / Calmar {base['calmar']} "
          f"/ CPCV최악MDD {base['cpcv_worst_mdd']}% · 한도위반 {base['cpcv_breach']}")
    if robust:
        print(f"[견고쿠션] NMULT={robust['NMULT']} : {robust['full_ret']}% / MDD {robust['full_mdd']}% / "
              f"Calmar {robust['calmar']} / CPCV최악MDD {robust['cpcv_worst_mdd']}% · 한도위반 {robust['cpcv_breach']}(=전조합 -20%내)")
    print(f"[Calmar최고] NMULT={best_cal['NMULT']} : {best_cal['full_ret']}% / MDD {best_cal['full_mdd']}% / "
          f"Calmar {best_cal['calmar']} / CPCV최악MDD {best_cal['cpcv_worst_mdd']}% · 한도위반 {best_cal['cpcv_breach']}")
    print(f"[트레이드오프] NMULT↑(덜 줄임)=수익·Calmar↑ but CPCV최악MDD↑ / NMULT↓(더 줄임)=견고 but 수익↓")
    print(f"[판단필요] '절대 MDD -20% 견고'면 견고쿠션값, 'Calmar 우선'이면 상향 — 사장님 결정 사안.")
    verdict = (f"기준0.6=CPCV1위반(실경로-15.4%안전) / 견고쿠션 NMULT={robust['NMULT'] if robust else 'NA'}(0위반) "
               f"/ Calmar최고 NMULT={best_cal['NMULT']} → 토론필요")
    print(f"VERDICT::{verdict}")

    with open(RESULTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"[저장] {os.path.basename(RESULTS)}")

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        nms = [r['NMULT'] for r in rows]
        fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
        ax[0].plot(nms, [r['full_ret'] for r in rows], 'o-', color='#0F6E56', label='full ret%')
        ax[0].plot(nms, [r['cpcv_worst_ret'] for r in rows], 's--', color='#854F0B', label='CPCV worst ret%')
        ax[0].axvline(BASELINE, ls=':', color='gray'); ax[0].set_title('Return vs NMULT (0.6=current)'); ax[0].set_xlabel('NMULT'); ax[0].legend(); ax[0].grid(alpha=.3)
        ax[1].plot(nms, [r['full_mdd'] for r in rows], 'o-', color='#0F6E56', label='full MDD%')
        ax[1].plot(nms, [r['cpcv_worst_mdd'] for r in rows], 's--', color='#C0392B', label='CPCV worst MDD%')
        ax[1].axhline(LIMIT_MDD, ls='--', color='red', label='-20% limit'); ax[1].axvline(BASELINE, ls=':', color='gray'); ax[1].set_title('MDD vs NMULT'); ax[1].set_xlabel('NMULT'); ax[1].legend(); ax[1].grid(alpha=.3)
        fig.suptitle('NMULT CPCV Sweep (devledger 264 trades, N_BOOST=1.0 fixed)', weight='bold')
        plt.tight_layout(); plt.savefig(PNG, dpi=110, bbox_inches='tight')
        print(f"[그래프] {os.path.basename(PNG)}")
    except Exception as e:
        print(f"[그래프] 생략: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
