# [test_07Prj_Ch4_RunAWS_Stg2_NBoostSweep.py]
# 코드길이: 약 175줄 / 내부버전: ch4_stg2_nboost_test_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 확정알파의 N_BOOST(동일방향 OPVnN 부스트, 현재 1.0=부스트없음)를 1.0~1.4로 스윕,
#        CPCV(조합형 교차검증)로 '과적합 아닌 견고한 상향'인지 검증(결과 주인공).
#        검증된 봇은 무수정 — 이 거래들이 나온 devledger(264 실거래) 위에서 N_BOOST만 바꿔 재계산.
# [근간] 07Prj_Ch2_Stg2_TrendStack_OPVnNSweep_devledger.csv (264 실거래 2023-05~2026-04)
#        bot_trendstack_signal.py(N_BOOST·opvnn_mult 원본) / trendstack_poc.py(dev·POC 원본) 참조 동봉.
# [복리] BTC선물 $10,000 시작·계좌잔금 복리. 거래별 p=R×노출, 노출=EXP×OPVnN배수×업트렌드숏컷.
# [CPCV] 264거래를 시간순 6그룹 → C(6,2)=15 조합 부분표본마다 복리·MDD 분포 → 견고성(최악·평균·한도위반).
# [한계] devledger 기반 재구성(+724.9%≈원본+827%, 강제청산 미반영 근사). 절대수치 아닌 'N_BOOST 상대비교'가 목적.
# ── 함수 In/Out ──
#   load()                In: devledger Out: DataFrame(dev·rdir·cut 전처리)
#   p_of(df, nboost)      In: df·N_BOOST Out: 거래별 손익 p 배열
#   comp(p)               In: p Out: (수익%, MDD%, 최종$)
#   cpcv(p, k, r)         In: p·그룹수·테스트그룹수 Out: dict(평균·최소·최악MDD·한도위반수)
#   main()                In: - Out: results.csv + PNG + 콘솔 요약·권장 N_BOOST
# ── 상수 ── EXP=1.559 / OPV=0.25 / NMULT=0.60 / START=$10,000 / LIMIT_MDD=-20%
# ─────────────────────────────────────────────────────────────────────────
import os
import csv
import itertools
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DL = os.path.join(HERE, "07Prj_Ch2_Stg2_TrendStack_OPVnNSweep_devledger.csv")
RESULTS = os.path.join(HERE, "07Prj_Ch4_RunAWS_Stg2_NBoostSweep_results.csv")
PNG = os.path.join(HERE, "07Prj_Ch4_RunAWS_Stg2_NBoostSweep.png")

EXP = 1.559
OPV = 0.25
NMULT = 0.60
START = 10000.0
LIMIT_MDD = -20.0
NBOOSTS = [1.0, 1.1, 1.2, 1.3, 1.4]


def load():
    d = pd.read_csv(DL)
    d['entry_t'] = pd.to_datetime(d['entry_t']); d['year'] = d['entry_t'].dt.year
    d['dev'] = pd.to_numeric(d['dev'], errors='coerce')
    d['rdir'] = d['regime_dir'].replace(-9223372036854775808, np.nan)
    d['cut'] = np.where((d['regime'] == 'uptrend') & (d['side'] == -1), 0.0, 1.0)  # 업트렌드 숏컷
    return d


def p_of(d, nboost):
    dev = d['dev'].values; rdir = d['rdir'].values; side = d['side'].values
    m = np.ones(len(d))
    fire = (~np.isnan(dev)) & (~np.isnan(rdir)) & (np.abs(dev) >= OPV)
    same = fire & (side == rdir)        # 동일방향(회귀) → N_BOOST
    opp = fire & (side == -rdir)        # 반대방향(역회귀) → NMULT
    m[same] = nboost
    m[opp] = NMULT
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
    print("[test] 07Prj_Ch4_RunAWS_Stg2_NBoostSweep — N_BOOST 1.0~1.4 · CPCV 견고성 ($10,000 복리)")
    print("=" * 92)
    print(f"{'N_BOOST':>8}{'full_ret%':>10}{'full_mdd%':>10}{'Calmar':>8}"
          f"{'cpcv_mean':>10}{'cpcv_worstRet':>14}{'cpcv_worstMDD':>14}{'breach':>7}")
    for nb in NBOOSTS:
        p = p_of(d, nb)
        ret, mdd, bal = comp(p)
        cal = ret / abs(mdd) if mdd < 0 else float('nan')
        cv = cpcv(p)
        yr = {y: round(comp(p[(d['year'] == y).values])[0], 1) for y in [2023, 2024, 2025, 2026]}
        rows.append(dict(N_BOOST=nb, full_ret=round(ret, 1), full_mdd=round(mdd, 1), calmar=round(cal, 1),
                         final_bal=round(bal, 0), cpcv_mean=cv['mean'], cpcv_worst_ret=cv['worst_ret'],
                         cpcv_worst_mdd=cv['worst_mdd'], cpcv_breach=cv['breach'],
                         y2023=yr[2023], y2024=yr[2024], y2025=yr[2025], y2026=yr[2026]))
        print(f"{nb:>8}{ret:>10.1f}{mdd:>10.1f}{cal:>8.1f}{cv['mean']:>10}"
              f"{cv['worst_ret']:>14}{cv['worst_mdd']:>14}{cv['breach']:>7}")

    # 권장: full·CPCV최악 모두 MDD 한도 내 + CPCV 최악수익>0 인 최고 N_BOOST
    ok = [r for r in rows if r['full_mdd'] > LIMIT_MDD and r['cpcv_worst_mdd'] > LIMIT_MDD and r['cpcv_worst_ret'] > 0]
    rec = max(ok, key=lambda r: r['full_ret']) if ok else rows[0]
    base = rows[0]
    print("-" * 92)
    print(f"[기준] N_BOOST=1.0 : {base['full_ret']}% / MDD {base['full_mdd']}% / Calmar {base['calmar']}")
    print(f"[권장] N_BOOST={rec['N_BOOST']} : {rec['full_ret']}% / MDD {rec['full_mdd']}% / Calmar {rec['calmar']} "
          f"(CPCV 최악MDD {rec['cpcv_worst_mdd']}% · 최악수익 {rec['cpcv_worst_ret']}% · 한도위반 {rec['cpcv_breach']}/{cpcv(p_of(d,1.0))['n']})")
    print(f"[근거] 한도(-20%) 내 + CPCV 전조합 양수수익 유지하는 최고 부스트. (절대수치는 devledger 근사)")

    with open(RESULTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"[저장] {os.path.basename(RESULTS)}")

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        nbs = [r['N_BOOST'] for r in rows]
        fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
        ax[0].plot(nbs, [r['full_ret'] for r in rows], 'o-', color='#0F6E56', label='full ret%')
        ax[0].plot(nbs, [r['cpcv_worst_ret'] for r in rows], 's--', color='#854F0B', label='CPCV worst ret%')
        ax[0].axvline(rec['N_BOOST'], ls=':', color='gray'); ax[0].set_title('Return vs N_BOOST'); ax[0].set_xlabel('N_BOOST'); ax[0].legend(); ax[0].grid(alpha=.3)
        ax[1].plot(nbs, [r['full_mdd'] for r in rows], 'o-', color='#0F6E56', label='full MDD%')
        ax[1].plot(nbs, [r['cpcv_worst_mdd'] for r in rows], 's--', color='#C0392B', label='CPCV worst MDD%')
        ax[1].axhline(LIMIT_MDD, ls='--', color='red', label='-20% limit'); ax[1].set_title('MDD vs N_BOOST'); ax[1].set_xlabel('N_BOOST'); ax[1].legend(); ax[1].grid(alpha=.3)
        fig.suptitle('N_BOOST CPCV Sweep (devledger 264 trades)', weight='bold')
        plt.tight_layout(); plt.savefig(PNG, dpi=110, bbox_inches='tight')
        print(f"[그래프] {os.path.basename(PNG)}")
    except Exception as e:
        print(f"[그래프] 생략(matplotlib 없음): {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
