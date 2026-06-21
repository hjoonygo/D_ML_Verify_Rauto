# [test_07Prj_Ch4_RunAWS_Stg6_DualSynthesis.py]
# 코드길이: 약 175줄 / 내부버전: ch4_stg6_dualsynth_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] TrendStack + SidewayDCA 두 확정봇을 '거래단위'로 한 계좌에 합성, 챔피언 듀얼봇이
#        ① 월 10%·매월양수에 얼마나 다가가나 ② -20% MDD를 지키나(월단위가 숨긴 intra-month 위험)
#        ③ 안전한 노출배분 계수 k는 얼마인가 를 측정(결과 주인공).
# [핵심발견 재현] 풀노출 공유계좌는 거래단위 MDD -23.5%로 -20% 위반(월단위 -12%가 숨김).
#                두 봇 동시보유 2.9%일에 합산노출 5.56x로 치솟는 게 원인 → 노출배분 필요.
# [근간] TrendStack devledger(264) + stg6 실행원장(exit_t용) + SidewayDCA 원장(86) + 엔진(참조).
# [복리] BTC $10,000. TS p=R×1.559×OPVnN×cut / SW p=R×4(EXP=4 확정, best.csv 일치).
# [한계] devledger 재구성·청산월귀속(±1개월)·동일계좌 단순합성 가정. 라이브 스트리밍 배선 아님(아래 §B).
# [§B 미해결] SidewayDCA 엔진은 배치 백테스트(698MB 데이터 필요)·스트리밍 on_bar 아님 →
#             라이브 BotPlugin 배선은 ADR9(사후원장스윕 vs 엔진내장 하드스탑) 결정 + PC데이터 필요.
#             본 합성은 docx 권장 '사후 원장 스윕' 통합아키텍처의 프로토타입.
# ── 함수 ── load_ts / load_sw / comp(p) / main()
# ─────────────────────────────────────────────────────────────────────────
import os
import csv
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
TS_DEV = os.path.join(HERE, "07Prj_Ch2_Stg2_TrendStack_OPVnNSweep_devledger.csv")
TS_EXEC = os.path.join(HERE, "stg6_levsweep_ledger.csv")
SW_LED = os.path.join(HERE, "07Prj_Ch2_SidewayDCARebuild_Stg1_ExpCutLiqSweep_ledger.csv")
RESULTS = os.path.join(HERE, "07Prj_Ch4_RunAWS_Stg6_DualSynthesis_results.csv")
PNG = os.path.join(HERE, "07Prj_Ch4_RunAWS_Stg6_DualSynthesis.png")
LIMIT = -20.0


def load_ts():
    t = pd.read_csv(TS_DEV); t['entry_t'] = pd.to_datetime(t['entry_t'])
    t['dev'] = pd.to_numeric(t['dev'], errors='coerce'); t['rdir'] = t['regime_dir'].replace(-9223372036854775808, np.nan)
    t['cut'] = np.where((t['regime'] == 'uptrend') & (t['side'] == -1), 0.0, 1.0)
    fire = (~t.dev.isna()) & (~t.rdir.isna()) & (t.dev.abs() >= 0.25)
    m = np.ones(len(t)); m[(fire & (t.side == t.rdir)).values] = 1.0; m[(fire & (t.side == -t.rdir)).values] = 0.6
    t['exp'] = 1.559 * m * t['cut']; t['p'] = t.R.values * t['exp']; t['bot'] = 'TS'
    te = pd.read_csv(TS_EXEC); te['exit_t'] = pd.to_datetime(te['exit_t'])
    t['exit_t'] = te['exit_t'].values[:len(t)]    # 동일 264거래 순서 → 보유시간 부여
    return t[['entry_t', 'exit_t', 'p', 'exp', 'bot']]


def load_sw():
    s = pd.read_csv(SW_LED); s['entry_t'] = pd.to_datetime(s['entry_t']); s['exit_t'] = pd.to_datetime(s['exit_t'])
    s['exp'] = 4.0; s['p'] = s.R * 4.0; s['bot'] = 'SW'
    return s[['entry_t', 'exit_t', 'p', 'exp', 'bot']]


def comp(p):
    bal = 10000.0; peak = 10000.0; mdd = 0.0; cur = [bal]
    for x in p:
        bal *= (1 + x); peak = max(peak, bal); mdd = min(mdd, bal / peak - 1); cur.append(bal)
    return (bal / 10000 - 1) * 100, mdd * 100, cur


def main():
    ts = load_ts(); sw = load_sw()
    both = pd.concat([ts, sw]).sort_values('exit_t').reset_index(drop=True)
    print("=" * 90)
    print("[test] 07Prj_Ch4_RunAWS_Stg6_DualSynthesis — TrendStack+SidewayDCA 거래단위 합성 ($10,000)")
    print("=" * 90)
    rsolo_t, mdd_t, _ = comp(ts.p.values); rsolo_s, mdd_s, _ = comp(sw.p.values)
    print(f"[단독] TrendStack {rsolo_t:+.0f}%/MDD{mdd_t:.1f}% · SidewayDCA {rsolo_s:+.0f}%/MDD{mdd_s:.1f}%")

    print("\n[A] 노출배분 스윕 (양 봇 동일계수 k) — -20% 한도 내 최대수익")
    print(f"{'k':>6}{'ret%':>10}{'MDD%':>9}{'판정':>8}")
    rows = []
    for k in np.round(np.arange(0.5, 1.01, 0.05), 2):
        r, mdd, _ = comp((both.p * k).values)
        flag = '한도내' if mdd > LIMIT else '위반'
        rows.append(dict(k=k, ret=round(r, 0), mdd=round(mdd, 1), ok=(mdd > LIMIT)))
        print(f"{k:>6}{r:>10.0f}{mdd:>9.1f}{flag:>8}")
    okrows = [x for x in rows if x['ok']]; rec = max(okrows, key=lambda z: z['ret'])
    full = rows[-1]
    print(f"  → 권장 k={rec['k']}: {rec['ret']:+.0f}% / MDD {rec['mdd']}% (한도내 최대) | 풀노출 k=1.0은 MDD {full['mdd']}% 위반")

    print("\n[B] 동시보유·합산노출 위험")
    allt = pd.concat([ts, sw])
    days = pd.date_range(both.exit_t.min().normalize(), both.exit_t.max().normalize(), freq='D')
    maxexp = 0.0; both_days = 0
    for d in days:
        op = allt[(allt.entry_t <= d) & (allt.exit_t >= d)]
        maxexp = max(maxexp, op.exp.sum())
        if op.bot.nunique() > 1:
            both_days += 1
    print(f"  최대 동시 합산노출 {maxexp:.2f}x (TS 1.56x/SW 4.0x) · 두 봇 동시보유 {both_days}/{len(days)}일 ({both_days/len(days)*100:.1f}%)")

    print("\n[C] 권장 k 월별 — 매월양수 점검")
    both['ym'] = both.exit_t.dt.to_period('M')
    idx = pd.period_range('2023-05', '2026-04', freq='M')
    mo = (both.assign(pk=both.p * rec['k']).groupby('ym').pk.sum()).reindex(idx, fill_value=0)
    print(f"  음수달 {int((mo < 0).sum())}/36 · 월평균 {mo.mean()*100:+.2f}% · 월복리MDD {comp(mo.values)[1]:.1f}%")

    print("-" * 90)
    print(f"[결론] 듀얼봇 GO이나 '풀노출 공유계좌'는 거래단위 MDD {full['mdd']}%로 한도 위반(월단위가 숨김).")
    print(f"       노출배분 k={rec['k']}로 {rec['ret']:+.0f}%/MDD{rec['mdd']}% 안전. 챔피언에 '노출배분 레이어' 필수.")
    print(f"VERDICT::듀얼 GO·노출배분필수 k={rec['k']}({rec['ret']:+.0f}%/{rec['mdd']}%)·풀노출k1.0위반({full['mdd']}%)·동시보유{both_days/len(days)*100:.1f}%")

    with open(RESULTS, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["k", "ret_pct", "mdd_pct", "within_limit"])
        for x in rows:
            w.writerow([x['k'], x['ret'], x['mdd'], x['ok']])
        w.writerow(["recommend", rec['k'], rec['ret'], rec['mdd']])
        w.writerow(["max_concurrent_exp", round(maxexp, 2), f"{both_days}/{len(days)}days", ""])
    print(f"[저장] {os.path.basename(RESULTS)}")

    try:
        import matplotlib
        matplotlib.use('Agg'); import matplotlib.pyplot as plt
        _, _, cf = comp(both.p.values); _, _, cr = comp((both.p * rec['k']).values); _, _, ch = comp((both.p * 0.5).values)
        fig, ax = plt.subplots(1, 2, figsize=(13, 4.6))
        ax[0].plot(cf, color='#C0392B', label=f"full k=1.0 ({full['ret']:+.0f}%/{full['mdd']}% VIOLATES)")
        ax[0].plot(cr, color='#0F6E56', lw=2, label=f"rec k={rec['k']} ({rec['ret']:+.0f}%/{rec['mdd']}%)")
        ax[0].plot(ch, color='#5D6D7E', label="50/50 k=0.5")
        ax[0].set_yscale('log'); ax[0].set_title('Trade-level combined equity'); ax[0].legend(fontsize=7); ax[0].grid(alpha=.3)
        ks = [x['k'] for x in rows]
        ax[1].plot(ks, [x['ret'] for x in rows], 'o-', color='#0F6E56', label='ret%')
        axb = ax[1].twinx(); axb.plot(ks, [x['mdd'] for x in rows], 's--', color='#C0392B', label='MDD%')
        axb.axhline(LIMIT, ls='--', color='red'); ax[1].axvline(rec['k'], ls=':', color='gray')
        ax[1].set_title('Exposure-scale sweep: max ret within -20%'); ax[1].set_xlabel('k')
        fig.suptitle('Dual-Bot Trade-Level Synthesis', weight='bold'); plt.tight_layout()
        plt.savefig(PNG, dpi=110, bbox_inches='tight'); print(f"[그래프] {os.path.basename(PNG)}")
    except Exception as e:
        print(f"[그래프] 생략: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
