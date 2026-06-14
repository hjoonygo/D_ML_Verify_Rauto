# -*- coding: utf-8 -*-
# [파일명] test_07Prj_Ch4_RunAWS_Stg11_RegimeAllocSweep.py
# 코드길이: 약 190줄 | 내부버전: ch4_stg11_regimealloc_v1
# ─────────────────────────────────────────────────────────────────────────────
# [목적 — 고딩 설명, 캡틴 확정 설계]
#   고정 k=0.77 대신 '현재 장세 상태'에 반응하는 봇별 가중(상태반응형, 예측형 금지)을
#   사전명세 고정표(스윕 금지, 0.5 한 점)로 측정한다.
#   A안: TS가중 = devledger regime=='dead_range' → ×0.5 (61/264건. ★라벨 근사 플래그:
#        regime은 사후 라벨 계열 — 측정 전용 상한 근사, 실시간 사용 금지 §1)
#        SW가중 = 진입시각 ER>=0.40 → ×0.5 (06PrjCh6Stg7 TrendGate 11줄 'ER_TREND=0.40
#        표준값 고정, Ch5 4/4년 견고' 인용. ER은 TrendStack 박제 신호엔진 compute_signals의
#        er을 7h봉에서 산출, 진입시각 이전 '마감된' 7h봉 값 asof — 과거봉만, 인과)
#   합성 = Stg9 정식 방식(Stg6 함수 박제 import, exit_t순, k=0.77 고정).
#   판정 가이드(캡틴): 개선 = MDD 개선 or 음수달 감소. 효과 있으면 CPCV+k재스윕,
#   없으면 C안(변동성 타게팅 한 점). 개선 +50%p 미만 or CPCV 비견고 → '기각, 고정 k 유지'.
#   상한 참고(회의실): 월단위 오라클 +234%p, 우세봇 지속률 29%(모멘텀식 역신호).
# [근간] Stg6 test(합성)+devledger264+stg6실행원장+박제SW원장 / causal_ledger(§8 c4964c55) /
#        trendstack_signal_engine(§8 c9d784bf, ER 산출) / Merged_Data(상위, 7h 리샘플)
# [근사 명시] 7h 리샘플은 pandas resample('420min', origin 기본값) — 측정 전용.
# [Out] stg11_result.txt / stg11_summary.csv / stg11_compare.png
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
import trendstack_signal_engine as TE                      # noqa: E402  ER 산출(박제)

CAUSAL = os.path.join(HERE, "causal_ledger.csv")
DEVLED = os.path.join(BOTS, "07Prj_Ch2_Stg2_TrendStack_OPVnNSweep_devledger.csv")
K_FIX = 0.77
ER_TREND = 0.40            # 06PrjCh6Stg7 11줄 표준값(캡틴 채택 — 0.45는 회의실 오기)
W_POINT = 0.5              # 한 점 측정(스윕 금지)
MDD_TARGET = -19.5
OUT_TXT = os.path.join(HERE, "stg11_result.txt")
OUT_CSV = os.path.join(HERE, "stg11_summary.csv")
OUT_PNG = os.path.join(HERE, "stg11_compare.png")


def load_data_7h():
    # 상위 Merged 1분봉 → 7h 리샘플 → 박제 compute_signals → (7h마감시각, er)
    for d in [os.path.dirname(HERE), r"D:\ML\verify"]:
        p = os.path.join(d, "Merged_Data_with_Regime_Features.csv")
        if os.path.exists(p):
            break
    df = pd.read_csv(p, usecols=['timestamp', 'open', 'high', 'low', 'close'],
                     index_col='timestamp', parse_dates=True).sort_index()
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)              # 엔진 load_1m과 동일(tz 제거)
    df7 = df.resample('420min', label='left', closed='left').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
    sig = TE.compute_signals(df7)
    er = np.asarray(sig['er'], float)
    close_t = df7.index + pd.Timedelta(minutes=420)        # 봉 '마감' 시각(인과 asof 기준)
    return pd.Series(er, index=close_t)


def metrics(both, w, k, label):
    p = (both.p * w * k).values
    r, m, _ = S6.comp(p)
    ym = both.exit_t.dt.to_period('M')
    idx = pd.period_range('2023-05', '2026-04', freq='M')
    mo = pd.Series(p, index=both.index).groupby(ym).sum().reindex(idx, fill_value=0.0)
    negm = int((mo < 0).sum())
    return dict(cell=label, ret_pct=round(r, 1), mdd_pct=round(m, 2), neg_months=negm)


def cpcv6(both, w, k):
    p = (both.p * w * k).values
    groups = np.array_split(np.arange(len(p)), 6)
    import itertools
    rets = []; mdds = []
    for combo in itertools.combinations(range(6), 2):
        idx = np.sort(np.concatenate([groups[g] for g in combo]))
        r, m, _ = S6.comp(p[idx])
        rets.append(r); mdds.append(m)
    return dict(mean=round(float(np.mean(rets)), 1), worst_ret=round(min(rets), 1),
                worst_mdd=round(min(mdds), 1), breach=int(sum(1 for m in mdds if m <= -20.0)))


def main():
    lines = []
    def log(s):
        print(s); lines.append(s)

    # 정식 합성(인과)
    S6.SW_LED = CAUSAL
    ts = S6.load_ts(); sw = S6.load_sw()

    # TS 가중(라벨 근사 — 측정 전용)
    dl = pd.read_csv(DEVLED)
    assert len(dl) == len(ts)
    w_ts = np.where(dl['regime'].values == 'dead_range', W_POINT, 1.0)
    log(f"[A-TS] dead_range×{W_POINT}: {int((w_ts < 1).sum())}/264건 ★라벨근사(사후 라벨 계열, 측정 전용 — 실시간 사용 금지 §1)")

    # SW 가중(ER>=0.40, 인과 asof)
    er7 = load_data_7h()
    ents = pd.to_datetime(sw['entry_t'].values)
    pos_idx = er7.index.searchsorted(ents, side='right') - 1
    er_at = np.where(pos_idx >= 0, er7.values[np.clip(pos_idx, 0, None)], np.nan)
    w_sw = np.where(np.nan_to_num(er_at, nan=0.0) >= ER_TREND, W_POINT, 1.0)
    log(f"[A-SW] ER>={ER_TREND}×{W_POINT}: {int((w_sw < 1).sum())}/{len(sw)}건 (ER=박제 compute_signals, 마감 7h봉 asof)")

    both = pd.concat([ts.assign(w=w_ts), sw.assign(w=w_sw)]).sort_values('exit_t').reset_index(drop=True)
    base = metrics(both, 1.0, K_FIX, f"BASE_fixed_k{K_FIX}")
    a = metrics(both, both.w.values, K_FIX, f"A_regime_w{W_POINT}_k{K_FIX}")
    rows = [base, a]
    log(f"\n[대조 k={K_FIX}] {'cell':<26}{'ret%':>10}{'MDD%':>9}{'음수달':>7}")
    for r in rows:
        log(f"          {r['cell']:<26}{r['ret_pct']:>10}{r['mdd_pct']:>9}{r['neg_months']:>7}/36")

    improved = (a['mdd_pct'] > base['mdd_pct']) or (a['neg_months'] < base['neg_months'])
    big_enough = (a['ret_pct'] - base['ret_pct']) >= 50.0 or improved  # ret -50%p 이상 후퇴 아니어야 의미
    verdict_parts = []

    if improved:
        cvb = cpcv6(both, 1.0, K_FIX); cva = cpcv6(both, both.w.values, K_FIX)
        log(f"\n[CPCV 6그룹15경로] BASE mean {cvb['mean']}% worstMDD {cvb['worst_mdd']}% breach {cvb['breach']} | "
            f"A안 mean {cva['mean']}% worstMDD {cva['worst_mdd']}% breach {cva['breach']}")
        yrs = {}
        for y in [2023, 2024, 2025, 2026]:
            sel = both.exit_t.dt.year == y
            rb, _, _ = S6.comp((both.p[sel] * K_FIX).values)
            ra, _, _ = S6.comp((both.p[sel] * both.w[sel] * K_FIX).values)
            yrs[y] = (round(rb, 1), round(ra, 1))
        log("[년도별 ret%] " + " | ".join(f"{y}: base {b} → A {a2}" for y, (b, a2) in yrs.items()))
        # k 상향 여지: 가중 적용 상태로 'MDD -19.5% 이내 최대 k'
        best_k = None
        for k in np.round(np.arange(0.70, 0.901, 0.01), 2):
            m = metrics(both, both.w.values, k, f"k{k}")
            if m['mdd_pct'] > MDD_TARGET:
                best_k = m | {'k': k}
        if best_k:
            log(f"[k 상향 여지] A안 가중 시 MDD {MDD_TARGET}% 이내 최대 k={best_k['k']} → "
                f"ret {best_k['ret_pct']}% / MDD {best_k['mdd_pct']}%")
            rows.append(dict(cell=f"A_w_maxk{best_k['k']}", ret_pct=best_k['ret_pct'],
                             mdd_pct=best_k['mdd_pct'], neg_months=best_k['neg_months']))
        robust = cva['breach'] == 0
        gain = (best_k['ret_pct'] if best_k else a['ret_pct']) - base['ret_pct']
        adopt = robust and gain >= 50.0
        verdict_parts.append(f"A안 개선O(MDD {base['mdd_pct']}→{a['mdd_pct']} 음수달 {base['neg_months']}→{a['neg_months']})")
        verdict_parts.append(f"CPCV {'견고' if robust else '비견고'} | 이득 {gain:+.1f}%p → "
                             f"{'후보 채택(캡틴 승인 사안)' if adopt else '기각, 고정 k 유지(가이드 미달)'}")
    else:
        verdict_parts.append(f"A안 개선X(MDD {base['mdd_pct']}→{a['mdd_pct']}, 음수달 {base['neg_months']}→{a['neg_months']})")
        # C안: 변동성 타게팅(직전 60일 실현변동성 역수, 한 점)
        #   운용화 명시: 봇별 일간손익(exit귀속 p 합) 시계열의 직전 60일 표준편차 σ60,
        #   w_i = clip(σ_med/σ60, 0.5, 1.5). σ_med=그 봇 전기간 σ60 중앙값. 이력<60일이면 w=1.
        both2 = both.copy()
        w_c = np.ones(len(both2))
        for b in ['TS', 'SW']:
            sel = (both2.bot == b).values
            sub = both2[sel]
            daily = sub.assign(d=sub.exit_t.dt.normalize()).groupby('d').p.sum()
            days = pd.date_range(both2.exit_t.min().normalize(), both2.exit_t.max().normalize(), freq='D')
            dser = daily.reindex(days, fill_value=0.0)
            roll = dser.rolling(60, min_periods=60).std().shift(1)   # 직전 60일(당일 제외)
            med = float(roll.dropna().median())
            for i, (idx_, t) in enumerate(zip(both2.index[sel], sub.exit_t)):
                s60 = roll.get(t.normalize(), np.nan)
                if not np.isnan(s60) and s60 > 0:
                    w_c[idx_] = float(np.clip(med / s60, 0.5, 1.5))
        c = metrics(both2, w_c, K_FIX, f"C_voltarget_k{K_FIX}")
        rows.append(c)
        log(f"\n[C안 변동성타게팅] ret {c['ret_pct']}% / MDD {c['mdd_pct']}% / 음수달 {c['neg_months']}/36 "
            f"(가중범위 {w_c.min():.2f}~{w_c.max():.2f})")
        c_improved = (c['mdd_pct'] > base['mdd_pct']) or (c['neg_months'] < base['neg_months'])
        if c_improved:
            cvc = cpcv6(both2, w_c, K_FIX)
            robust = cvc['breach'] == 0
            gain = c['ret_pct'] - base['ret_pct']
            log(f"[C-CPCV] mean {cvc['mean']}% worstMDD {cvc['worst_mdd']}% breach {cvc['breach']}")
            adopt = robust and gain >= 50.0
            verdict_parts.append(f"C안 개선O | CPCV {'견고' if robust else '비견고'} | 이득 {gain:+.1f}%p → "
                                 f"{'후보 채택(캡틴 승인 사안)' if adopt else '기각, 고정 k 유지'}")
        else:
            verdict_parts.append(f"C안도 개선X(MDD {c['mdd_pct']}, 음수달 {c['neg_months']}) → 기각, 고정 k={K_FIX} 유지")

    verdict = "VERDICT Stg11 | " + " | ".join(verdict_parts) + " | 오라클상한 +234%p·지속률29%(회의실 참고)"
    log("\n" + verdict)
    pd.DataFrame(rows).to_csv(OUT_CSV, index=False, encoding='utf-8-sig')
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    try:
        import matplotlib
        matplotlib.use('Agg'); import matplotlib.pyplot as plt
        labs = [r['cell'] for r in rows]
        fig, ax = plt.subplots(1, 3, figsize=(13, 4))
        for i, (key, ttl) in enumerate([('ret_pct', 'Return %'), ('mdd_pct', 'MDD %'), ('neg_months', 'Negative months /36')]):
            ax[i].bar(range(len(rows)), [r[key] for r in rows],
                      color=['#5D6D7E', '#0F6E56', '#854F0B', '#C0392B'][:len(rows)])
            ax[i].set_xticks(range(len(rows))); ax[i].set_xticklabels(labs, rotation=20, fontsize=7)
            ax[i].set_title(ttl); ax[i].grid(alpha=.3, axis='y')
        fig.suptitle('Stg11 Regime-Reactive Allocation vs Fixed k=0.77 (causal dual, official synth)')
        plt.tight_layout(); plt.savefig(OUT_PNG, dpi=110)
        print(f"[그래프] {os.path.basename(OUT_PNG)}")
    except Exception as e:
        print(f"[그래프] 생략: {e}")


if __name__ == "__main__":
    main()
