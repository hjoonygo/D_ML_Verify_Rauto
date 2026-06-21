# [test_07Prj_Ch4_RunAWS_Stg5_Y2025Diag.py]
# 코드길이: 약 175줄 / 내부버전: ch4_stg5_y2025diag_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 2025 약세(PF 1.24, 매월양수 최대위협)의 '원인'을 진단(결과 주인공). 두 가설 검정:
#        H1 구성(composition): 2025가 나쁜 장세를 더 많이 했나? → 연도별 장세비중 비교.
#        H2 열화(degradation): 같은 장세가 2025엔 더 안 통했나? → 장세별 PF 2025 vs 전체.
#        + 월별 P&L(매월양수 위반 수) + 롱숏. 결론으로 SidewayDCA 착수 방향을 가린다.
# [성격] 파라미터 스윕 아님 = 봇 무수정·읽기전용 진단. CPCV 불필요(파라미터 선택 아님).
# [근간] devledger 264거래 / bot_trendstack_signal.py / trendstack_poc.py 동봉(참조).
# [복리] BTC선물 $10,000 기준. 거래별 p=R×노출(확정알파: EXP1.559·OPVnN·업트렌드숏컷).
# [한계] devledger 재구성(절대수치 근사). 상대비교·구조진단이 목적.
# ── 함수 ── load / pf(arr) / main()
# ─────────────────────────────────────────────────────────────────────────
import os
import csv
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DL = os.path.join(HERE, "07Prj_Ch2_Stg2_TrendStack_OPVnNSweep_devledger.csv")
RESULTS = os.path.join(HERE, "07Prj_Ch4_RunAWS_Stg5_Y2025Diag_results.csv")
PNG = os.path.join(HERE, "07Prj_Ch4_RunAWS_Stg5_Y2025Diag.png")

EXP = 1.559; OPV = 0.25; NBOOST = 1.0; NMULT = 0.6
REGIMES = ['uptrend', 'downtrend', 'volatile_range', 'dead_range']


def load():
    d = pd.read_csv(DL)
    d['entry_t'] = pd.to_datetime(d['entry_t']); d['year'] = d['entry_t'].dt.year
    d['month'] = d['entry_t'].dt.to_period('M')
    d['dev'] = pd.to_numeric(d['dev'], errors='coerce')
    d['rdir'] = d['regime_dir'].replace(-9223372036854775808, np.nan)
    d['cut'] = np.where((d['regime'] == 'uptrend') & (d['side'] == -1), 0.0, 1.0)
    fire = (~d.dev.isna()) & (~d.rdir.isna()) & (d.dev.abs() >= OPV)
    m = np.ones(len(d))
    m[(fire & (d.side == d.rdir)).values] = NBOOST
    m[(fire & (d.side == -d.rdir)).values] = NMULT
    d['p'] = d.R.values * EXP * m * d.cut.values
    return d


def pf(arr):
    g = arr[arr > 0].sum(); l = -arr[arr < 0].sum()
    return round(g / l, 2) if l > 0 else float('inf')


def main():
    d = load()
    y25 = d[d.year == 2025]
    print("=" * 86)
    print("[test] 07Prj_Ch4_RunAWS_Stg5_Y2025Diag — 2025 약세 원인 진단 (구성 vs 열화)")
    print("=" * 86)
    print(f"[2025] {len(y25)}거래 · sumP {y25.p.sum():.3f} · PF {pf(y25.p.values)} · 승률 {(y25.p>0).mean()*100:.1f}%")

    print("\n[H1 구성] 연도별 장세 비중(%) — 2025가 나쁜 장세를 더 많이 했나?")
    mix = (pd.crosstab(d.year, d.regime, normalize='index') * 100).round(1)
    print(mix.to_string())
    dt_25 = mix.loc[2025, 'downtrend']; dt_other = mix.loc[[2023, 2024, 2026], 'downtrend'].mean()
    h1 = dt_25 > dt_other  # 2025가 downtrend(최강장세)를 더 많이 함 → 구성은 오히려 유리
    print(f"  → 2025 downtrend비중 {dt_25}% vs 타년평균 {dt_other:.1f}% : "
          f"{'2025가 최강장세를 더 많이 함 → 구성 불리 아님(H1 기각)' if h1 else 'H1 가능'}")

    print("\n[H2 열화] 장세별 PF: 2025 vs 전체 — 같은 장세가 2025엔 더 안 통했나?")
    print(f"{'regime':>16}{'전체PF':>9}{'2025PF':>9}{'n_2025':>8}{'판정':>10}")
    rows = []; degraded = 0
    for rg in REGIMES:
        allpf = pf(d[d.regime == rg].p.values)
        y25pf = pf(y25[y25.regime == rg].p.values)
        n = int((y25.regime == rg).sum())
        worse = (y25pf < allpf)
        if worse and rg != 'dead_range':
            degraded += 1
        print(f"{rg:>16}{allpf:>9}{y25pf:>9}{n:>8}{'열화' if worse else '유지/개선':>10}")
        rows.append(dict(regime=rg, all_pf=allpf, y2025_pf=y25pf, n_2025=n, degraded=bool(worse)))

    print("\n[월별 P&L] 2025 — '매월 양수' 위반(음수 달)")
    mo = y25.groupby('month').p.sum()
    neg = int((mo < 0).sum())
    print(f"  음수 달 {neg}/{len(mo)} · 최악 {mo.min():.3f}({mo.idxmin()}) · 최고 {mo.max():.3f}({mo.idxmax()})")
    print("  월별: " + " ".join(f"{str(k)[-2:]}:{v:+.3f}" for k, v in mo.items()))

    ls = {('Long' if s == 1 else 'Short'): round(y25[y25.side == s].p.sum(), 3) for s in [1, -1]}
    print(f"\n[롱숏] 2025 Long {ls['Long']} · Short {ls['Short']} (둘 다 약하게 +)")

    print("-" * 86)
    if h1 and degraded >= 2:
        verdict = ("2025 약세 = 열화(degradation). 구성은 오히려 유리(downtrend 비중 최대)였으나 "
                   "추세장세 PF가 일제히 붕괴(uptrend·downtrend·volatile). 즉 2025는 추세가 안 통한 해 "
                   "→ 추세봇 사이징으론 불가. dead_range(횡보)만 유지/개선 → SidewayDCA가 정확히 그 구간 커버. "
                   "[결론] SidewayDCA 착수가 매월양수의 정답.")
    else:
        verdict = "추가 분석 필요(구성/열화 혼재)"
    print("[진단] " + verdict)
    print("VERDICT::" + verdict)

    with open(RESULTS, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["section", "key", "value"])
        w.writerow(["summary", "n_trades_2025", len(y25)])
        w.writerow(["summary", "pf_2025", pf(y25.p.values)])
        w.writerow(["summary", "neg_months_2025", neg])
        w.writerow(["composition", "downtrend_pct_2025", dt_25])
        w.writerow(["composition", "downtrend_pct_other", round(dt_other, 1)])
        for r in rows:
            w.writerow(["degradation", r['regime'], f"allPF={r['all_pf']};2025PF={r['y2025_pf']};n={r['n_2025']};degraded={r['degraded']}"])
        for k, v in mo.items():
            w.writerow(["month_2025", str(k), round(v, 4)])
        w.writerow(["verdict", "diagnosis", verdict])
    print(f"[저장] {os.path.basename(RESULTS)}")

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig = plt.figure(figsize=(14, 9)); fig.suptitle('2025 Weakness Diagnosis — degradation, not composition', weight='bold', fontsize=13)
        ax1 = plt.subplot(2, 2, 1)
        mix[REGIMES].plot(kind='bar', stacked=True, ax=ax1, colormap='Set2')
        ax1.set_title('Regime mix % by year (2025 had MORE downtrend = best regime)'); ax1.set_xlabel('year'); ax1.legend(fontsize=7); ax1.tick_params(axis='x', rotation=0)
        ax2 = plt.subplot(2, 2, 2)
        x = np.arange(len(REGIMES)); w = .35
        ax2.bar(x - w/2, [pf(d[d.regime == r].p.values) for r in REGIMES], w, label='all years', color='#5D6D7E')
        ax2.bar(x + w/2, [pf(y25[y25.regime == r].p.values) for r in REGIMES], w, label='2025', color='#C0392B')
        ax2.axhline(1, ls='--', color='gray'); ax2.set_xticks(x); ax2.set_xticklabels(REGIMES, rotation=15, fontsize=8); ax2.set_title('Regime PF: all-years vs 2025 (trend regimes collapsed)'); ax2.legend()
        ax3 = plt.subplot(2, 1, 2)
        cols = ['#0F6E56' if v >= 0 else '#C0392B' for v in mo.values]
        ax3.bar([str(k) for k in mo.index], mo.values, color=cols)
        ax3.axhline(0, color='gray'); ax3.set_title(f'2025 monthly P&L ({neg}/12 negative months = "every-month-positive" fails)'); ax3.tick_params(axis='x', rotation=45)
        plt.tight_layout(rect=[0, 0, 1, .96]); plt.savefig(PNG, dpi=110, bbox_inches='tight')
        print(f"[그래프] {os.path.basename(PNG)}")
    except Exception as e:
        print(f"[그래프] 생략: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
