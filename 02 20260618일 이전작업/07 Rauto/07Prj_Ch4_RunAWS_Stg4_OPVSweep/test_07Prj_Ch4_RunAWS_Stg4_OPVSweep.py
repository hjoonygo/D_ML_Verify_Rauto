# [test_07Prj_Ch4_RunAWS_Stg4_OPVSweep.py]
# 코드길이: 약 185줄 / 내부버전: ch4_stg4_opv_test_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 확정알파의 OPV(OPVnN 발동 dev 임계, 현재 0.25)를 0.10~0.60으로 스윕,
#        CPCV(조합형 교차검증)로 '0.25가 견고 최적인가'를 검증(결과 주인공).
#        N_BOOST=1.0·NMULT=0.6 고정. 검증된 봇 무수정 — devledger(264 실거래) 위에서 OPV만 재계산.
# [맥락] OPV는 'OPVnN을 몇 개 거래에 적용할지' 문턱. 낮추면 더 많이 축소(보수), 높이면 base에 근접.
#        N_BOOST=1.0이라 부스트는 중립 → 실효과는 '역회귀 거래를 얼마나 많이 0.6배로 줄이나'.
# [근간] devledger 264거래 / bot_trendstack_signal.py(OPV 35줄·opvnn_mult) / trendstack_poc.py 동봉.
# [복리] BTC선물 $10,000 시작·계좌잔금 복리. p=R×노출, 노출=EXP×OPVnN배수×업트렌드숏컷.
# [CPCV] 264거래 시간순 6그룹 → C(6,2)=15 조합 부분표본 복리·MDD → 견고성(최악·평균·한도위반).
# [한계] devledger 재구성(절대수치 근사). 'OPV 상대비교'가 목적. + n_fire(발동수) 추적.
# ── 함수 ── load / p_of(df,opv) / comp(p) / cpcv(p,k,r) / main()
# ── 상수 ── EXP=1.559 / NBOOST=1.00 / NMULT=0.60 / START=$10,000 / LIMIT_MDD=-20%
# ─────────────────────────────────────────────────────────────────────────
import os
import csv
import itertools
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DL = os.path.join(HERE, "07Prj_Ch2_Stg2_TrendStack_OPVnNSweep_devledger.csv")
RESULTS = os.path.join(HERE, "07Prj_Ch4_RunAWS_Stg4_OPVSweep_results.csv")
PNG = os.path.join(HERE, "07Prj_Ch4_RunAWS_Stg4_OPVSweep.png")

EXP = 1.559
NBOOST = 1.00
NMULT = 0.60
START = 10000.0
LIMIT_MDD = -20.0
OPVS = [0.10, 0.15, 0.25, 0.40, 0.60]
BASELINE = 0.25


def load():
    d = pd.read_csv(DL)
    d['entry_t'] = pd.to_datetime(d['entry_t']); d['year'] = d['entry_t'].dt.year
    d['dev'] = pd.to_numeric(d['dev'], errors='coerce')
    d['rdir'] = d['regime_dir'].replace(-9223372036854775808, np.nan)
    d['cut'] = np.where((d['regime'] == 'uptrend') & (d['side'] == -1), 0.0, 1.0)
    return d


def p_of(d, opv):
    dev = d['dev'].values; rdir = d['rdir'].values; side = d['side'].values
    m = np.ones(len(d))
    fire = (~np.isnan(dev)) & (~np.isnan(rdir)) & (np.abs(dev) >= opv)
    same = fire & (side == rdir)
    opp = fire & (side == -rdir)
    m[same] = NBOOST
    m[opp] = NMULT
    exp = EXP * m * d['cut'].values
    return d['R'].values * exp, int(fire.sum()), int(opp.sum())


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
    print("=" * 100)
    print("[test] 07Prj_Ch4_RunAWS_Stg4_OPVSweep — OPV 0.10~0.60 · CPCV 견고성 ($10,000 복리)")
    print("=" * 100)
    print(f"{'OPV':>6}{'n_fire':>8}{'n_reduce':>9}{'full_ret%':>10}{'full_mdd%':>10}{'Calmar':>8}"
          f"{'cpcv_mean':>10}{'cpcv_worstMDD':>14}{'breach':>7}")
    for ov in OPVS:
        p, nfire, nred = p_of(d, ov)
        ret, mdd, bal = comp(p)
        cal = ret / abs(mdd) if mdd < 0 else float('nan')
        cv = cpcv(p)
        yr = {y: round(comp(p[(d['year'] == y).values])[0], 1) for y in [2023, 2024, 2025, 2026]}
        rows.append(dict(OPV=ov, n_fire=nfire, n_reduce=nred, full_ret=round(ret, 1), full_mdd=round(mdd, 1),
                         calmar=round(cal, 1), final_bal=round(bal, 0), cpcv_mean=cv['mean'],
                         cpcv_worst_ret=cv['worst_ret'], cpcv_worst_mdd=cv['worst_mdd'], cpcv_breach=cv['breach'],
                         y2023=yr[2023], y2024=yr[2024], y2025=yr[2025], y2026=yr[2026]))
        print(f"{ov:>6}{nfire:>8}{nred:>9}{ret:>10.1f}{mdd:>10.1f}{cal:>8.1f}{cv['mean']:>10}"
              f"{cv['worst_mdd']:>14}{cv['breach']:>7}")

    base = next(r for r in rows if r['OPV'] == BASELINE)
    zero = [r for r in rows if r['cpcv_breach'] == 0]
    robust = max(zero, key=lambda r: r['full_ret']) if zero else None
    best_cal = max(rows, key=lambda r: r['calmar'])
    print("-" * 100)
    print(f"[기준] OPV=0.25(확정) : {base['full_ret']}% / full MDD {base['full_mdd']}% / Calmar {base['calmar']} "
          f"/ CPCV최악MDD {base['cpcv_worst_mdd']}% · 한도위반 {base['cpcv_breach']} (발동 {base['n_fire']}건)")
    if robust:
        print(f"[견고쿠션] OPV={robust['OPV']} : {robust['full_ret']}% / MDD {robust['full_mdd']}% / "
              f"Calmar {robust['calmar']} / CPCV최악MDD {robust['cpcv_worst_mdd']}% · 한도위반 0")
    print(f"[Calmar최고] OPV={best_cal['OPV']} : {best_cal['full_ret']}% / MDD {best_cal['full_mdd']}% / "
          f"Calmar {best_cal['calmar']} / CPCV최악MDD {best_cal['cpcv_worst_mdd']}% · 한도위반 {best_cal['cpcv_breach']}")
    print(f"[해석] OPV↓=더 많이 줄임(보수,수익↓MDD↓) / OPV↑=base근접(수익↑MDD↑). NMULT와 같은 축이라 함께 정함.")
    verdict = (f"기준 OPV=0.25 CPCV위반 {base['cpcv_breach']} / 견고쿠션 OPV={robust['OPV'] if robust else 'NA'} "
               f"/ Calmar최고 OPV={best_cal['OPV']} → NMULT와 함께 결정")
    print(f"VERDICT::{verdict}")

    with open(RESULTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"[저장] {os.path.basename(RESULTS)}")

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        ovs = [r['OPV'] for r in rows]
        fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
        ax[0].plot(ovs, [r['full_ret'] for r in rows], 'o-', color='#0F6E56', label='full ret%')
        ax2 = ax[0].twinx(); ax2.plot(ovs, [r['n_fire'] for r in rows], '^:', color='#5D6D7E', label='n_fire')
        ax[0].axvline(BASELINE, ls=':', color='gray'); ax[0].set_title('Return & OPVnN-fire count vs OPV'); ax[0].set_xlabel('OPV'); ax[0].set_ylabel('ret%'); ax2.set_ylabel('n_fire')
        ax[0].grid(alpha=.3)
        ax[1].plot(ovs, [r['full_mdd'] for r in rows], 'o-', color='#0F6E56', label='full MDD%')
        ax[1].plot(ovs, [r['cpcv_worst_mdd'] for r in rows], 's--', color='#C0392B', label='CPCV worst MDD%')
        ax[1].axhline(LIMIT_MDD, ls='--', color='red', label='-20% limit'); ax[1].axvline(BASELINE, ls=':', color='gray'); ax[1].set_title('MDD vs OPV'); ax[1].set_xlabel('OPV'); ax[1].legend(); ax[1].grid(alpha=.3)
        fig.suptitle('OPV CPCV Sweep (devledger 264 trades, N_BOOST=1.0 / NMULT=0.6 fixed)', weight='bold')
        plt.tight_layout(); plt.savefig(PNG, dpi=110, bbox_inches='tight')
        print(f"[그래프] {os.path.basename(PNG)}")
    except Exception as e:
        print(f"[그래프] 생략: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
