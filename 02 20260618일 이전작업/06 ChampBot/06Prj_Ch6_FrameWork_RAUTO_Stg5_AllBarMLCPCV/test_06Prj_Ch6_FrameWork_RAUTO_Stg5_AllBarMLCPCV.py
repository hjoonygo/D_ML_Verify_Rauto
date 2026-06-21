# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch6_FrameWork_RAUTO_Stg5_AllBarMLCPCV.py
# 코드길이: 약 420줄 | 내부버전: 06Prj_Ch6_Stg5_AllBarMLCPCV_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]  사장님 확정: (C)전봉강제진입+거른이유특징 + 방식2고정청산 + 보유상한자동 + CPCV(N6,k2)
#   목적: ML 표본을 408개(실제거래)→전봉(수천)으로 늘려, "표본부족이 ML 실패의 원인이었나"를 끝까지 본다.
#   엔진 무수정(해시대조). 강제진입 가상수익=forced_entry.py, CPCV검증=cpcv.py, 지표=regime_classifier.py.
#
#   [A. 전봉 강제진입 가상수익]  매 봉에서 롱·숏 각각 강제진입→방식2청산(트렌드플립/ATR손절/N봉상한).
#     보유상한N=실제거래 평균보유봉 자동계산. 타깃y=추세봇가상R vs 횡보봇가상R 중 큰 쪽(어느 봇 유리한가).
#   [B. (C) 거른이유 특징]  각 봉에 f_low_gate/f_grave/f_trend_up 플래그 → ML이 '실전엔 없는 자리' 구분.
#   [C. ML + CPCV]  특징=표준8+허스트+CVD+OI+구조+거른이유. 모델4종. CPCV 15분할로 OOS AUC '분포'.
#     ★비교: (i)CPCV AUC분포가 0.5 위에 안정적인가  (ii)전봉ML이 Stg4의 거래봉ML(AUC0.5)보다 나은가
#   [D. 매트릭스]  실제거래 408건으로 장세×년도×롱숏 × PF·수익률·payoff·거래수·수익금 (Stg4와 동일포맷, 재확인용)
#
#   [★미래참조 차단 — 3중]  ① 특징 X=진입봉-1(과거)만  ② 가상수익 청산은 미래봉이나 그건 타깃(라벨)전용
#     ③ CPCV purge+embargo로 학습-검증 누수 차단  + check가 AUC 0.95+면 누수경보.
#
# [PATH] 실행 D:\ML\verify\06Prj_Ch6_FrameWork_RAUTO_Stg5_AllBarMLCPCV\ . 데이터 상위 D:\ML\verify.
# [OUTPUT] allbar_ml_cpcv.csv / ml_model_compare.csv / ml_feature_importance.csv / cpcv_paths.csv /
#          compare_stg4.csv / matrix_regime.csv / matrix_year.csv / matrix_side.csv / ledger_trades.csv / summary.csv + .stg5_metric
# [In/Out 태그]
#   forced_entry: avg_hold_bars(In 거래/Out 평균봉) / forced_vret(In OHLC,Trend,atr,side,N/Out 가상R,이유,봉) / skip_reason_flags
#   cpcv: cpcv_split(In n,t_entry,t_exit,N,k/Out 분할15) / cpcv_eval(In 모델,X,y,w,시각/Out AUC분포)
#   regime_classifier: compute_indicators / feature_matrix
#   엔진(무수정): champ.* / sdca.*  본코드: ns_i64/metrics/get_trades/agg_matrix/main
#   변수(동결): N_GROUP=6 K_TEST=2 COST_RT=0.0014 SL_MULT=2.0
# ==============================================================================
import os, sys, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE); BOTS = os.path.join(HERE, "bots")
sys.path.insert(0, HERE)
import regime_classifier as RC
import forced_entry as FE
import cpcv as CP

N_GROUP = 6; K_TEST = 2; COST_RT = 0.0014; SL_MULT = 2.0
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


def get_trades(champ, sdca, DATA, OIPATH, FUND):
    df1m = champ.load_data(DATA); df7 = champ.resample_tf(df1m, champ.TF_MIN); sig = champ.compute_signals(df7)
    idx7 = df7.index; oi7 = champ.load_oi_8h(OIPATH, idx7); bb7 = champ.load_bb_8h(DATA, idx7)
    ft = fr = None
    if FUND:
        try:
            ft, fr = sdca.load_funding(FUND)
        except Exception:
            ft = fr = None

    def fpay(side, et, xt):
        if ft is None:
            return 0.0
        fs = sdca.funding_sum(ft, fr, int(pd.Timestamp(et).value), int(pd.Timestamp(xt).value))
        return side * fs if fs is not None else 0.0
    ttr = champ.run_strategy(df7, sig, 0, 'none', 0.8, gate_mode='er', gate_er=0.45,
                             dz_oi=oi7, gate_bb=bb7, fib=(0.3, 0.5, 0.6), split_mode='A', split_n=3)
    tT = []
    for t in ttr:
        R = t['side'] * (t['exit'] - t['entry']) / t['entry'] - COST_RT - fpay(t['side'], t['entry_t'], t['exit_t'])
        et = pd.Timestamp(t['entry_t'])
        tT.append(dict(bot='trend', side=int(t['side']), entry_t=et, year=et.year, R=float(R), bars=int(t.get('bars', 0))))
    s1 = sdca.load_1m(DATA); df8 = sdca.resample_tf(s1, sdca.TF_MIN); ssig = sdca.precompute(df8)
    ss, se = sdca.build_1m_map(s1, df8)
    mO = s1['open'].values; mH = s1['high'].values; mL = s1['low'].values
    mT = s1.index.values.astype('datetime64[ns]').astype('int64')
    res = sdca.run_bot_honest(df8, ssig, sdca.BEST_PAR, mO, mH, mL, mT, ss, se, ft, fr, sdca.DEFAULT_SLMULT, filter_mode='precise')
    trades = res[0] if isinstance(res, tuple) else res
    tS = []
    for t in (trades or []):
        et = t.get('entry_t')
        if et is None:
            continue
        et = pd.Timestamp(et)
        tS.append(dict(bot='sideway', side=int(t.get('side', 1)), entry_t=et,
                       year=int(t.get('year', et.year)), R=float(t.get('R', 0.0)), bars=int(t.get('bars', 0))))
    o = df7['open'].values; h = df7['high'].values; l = df7['low'].values; c = df7['close'].values
    Trend = sig['Trend']; adx = sig['adx']; er = sig['er']
    # ATR(엔진 함수 재사용)
    atr = champ.compute_atr(h, l, c, champ.ADX_N)
    return tT, tS, (o, h, l, c), Trend, adx, er, atr, idx7, oi7, (ft is not None), sig


def trade_bar_idx(trades, idx7):
    edges = ns_i64(idx7); out = []
    for t in trades:
        pos = np.searchsorted(edges, np.int64(pd.Timestamp(t['entry_t']).value), side='right') - 1
        out.append(max(0, min(pos, len(edges) - 1)))
    return np.array(out)


def agg_matrix(ledger, group_col):
    rows = []
    for key, g in ledger.groupby(group_col):
        for bot in ['trend', 'sideway', 'ALL']:
            sub = g if bot == 'ALL' else g[g['bot'] == bot]
            if len(sub) == 0:
                continue
            m = metrics(sub['R'].values)
            rows.append(dict(key=key, bot=bot, n=m['n'], PF=m['PF'], ret_pct=m['ret'],
                             payoff=m['payoff'], win=m['win'], profit_usd=round(sub['R'].sum() * 10000, 0)))
    return pd.DataFrame(rows)


def main():
    print("[Stg5] 전봉 강제진입 가상수익 + (C)거른이유특징 + ML + CPCV(N6,k2) 15분할")
    champ = load_engine(os.path.join(BOTS, "SpTrd_Fib_V1_Champion.py"), "champ_engine")
    sdca = load_engine(os.path.join(BOTS, "SidewayDCA_Stg7_engine.py"), "sdca_engine")
    DATA = find_file(["Merged_Data_with_Regime_Features.csv", "merged_data.csv"])
    OIPATH = find_file(["Merged_Data.csv", "merged_data.csv"])
    FUND = find_file(["BTCUSDT_funding_history_8h.csv", "funding_history_8h.csv"])
    if DATA is None:
        pd.DataFrame([{'x': 'no data'}]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig'); return

    tT, tS, (o, h, l, c), Trend, adx, er, atr, idx7, oi7, fund_real, sig = get_trades(champ, sdca, DATA, OIPATH, FUND)
    n = len(c)
    ind = RC.compute_indicators(o, h, l, c, RC.DEFAULT_PARAMS)
    print(f"[준비] 7h봉 {n} / 추세 {len(tT)} / 횡보 {len(tS)} / 펀딩 {'REAL' if fund_real else 'NONE'}")

    # ── 보유상한 자동계산 ──
    hold_T = FE.avg_hold_bars(tT, default=8); hold_S = FE.avg_hold_bars(tS, default=5)
    print(f"[자동계산] 보유상한봉 추세봇={hold_T} 횡보봇={hold_S} (실제거래 평균)")

    # ── A. 전봉 강제진입 가상수익 (롱/숏 각각, 추세봇·횡보봇 보유상한 다름) ──
    # 추세봇 관점 가상수익(롱/숏 중 그 봉 Trend방향), 횡보봇 관점(평균회귀=짧은보유)
    vRT_long, _, _ = FE.forced_vret(c, h, l, Trend, atr, +1, hold_T, SL_MULT)
    vRT_short, _, _ = FE.forced_vret(c, h, l, Trend, atr, -1, hold_T, SL_MULT)
    vRS_long, _, _ = FE.forced_vret(c, h, l, Trend, atr, +1, hold_S, SL_MULT)
    vRS_short, _, _ = FE.forced_vret(c, h, l, Trend, atr, -1, hold_S, SL_MULT)
    # 각 봉: 추세봇 최선(롱/숏 큰쪽) vs 횡보봇 최선 → 타깃 = 추세봇이 유리하면 1
    with np.errstate(all='ignore'):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', category=RuntimeWarning)
            vRT_best = np.nanmax(np.vstack([vRT_long, vRT_short]), axis=0)
            vRS_best = np.nanmax(np.vstack([vRS_long, vRS_short]), axis=0)
    y_all = (vRT_best > vRS_best).astype(int)        # 1=추세봇유리, 0=횡보봇유리
    w_all = np.abs(vRT_best - vRS_best)              # 차이 클수록 확실
    w_all = np.nan_to_num(np.clip(w_all, 1e-6, None), nan=1e-6)

    # ── B. (C) 거른이유 특징 ──
    flags = FE.skip_reason_flags(sig, n, dz_oi=oi7, dz_lo=champ.DZ_LO, dz_hi=champ.DZ_HI,
                                 gate_mode='er', gate_er=0.45)

    # ── 특징행렬 (진입봉-1 = 과거만) ──
    hurst = np.zeros(n)
    try:
        hurst = _hurst(c, 64)
    except Exception:
        pass
    base_X = RC.feature_matrix(ind)
    extra = [hurst.reshape(-1, 1), flags['f_low_gate'].reshape(-1, 1),
             flags['f_grave'].reshape(-1, 1), flags['f_trend_up'].reshape(-1, 1)]
    full = np.column_stack([base_X] + extra)
    feat_names = ['adx', 'pdi', 'ndi', 'chop', 'er', 'bb', 'atr_r', 'slope', 'hurst', 'f_low_gate', 'f_grave', 'f_trend_up']
    # 미래참조 차단: 각 봉 특징 = 진입봉-1(전봉)
    Xshift = np.vstack([full[0:1], full[:-1]])      # 한 칸 과거로
    valid = np.isfinite(Xshift).all(axis=1) & np.isfinite(vRT_best) & np.isfinite(vRS_best)
    warm = 2 * RC.DEFAULT_PARAMS['adx_n']
    valid[:warm] = False
    Xall = np.nan_to_num(Xshift[valid], nan=0.0, posinf=0.0, neginf=0.0)
    y = y_all[valid]; w = w_all[valid]
    # 시각(라벨이 관측한 범위): entry=봉i, exit=봉i+보유상한(최대)
    bar_pos = np.where(valid)[0]
    t_entry = bar_pos.astype(float); t_exit = (bar_pos + max(hold_T, hold_S)).astype(float)
    print(f"[전봉ML] 학습표본 {len(Xall)}개 (Stg4 거래봉 408 대비) / 추세봇유리 {int(y.sum())} 횡보봇유리 {int((y==0).sum())}")

    # ── C. ML 4모델 (시간순 단일분할 비교 + CPCV 분포) ──
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score
    sc = StandardScaler().fit(Xall); Xs = sc.transform(Xall)
    k = int(len(Xs) * 0.7); tr = np.arange(k); te = np.arange(k, len(Xs))
    model_specs = {
        'LogReg': lambda: __import__('sklearn.linear_model', fromlist=['LogisticRegression']).LogisticRegression(max_iter=2000, class_weight='balanced'),
        'RandForest': lambda: __import__('sklearn.ensemble', fromlist=['RandomForestClassifier']).RandomForestClassifier(n_estimators=300, max_depth=6, class_weight='balanced', random_state=0, n_jobs=-1),
        'GradBoost': lambda: __import__('sklearn.ensemble', fromlist=['GradientBoostingClassifier']).GradientBoostingClassifier(n_estimators=200, max_depth=3, random_state=0),
        'HistGB': lambda: __import__('sklearn.ensemble', fromlist=['HistGradientBoostingClassifier']).HistGradientBoostingClassifier(max_iter=300, random_state=0, class_weight='balanced'),
    }
    mc_rows = []; best_simple = None
    for name, fac in model_specs.items():
        try:
            m = fac(); m.fit(Xs[tr], y[tr], sample_weight=w[tr])
            p = m.predict_proba(Xs[te])[:, 1]
            auc = roc_auc_score(y[te], p) if len(np.unique(y[te])) >= 2 else float('nan')
            acc = float(((p > 0.5).astype(int) == y[te]).mean())
            mc_rows.append(dict(model=name, oos_auc=round(auc, 3), oos_acc=round(acc, 3)))
            if not np.isnan(auc) and (best_simple is None or auc > best_simple[1]):
                best_simple = (name, auc, fac)
        except Exception as e:
            mc_rows.append(dict(model=name, oos_auc='ERR', oos_acc=str(e)[:30]))
    pd.DataFrame(mc_rows).to_csv(os.path.join(HERE, "ml_model_compare.csv"), index=False, encoding='utf-8-sig')

    # CPCV 분포(best 모델)
    cpcv_res = dict(n_paths=0, auc_mean=float('nan'), auc_std=float('nan'), auc_min=float('nan'), auc_p25=float('nan'))
    paths_df = pd.DataFrame()
    if best_simple is not None:
        fac = best_simple[2]
        cpcv_res = CP.cpcv_eval(lambda: fac(), Xs, y, w, t_entry, t_exit, N=N_GROUP, k=K_TEST)
        # 경로별 상세
        splits = CP.cpcv_split(len(Xs), t_entry, t_exit, N_GROUP, K_TEST)
        prows = []
        for tri, tei, tg in splits:
            if len(np.unique(y[tri])) < 2 or len(np.unique(y[tei])) < 2:
                continue
            try:
                m = fac(); m.fit(Xs[tri], y[tri], sample_weight=w[tri])
                pp = m.predict_proba(Xs[tei])[:, 1]
                prows.append(dict(test_groups=str(tg), n_train=len(tri), n_test=len(tei),
                                  auc=round(roc_auc_score(y[tei], pp), 3)))
            except Exception:
                continue
        paths_df = pd.DataFrame(prows)
    paths_df.to_csv(os.path.join(HERE, "cpcv_paths.csv"), index=False, encoding='utf-8-sig')

    # 특징 중요도
    fi = []
    if best_simple is not None:
        try:
            m = best_simple[2](); m.fit(Xs, y, sample_weight=w)
            if hasattr(m, 'feature_importances_'):
                imp = m.feature_importances_
            elif hasattr(m, 'coef_'):
                imp = np.abs(m.coef_).ravel()
            else:
                imp = np.zeros(len(feat_names))
            order = np.argsort(imp)[::-1]
            fi = [(feat_names[i], round(float(imp[i]), 4)) for i in order]
        except Exception:
            fi = []
    pd.DataFrame(fi, columns=['feature', 'importance']).to_csv(os.path.join(HERE, "ml_feature_importance.csv"), index=False, encoding='utf-8-sig')

    # allbar 요약
    best_auc = round(best_simple[1], 3) if best_simple else float('nan')
    pd.DataFrame([dict(n_samples=len(Xall), best_model=best_simple[0] if best_simple else 'none',
                       simple_oos_auc=best_auc, cpcv_auc_mean=cpcv_res['auc_mean'],
                       cpcv_auc_std=cpcv_res['auc_std'], cpcv_auc_min=cpcv_res['auc_min'],
                       cpcv_auc_p25=cpcv_res['auc_p25'], cpcv_paths=cpcv_res['n_paths'])]
                 ).to_csv(os.path.join(HERE, "allbar_ml_cpcv.csv"), index=False, encoding='utf-8-sig')

    # Stg4 비교(거래봉ML AUC~0.5 vs 전봉ML)
    pd.DataFrame([dict(approach='Stg4_거래봉ML(408)', best_oos_auc='0.50~0.55(동전)', note='표본부족 가설'),
                  dict(approach='Stg5_전봉ML(%d)' % len(Xall), best_oos_auc=best_auc,
                       note='CPCV평균%.3f 최저%.3f' % (cpcv_res['auc_mean'], cpcv_res['auc_min']))]
                 ).to_csv(os.path.join(HERE, "compare_stg4.csv"), index=False, encoding='utf-8-sig')

    # ── D. 매트릭스(실제거래) ──
    bi_T = trade_bar_idx(tT, idx7); bi_S = trade_bar_idx(tS, idx7)
    reg_b, _, _, _ = RC.classify(o, h, l, c, dict(w=0.0, chop_hi=60.0, adx_hi=30.0, vote_n=3), ind=ind)
    regT = reg_b[bi_T]; regS = reg_b[bi_S]
    led = []
    for kk, t in enumerate(tT):
        led.append(dict(bot='trend', side=('long' if t['side'] > 0 else 'short'), year=t['year'],
                        regime=REGIME_MAP[int(regT[kk])], R=t['R'], win=int(t['R'] > 0)))
    for kk, t in enumerate(tS):
        led.append(dict(bot='sideway', side=('long' if t['side'] > 0 else 'short'), year=t['year'],
                        regime=REGIME_MAP[int(regS[kk])], R=t['R'], win=int(t['R'] > 0)))
    ledger = pd.DataFrame(led)
    ledger.to_csv(os.path.join(HERE, "ledger_trades.csv"), index=False, encoding='utf-8-sig')
    agg_matrix(ledger, 'regime').to_csv(os.path.join(HERE, "matrix_regime.csv"), index=False, encoding='utf-8-sig')
    agg_matrix(ledger, 'year').to_csv(os.path.join(HERE, "matrix_year.csv"), index=False, encoding='utf-8-sig')
    agg_matrix(ledger, 'side').to_csv(os.path.join(HERE, "matrix_side.csv"), index=False, encoding='utf-8-sig')

    # 판정: 전봉ML이 CPCV에서 0.5+ 안정적으로 이기나
    verdict_ml = "ML유효" if (cpcv_res['auc_p25'] == cpcv_res['auc_p25'] and cpcv_res['auc_p25'] > 0.55) else "ML무효(표본늘려도 동전)"
    verdict = (f"VERDICT Stg5 | 추세{len(tT)}/횡보{len(tS)} 펀딩{'REAL' if fund_real else 'NONE'} | "
               f"보유상한 추세{hold_T}/횡보{hold_S} | 전봉ML표본 {len(Xall)}(거래봉408 대비) | "
               f"best {best_simple[0] if best_simple else 'NA'} 단일OOS_AUC={best_auc} | "
               f"CPCV {cpcv_res['n_paths']}경로 AUC평균={cpcv_res['auc_mean']} 최저={cpcv_res['auc_min']} p25={cpcv_res['auc_p25']} | "
               f"-> {verdict_ml} | 특징중요도1위={fi[0] if fi else 'NA'}")
    print("[verdict] " + verdict)
    pd.DataFrame([dict(sec=verdict),
                  dict(sec=f"[ML모델비교] {mc_rows}"),
                  dict(sec=f"[CPCV] {cpcv_res}"),
                  dict(sec=f"[특징중요도 상위8] {fi[:8]}"),
                  dict(sec=f"[Stg4대비] 거래봉ML 0.5 vs 전봉ML {best_auc}")]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')
    with open(os.path.join(HERE, ".stg5_metric"), "w", encoding="utf-8") as f:
        f.write(f"n_trend={len(tT)}\nn_sw={len(tS)}\nbars7h={n}\nhold_T={hold_T}\nhold_S={hold_S}\n"
                f"ml_samples={len(Xall)}\nbest_model={best_simple[0] if best_simple else 'NA'}\n"
                f"simple_oos_auc={best_auc}\ncpcv_paths={cpcv_res['n_paths']}\ncpcv_auc_mean={cpcv_res['auc_mean']}\n"
                f"cpcv_auc_std={cpcv_res['auc_std']}\ncpcv_auc_min={cpcv_res['auc_min']}\ncpcv_auc_p25={cpcv_res['auc_p25']}\n"
                f"verdict_ml={verdict_ml}\nml_feat_n={len(feat_names)}\n"
                f"label_in_feature=False\nlookahead_block=feat_shift1+cpcv_purge+embargo\nfunding={'REAL' if fund_real else 'NONE'}\n")
    print("[save] allbar_ml_cpcv/ml_model_compare/ml_feature_importance/cpcv_paths/compare_stg4/matrix_*/ledger/summary.csv")


def _hurst(close, win=64):
    N = len(close); H = np.full(N, 0.5); lr = np.zeros(N)
    lr[1:] = np.diff(np.log(np.clip(close, 1e-9, None)))
    for i in range(win, N):
        x = lr[i - win + 1:i + 1]; m = x.mean(); dev = np.cumsum(x - m)
        Rg = dev.max() - dev.min(); S = x.std()
        if S > 0 and Rg > 0:
            H[i] = np.log(Rg / S) / np.log(win)
    return H


if __name__ == "__main__":
    main()
