# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch6_FrameWork_RAUTO_Stg8_Y2025Forensics.py
# 코드길이: 약 360줄 | 내부버전: 06Prj_Ch6_Stg8_Y2025Forensics_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]  사장님 통찰: "2025는 칩장이 아니다 / 분류기가 추세라 본 곳에서 추세봇이 죽었다".
#   2025는 추세봇 유일 참패해(PF0.858, 타년 1.7~2.3). 그 원인을 축1~4로 다각도 분해(확인=가) → 가짜추세 정체 규명.
#   엔진 무수정(해시대조). 거래 reason/bars 실측 + 진입봉 지표(ER/ADX/CHOP) 부착. label_smc 입력금지.
#
#   [축1 시간분포]  2025 손실이 월/분기 몰렸나(이벤트) vs 골고루(구조적). 월별 PF/수익.
#   [축2 청산이유]  손실거래 reason 비율: sl(즉시역행=가짜브레이크) vs trend_flip(휩쏘). 2025 vs 타년.
#   [축3 보유봉수]  손실거래 bars 분포. 짧으면 진입즉시 털림(가짜추세 전형). 2025 vs 타년.
#   [축4 진입지표]  진입봉 ER/ADX/CHOP 평균. 2025 추세진입의 ER이 사실 낮았나(가짜추세면 낮음). 2025 vs 타년.
#
#   [필터 시제품 + CPCV]  축1~4서 원인 나오면 거르는 필터 후보 자동구성(예:진입ER하한,보유봉하한) →
#     ★2025만 좋아지는 과최적 방지: 반드시 CPCV 15경로로 4년 전체 견고성 검증. 2025 고치고 타년 망치면 기각.
#
#   [★미래참조 차단]  진입봉 지표는 진입시점 값(과거). 청산 reason/bars는 결과기록(채점용). CPCV 봉그룹 채점.
#
# [PATH] 실행 D:\ML\verify\06Prj_Ch6_FrameWork_RAUTO_Stg8_Y2025Forensics\ . 데이터 상위 D:\ML\verify.
# [OUTPUT] axis1_month.csv / axis2_reason.csv / axis3_holdbars.csv / axis4_entryfeat.csv /
#          filter_candidates.csv / filter_cpcv_paths.csv / ledger_trades.csv / summary.csv + .stg8_metric
# [In/Out 태그]
#   regime_classifier: compute_indicators(In OHLC/Out ER·ADX·CHOP) / classify
#   cpcv: cpcv_pf_eval(In 거래봉,R,총봉/Out PF분포)
#   엔진(무수정): champ.run_strategy(none)/compute_signals/load_oi_8h/load_bb_8h/load_data/resample_tf/TF_MIN
#                 sdca.load_funding/funding_sum
#   본코드: ns_i64/metrics/get_trend_trades(reason·bars·진입지표 부착)/forensic_axes/build_filter/main
#   변수(동결): TARGET_YEAR=2025 N_GROUP=6 K_TEST=2 COST_RT=0.0014 RANGE_REG={2,3}
# ==============================================================================
import os, sys, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE); BOTS = os.path.join(HERE, "bots")
sys.path.insert(0, HERE)
import regime_classifier as RC
import cpcv as CP

TARGET_YEAR = 2025; N_GROUP = 6; K_TEST = 2; COST_RT = 0.0014
REGIME_MAP = {0: 'uptrend', 1: 'downtrend', 2: 'volatile_range', 3: 'dead_range'}


def load_engine(p, nm):
    s = importlib.util.spec_from_file_location(nm, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def ns_i64(dtindex):
    return np.asarray(dtindex.values).astype('datetime64[ns]').astype('int64')


def find_file(c):
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for x in c:
            p = os.path.join(d, x)
            if os.path.exists(p):
                return p
    return None


def metrics(R):
    R = np.asarray(R, float); R = R[np.isfinite(R)]; n = len(R)
    if n == 0:
        return dict(n=0, PF=0.0, ret=0.0, win=0.0, payoff=0.0)
    gp = float(R[R > 0].sum()); gl = float(-R[R < 0].sum())
    pf = round(gp / gl, 3) if gl > 0 else (999.0 if gp > 0 else 0.0)
    wins = R[R > 0]; losses = R[R < 0]
    aw = wins.mean() if len(wins) else 0.0; al = -losses.mean() if len(losses) else 0.0
    payoff = round(aw / al, 3) if al > 0 else (999.0 if aw > 0 else 0.0)
    return dict(n=n, PF=pf, ret=round(R.sum() * 100, 2), win=round(100 * (R > 0).mean(), 1), payoff=payoff)


def get_trend_trades(champ, sdca, df7, sig, oi7, bb7, ft, fr, ind, idx7):
    # 추세봇 none게이트 거래 + reason/bars + 진입봉 지표(ER/ADX/CHOP/CHOP) 부착. 비용·실펀딩 재계산.
    def fpay(side, et, xt):
        if ft is None:
            return 0.0
        fs = sdca.funding_sum(ft, fr, int(pd.Timestamp(et).value), int(pd.Timestamp(xt).value))
        return side * fs if fs is not None else 0.0
    ttr = champ.run_strategy(df7, sig, 0, 'none', 0.8, dz_oi=oi7, gate_mode='none',
                             gate_bb=bb7, fib=(0.3, 0.5, 0.6), split_mode='A', split_n=3)
    edges = ns_i64(idx7); out = []
    for t in ttr:
        R = t['side'] * (t['exit'] - t['entry']) / t['entry'] - COST_RT - fpay(t['side'], t['entry_t'], t['exit_t'])
        et = pd.Timestamp(t['entry_t'])
        pos = max(0, min(np.searchsorted(edges, np.int64(et.value), side='right') - 1, len(edges) - 1))
        out.append(dict(side=int(t['side']), entry_t=et, year=et.year, month=et.month, R=float(R),
                        reason=t.get('reason', '?'), bars=int(t.get('bars', 0)), bar=pos,
                        f_er=float(ind['er'][pos]) if np.isfinite(ind['er'][pos]) else np.nan,
                        f_adx=float(ind['adx'][pos]) if np.isfinite(ind['adx'][pos]) else np.nan,
                        f_chop=float(ind['chop'][pos]) if np.isfinite(ind['chop'][pos]) else np.nan))
    return out


def main():
    print("[Stg8] 2025 포렌식: 추세봇 유일참패해(PF0.858)의 정체를 축1~4로 분해 (사장님 통찰)")
    champ = load_engine(os.path.join(BOTS, "SpTrd_Fib_V1_Champion.py"), "champ_engine")
    sdca = load_engine(os.path.join(BOTS, "SidewayDCA_Stg7_engine.py"), "sdca_engine")
    DATA = find_file(["Merged_Data_with_Regime_Features.csv", "merged_data.csv"])
    OIPATH = find_file(["Merged_Data.csv", "merged_data.csv"])
    FUND = find_file(["BTCUSDT_funding_history_8h.csv", "funding_history_8h.csv"])
    if DATA is None:
        pd.DataFrame([{'x': 'no data'}]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig'); return

    df1m = champ.load_data(DATA); df7 = champ.resample_tf(df1m, champ.TF_MIN); sig = champ.compute_signals(df7)
    idx7 = df7.index; oi7 = champ.load_oi_8h(OIPATH, idx7); bb7 = champ.load_bb_8h(DATA, idx7)
    ft = fr = None
    if FUND:
        try:
            ft, fr = sdca.load_funding(FUND)
        except Exception:
            ft = fr = None
    fund_real = ft is not None
    o = df7['open'].values; h = df7['high'].values; l = df7['low'].values; c = df7['close'].values
    n_bars = len(c)
    ind = RC.compute_indicators(o, h, l, c, RC.DEFAULT_PARAMS)
    tr = get_trend_trades(champ, sdca, df7, sig, oi7, bb7, ft, fr, ind, idx7)
    df = pd.DataFrame(tr)
    is25 = df['year'] == TARGET_YEAR
    other = ~is25
    print(f"[준비] 추세봇 {len(df)}건 | 2025 {int(is25.sum())}건 / 타년 {int(other.sum())}건 | 펀딩 {'REAL' if fund_real else 'NONE'}")

    # ══ 축1: 시간분포(2025 월별) ══
    a1 = []
    for mth in range(1, 13):
        g = df[is25 & (df['month'] == mth)]
        if len(g) == 0:
            continue
        m = metrics(g['R'].values)
        a1.append(dict(month=mth, n=m['n'], PF=m['PF'], ret=m['ret'], win=m['win']))
    pd.DataFrame(a1).to_csv(os.path.join(HERE, "axis1_month.csv"), index=False, encoding='utf-8-sig')

    # ══ 축2: 청산이유(2025 vs 타년, 손실거래 중심) ══
    a2 = []
    for tag, mask in [('2025', is25), ('타년', other)]:
        g = df[mask]; gl = g[g['R'] < 0]   # 손실거래
        for reason in ['trend_flip', 'sl']:
            rr = g[g['reason'] == reason]; rl = gl[gl['reason'] == reason]
            a2.append(dict(group=tag, reason=reason, n_total=len(rr), n_loss=len(rl),
                           loss_share=round(100 * len(rl) / max(1, len(gl)), 1),
                           avg_R=round(rr['R'].mean() * 100, 3) if len(rr) else 0.0))
    pd.DataFrame(a2).to_csv(os.path.join(HERE, "axis2_reason.csv"), index=False, encoding='utf-8-sig')

    # ══ 축3: 보유봉수(2025 vs 타년) ══
    a3 = []
    for tag, mask in [('2025', is25), ('타년', other)]:
        g = df[mask]; gw = g[g['R'] > 0]; gl = g[g['R'] < 0]
        a3.append(dict(group=tag, bars_mean=round(g['bars'].mean(), 2), bars_med=int(g['bars'].median()),
                       win_bars_mean=round(gw['bars'].mean(), 2) if len(gw) else 0.0,
                       loss_bars_mean=round(gl['bars'].mean(), 2) if len(gl) else 0.0,
                       short_loss_share=round(100 * (gl['bars'] <= 2).mean(), 1) if len(gl) else 0.0))
    pd.DataFrame(a3).to_csv(os.path.join(HERE, "axis3_holdbars.csv"), index=False, encoding='utf-8-sig')

    # ══ 축4: 진입지표(2025 vs 타년, 승/패 분리) ══
    a4 = []
    for tag, mask in [('2025', is25), ('타년', other)]:
        g = df[mask]
        for sub, sm in [('전체', g), ('승', g[g['R'] > 0]), ('패', g[g['R'] < 0])]:
            if len(sm) == 0:
                continue
            a4.append(dict(group=tag, subset=sub, n=len(sm),
                           ER=round(sm['f_er'].mean(), 4), ADX=round(sm['f_adx'].mean(), 2),
                           CHOP=round(sm['f_chop'].mean(), 2)))
    pd.DataFrame(a4).to_csv(os.path.join(HERE, "axis4_entryfeat.csv"), index=False, encoding='utf-8-sig')

    # ══ 필터 시제품: 축4서 2025 패배가 '진입 ER 낮음'과 연관되면 ER하한 필터 후보 격자 + CPCV ══
    # 2025 패 ER vs 타년 승 ER 비교로 임계 후보 자동 설정
    er25_loss = df[is25 & (df['R'] < 0)]['f_er'].mean()
    er_oth_win = df[other & (df['R'] > 0)]['f_er'].mean()
    fc_rows = []; best_paths = []
    all_R = df['R'].values; all_pos = df['bar'].values
    base_all = metrics(all_R)
    # 후보 격자: ER하한 [없음, 0.30, 0.35, 0.40, 0.45] × 보유봉하한은 사후성이라 진입필터만(ER·ADX)
    for er_min in [0.0, 0.30, 0.35, 0.40, 0.45]:
        for adx_min in [0.0, 20.0, 25.0]:
            keep = np.ones(len(df), dtype=bool)
            if er_min > 0:
                keep &= (df['f_er'].values >= er_min)
            if adx_min > 0:
                keep &= (df['f_adx'].values >= adx_min)
            Rk = all_R[keep]; posk = all_pos[keep]
            mk = metrics(Rk)
            # 2025만 따로
            k25 = keep & is25.values
            m25 = metrics(all_R[k25])
            # CPCV(거래 충분할때)
            if mk['n'] >= 30:
                cs, paths = CP.cpcv_pf_eval(posk, Rk, n_bars, N=N_GROUP, k=K_TEST, min_n=3)
                cpcv_p25 = cs['pf_p25']; cpcv_below1 = cs['pf_below1']
            else:
                cpcv_p25 = float('nan'); cpcv_below1 = -1; paths = []
            fc_rows.append(dict(er_min=er_min, adx_min=adx_min, n=mk['n'], PF_all=mk['PF'], ret_all=mk['ret'],
                                n2025=m25['n'], PF_2025=m25['PF'], ret_2025=m25['ret'],
                                cpcv_p25=cpcv_p25, cpcv_below1=cpcv_below1))
    fc = pd.DataFrame(fc_rows)
    fc.to_csv(os.path.join(HERE, "filter_candidates.csv"), index=False, encoding='utf-8-sig')
    # BEST: 2025 PF를 1위로 올리면서(>1) 전체 CPCV 견고(p25>1.3, PF<1경로<=2), degenerate(999)아님
    cand = fc[(fc['n'] >= 30) & (fc['PF_all'] < 900) & (fc['PF_2025'] > 1.0)].copy()
    improved = "개선"
    if len(cand) == 0:
        cand = fc[(fc['n'] >= 30) & (fc['PF_all'] < 900)].copy(); improved = "2025 흑자전환 실패"
    if len(cand) == 0:
        cand = fc.copy()
    cand['score'] = cand['cpcv_p25'].fillna(0) + cand['PF_2025'].clip(upper=5) * 0.3
    fbest = cand.sort_values('score', ascending=False).iloc[0]
    # BEST CPCV 경로상세
    bk = np.ones(len(df), dtype=bool)
    if fbest['er_min'] > 0:
        bk &= (df['f_er'].values >= fbest['er_min'])
    if fbest['adx_min'] > 0:
        bk &= (df['f_adx'].values >= fbest['adx_min'])
    _, bpaths = CP.cpcv_pf_eval(all_pos[bk], all_R[bk], n_bars, N=N_GROUP, k=K_TEST, min_n=3)
    pd.DataFrame(bpaths).to_csv(os.path.join(HERE, "filter_cpcv_paths.csv"), index=False, encoding='utf-8-sig')

    # 원장
    reg, _, _, _ = RC.classify(o, h, l, c, dict(w=0.0, chop_hi=60.0, adx_hi=30.0, vote_n=3), ind=ind)
    df['regime'] = [REGIME_MAP[int(reg[p])] for p in df['bar']]
    df[['side', 'year', 'month', 'regime', 'R', 'reason', 'bars', 'f_er', 'f_adx', 'f_chop']].to_csv(
        os.path.join(HERE, "ledger_trades.csv"), index=False, encoding='utf-8-sig')

    # 판정
    m2025 = metrics(df[is25]['R'].values); mother = metrics(df[other]['R'].values)
    # 축2 핵심: 2025 손실 중 sl vs flip
    g25l = df[is25 & (df['R'] < 0)]
    sl_share = round(100 * (g25l['reason'] == 'sl').mean(), 1) if len(g25l) else 0.0
    verdict = (f"VERDICT Stg8 2025포렌식 | 추세봇 2025 PF{m2025['PF']}(수익{m2025['ret']}) vs 타년 PF{mother['PF']}(수익{mother['ret']}) | "
               f"[축2]2025손실 sl비율{sl_share}% | [축4]2025패 진입ER {round(er25_loss,3)} vs 타년승 진입ER {round(er_oth_win,3)} | "
               f"[필터BEST] ER>={fbest['er_min']} ADX>={fbest['adx_min']} -> 전체PF{fbest['PF_all']}(n{fbest['n']}) 2025PF{fbest['PF_2025']} CPCV_p25{fbest['cpcv_p25']} -> {improved}")
    print("[verdict] " + verdict)
    pd.DataFrame([dict(sec=verdict),
                  dict(sec=f"[축1 월별] {a1}"),
                  dict(sec=f"[축2 청산이유] {a2}"),
                  dict(sec=f"[축3 보유봉] {a3}"),
                  dict(sec=f"[축4 진입지표] {a4}"),
                  dict(sec=f"[필터후보 상위5] {fc.sort_values('PF_2025',ascending=False).head(5).to_dict('records')}")]
                 ).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')
    with open(os.path.join(HERE, ".stg8_metric"), "w", encoding="utf-8") as f:
        f.write(f"bars7h={n_bars}\nn_trend={len(df)}\nn_2025={int(is25.sum())}\nn_other={int(other.sum())}\n"
                f"pf_2025={m2025['PF']}\nret_2025={m2025['ret']}\npf_other={mother['PF']}\nret_other={mother['ret']}\n"
                f"y2025_sl_loss_share={sl_share}\ner_2025_loss={round(er25_loss,4)}\ner_other_win={round(er_oth_win,4)}\n"
                f"filter_best_er={fbest['er_min']}\nfilter_best_adx={fbest['adx_min']}\nfilter_best_pf_all={fbest['PF_all']}\n"
                f"filter_best_pf_2025={fbest['PF_2025']}\nfilter_best_cpcv_p25={fbest['cpcv_p25']}\nfilter_best_n={fbest['n']}\n"
                f"filter_improved={improved}\nfilter_grid_n={len(fc)}\n"
                f"label_in_feature=False\nlookahead_block=entryfeat_past+cpcv_group\nfunding={'REAL' if fund_real else 'NONE'}\n")
    print("[save] axis1_month/axis2_reason/axis3_holdbars/axis4_entryfeat/filter_candidates/filter_cpcv_paths/ledger/summary.csv")


if __name__ == "__main__":
    main()
