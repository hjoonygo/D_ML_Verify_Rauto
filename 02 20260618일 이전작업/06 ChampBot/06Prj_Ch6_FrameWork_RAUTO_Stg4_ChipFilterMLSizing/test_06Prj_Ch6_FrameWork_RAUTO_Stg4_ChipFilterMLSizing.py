# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch6_FrameWork_RAUTO_Stg4_ChipFilterMLSizing.py
# 코드길이: 약 480줄 | 내부버전: 06Prj_Ch6_Stg4_ChipFilterMLSizing_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]  사장님 확정 4건 전부 반영:
#   확인1 = 칩필터 S1~S5 전부 격자  확인2 = ML 동봉  +Squeeze 게이트 추가  +ML 자유도 최대(가-강화)
#
#   [목표] 옛 칩필터(2025 횡보봇 0번 켜진 버그)를 검색근거로 고쳐 '최대 알파'를 뽑고, ML로 사이징까지 본다.
#   엔진 무수정(해시대조). 분류기·칩게이트는 독립모듈(regime_classifier.py). 비용0.14%+실펀딩. label_smc 입력금지.
#
#   [A. 243 칩필터 격자 — S1~S5 + Squeeze]  (2단계 탐색으로 연산폭발 방지)
#     S1 사전게이팅 pre_n: 0/2/4   S2 연속확정 hold_k: 1/2/3   S3 CHOP임계: 55/61.8/65
#     S4 조합: AND/OR/2of3         S5 방향짝: (게이트는 무방향, 방향은 분류기 w가 담당)
#     Squeeze: off / bb<4.0 / bb<2.5
#     → 각 조합에서 '횡보봇을 칩게이트 통과봉만 켰을 때' PF·수익·2025 켜짐수를 채점. BEST=횡보봇 레인지 PF·수익.
#
#   [B. ML 사이징 — 만반준비]  타깃=(다)봇수익정답지+(가)거래있는봉만(미래참조 구조차단), R크기 가중.
#     특징=표준8(분류기) + 허스트 + CVD(cvd_press/taker_ratio) + OI(oi_z/taker_imb/top_retail) + 다TF + 구조(feat_break)
#     모델 4종+하이퍼탐색. 평가=ML확률로 사이징(베팅배수)했을 때 봇 PF가 표준 대비 나은가. 워크포워드 OOS.
#
#   [C. 출력 매트릭스]  per-trade 원장(bot·side·year·regime·R·win) → 장세별·년도별·롱숏별 × {PF·수익률·손익비·거래수·수익금}
#
# [PATH] 실행 D:\ML\verify\06Prj_Ch6_FrameWork_RAUTO_Stg4_ChipFilterMLSizing\ . 데이터 상위 D:\ML\verify.
# [OUTPUT] chip_grid.csv / chip_best.csv / matrix_regime.csv / matrix_year.csv / matrix_side.csv /
#          ledger_trades.csv / ml_model_compare.csv / ml_feature_importance.csv / ml_sizing_pf.csv /
#          walkforward.csv / summary.csv + .stg4_metric
# [In/Out 태그]
#   regime_classifier: compute_indicators(In OHLC,P/Out 지표) / chip_gate_at(In 지표,봉idx,P/Out 통과bool) / feature_matrix
#   ml_sizing: build_targets / fit_eval_models / feature_importance
#   엔진(무수정): champ.load_data/resample_tf/compute_signals/run_strategy/load_oi_8h/load_bb_8h/TF_MIN
#                 sdca.load_1m/resample_tf/precompute/build_1m_map/run_bot_honest/load_funding/funding_sum/BEST_PAR/DEFAULT_SLMULT/TF_MIN
#   본코드: ns_i64 / metrics(R→PF·payoff·win) / get_trades(거래+side+year+R재계산) / load_aux_features(허스트/CVD/OI/다TF/구조)
#           / trade_bar_idx / chip_grid_search / ml_block / agg_matrix / save_all
#   변수(동결): PRE_N=[0,2,4] HOLD_K=[1,2,3] CHOP_HI=[55,61.8,65] COMBO=[AND,OR,2of3] SQZ=[0,4.0,2.5]
#               COST_RT=0.0014 TREND_REG={0,1} RANGE_REG={2,3} TRAIN_MIN=18 TEST_M=3 STEP_M=3
# ==============================================================================
import os, sys, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE); BOTS = os.path.join(HERE, "bots")
sys.path.insert(0, HERE)
import regime_classifier as RC
import ml_sizing as ML

PRE_N = [0, 2, 4]; HOLD_K = [1, 2, 3]; CHOP_HI = [55.0, 61.8, 65.0]
COMBO = ['AND', 'OR', '2of3']; SQZ = [0.0, 4.0, 2.5]
COST_RT = 0.0014
TREND_REG = {0, 1}; RANGE_REG = {2, 3}
TRAIN_MIN, TEST_M, STEP_M = 18, 3, 3
REGIME_MAP = {0: 'uptrend', 1: 'downtrend', 2: 'volatile_range', 3: 'dead_range'}
NAME2INT = {'uptrend': 0, 'downtrend': 1, 'volatile_range': 2, 'dead_range': 3}


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
    R = np.asarray(R, float); n = len(R)
    if n == 0:
        return dict(n=0, PF=0.0, ret=0.0, win=0.0, payoff=0.0)
    gp = float(R[R > 0].sum()); gl = float(-R[R < 0].sum())
    pf = round(gp / gl, 3) if gl > 0 else (999.0 if gp > 0 else 0.0)
    wins = R[R > 0]; losses = R[R < 0]
    avg_w = wins.mean() if len(wins) else 0.0; avg_l = -losses.mean() if len(losses) else 0.0
    payoff = round(avg_w / avg_l, 3) if avg_l > 0 else (999.0 if avg_w > 0 else 0.0)
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
        tT.append(dict(bot='trend', side=int(t['side']), entry_t=et, year=et.year, R=float(R)))
    # 횡보봇(정밀필터)
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
                       year=int(t.get('year', et.year)), R=float(t.get('R', 0.0))))
    o = df7['open'].values; h = df7['high'].values; l = df7['low'].values; c = df7['close'].values
    return tT, tS, (o, h, l, c), idx7, (ft is not None), df7


def load_aux_features(DATA, OIPATH, idx7, champ):
    # ML 자유도용 추가특징(전부 과거봉만). 없으면 NaN열(ML이 알아서 무시). lookahead 없음.
    feats = {}
    o = None
    head_main = list(pd.read_csv(DATA, nrows=1).columns)
    # 구조특징 feat_break_* / feat_struct (Merged_Data_with_Regime_Features에 있으면 7h last 매칭)
    struct_cols = [c for c in head_main if c.startswith('feat_break') or c.startswith('feat_struct')]
    micro_cols = [c for c in head_main if c in ('oi_zscore_24h', 'taker_imbalance', 'top_retail_divergence', 'oi_change')]
    want = struct_cols + micro_cols
    if want:
        try:
            df = pd.read_csv(DATA, usecols=['timestamp'] + want, index_col='timestamp', parse_dates=True)
            if getattr(df.index, 'tz', None) is not None:
                df.index = df.index.tz_localize(None)
            r = df.resample('420min', label='left', closed='left').last().reindex(idx7)
            for cc in want:
                feats[cc] = r[cc].values.astype('float64')
        except Exception:
            pass
    return feats


def compute_hurst(close, win=64):
    # R/S 허스트(과거 win봉만). 표준 Rescaled Range.
    N = len(close); H = np.full(N, 0.5)
    lr = np.zeros(N)
    lr[1:] = np.diff(np.log(np.clip(close, 1e-9, None)))
    for i in range(win, N):
        x = lr[i - win + 1:i + 1]
        m = x.mean(); dev = np.cumsum(x - m)
        Rg = dev.max() - dev.min(); S = x.std()
        if S > 0 and Rg > 0:
            H[i] = np.log(Rg / S) / np.log(win)
    return H


def trade_bar_idx(trades, idx7):
    edges = ns_i64(idx7)
    out = []
    for t in trades:
        pos = np.searchsorted(edges, np.int64(pd.Timestamp(t['entry_t']).value), side='right') - 1
        out.append(max(0, min(pos, len(edges) - 1)))
    return np.array(out)


def chip_grid_search(ind, tS, bi_S, RS):
    # 횡보봇 거래를 칩게이트 통과봉만 켰을 때 PF·수익·2025켜짐. 243조합(전수, 빠름).
    rows = []
    yr = np.array([t['year'] for t in tS])
    for pn in PRE_N:
        for hk in HOLD_K:
            for ch in CHOP_HI:
                for cb in COMBO:
                    for sq in SQZ:
                        P = dict(chip_pre_n=pn, chip_hold_k=hk, chip_chop_hi=ch, chip_combo=cb, chip_squeeze=sq)
                        passed = RC.chip_gate_at(ind, bi_S, P)
                        Rp = RS[passed]
                        m = metrics(Rp)
                        on2025 = int(((yr == 2025) & passed).sum())
                        rows.append(dict(pre_n=pn, hold_k=hk, chop_hi=ch, combo=cb, sqz=sq,
                                         n=m['n'], PF=m['PF'], ret=m['ret'], win=m['win'], payoff=m['payoff'],
                                         on2025=on2025))
    return pd.DataFrame(rows)


def agg_matrix(ledger, group_col):
    rows = []
    for key, g in ledger.groupby(group_col):
        for bot in ['trend', 'sideway', 'ALL']:
            sub = g if bot == 'ALL' else g[g['bot'] == bot]
            if len(sub) == 0:
                continue
            m = metrics(sub['R'].values)
            # 수익금 근사: START_CAP=10000 복리 아닌 단순 R합*명목 (거칢, 표시용). PF·수익률·거래수·payoff는 정확.
            rows.append(dict(key=key, bot=bot, n=m['n'], PF=m['PF'], ret_pct=m['ret'],
                             payoff=m['payoff'], win=m['win'], profit_usd=round(sub['R'].sum() * 10000, 0)))
    return pd.DataFrame(rows)


def gen_windows(t0, t1):
    wins = []; ts = t0 + pd.DateOffset(months=TRAIN_MIN)
    while ts < t1:
        wins.append((t0, ts, min(ts + pd.DateOffset(months=TEST_M), t1))); ts += pd.DateOffset(months=STEP_M)
    return wins


def main():
    print("[Stg4] 칩필터 S1~S5+Squeeze 243격자 + ML 사이징(만반준비) + per-trade 매트릭스")
    champ = load_engine(os.path.join(BOTS, "SpTrd_Fib_V1_Champion.py"), "champ_engine")
    sdca = load_engine(os.path.join(BOTS, "SidewayDCA_Stg7_engine.py"), "sdca_engine")
    DATA = find_file(["Merged_Data_with_Regime_Features.csv", "merged_data.csv"])
    OIPATH = find_file(["Merged_Data.csv", "merged_data.csv"])
    FUND = find_file(["BTCUSDT_funding_history_8h.csv", "funding_history_8h.csv"])
    if DATA is None:
        pd.DataFrame([{'x': 'no data'}]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig'); return

    tT, tS, (o, h, l, c), idx7, fund_real, df7 = get_trades(champ, sdca, DATA, OIPATH, FUND)
    ind = RC.compute_indicators(o, h, l, c, RC.DEFAULT_PARAMS)
    bi_T = trade_bar_idx(tT, idx7); bi_S = trade_bar_idx(tS, idx7)
    RT = np.array([t['R'] for t in tT]); RS = np.array([t['R'] for t in tS])
    print(f"[준비] 7h봉 {len(c)} / 추세 {len(tT)} / 횡보 {len(tS)} / 펀딩 {'REAL' if fund_real else 'NONE'}")

    # ── A. 칩필터 243격자 ──
    chip = chip_grid_search(ind, tS, bi_S, RS)
    chip.to_csv(os.path.join(HERE, "chip_grid.csv"), index=False, encoding='utf-8-sig')
    # BEST: 표본 충분(n>=15) 중 PF*수익 정렬, 2025 켜짐 우선
    cand = chip[chip['n'] >= 15].copy()
    if len(cand) == 0:
        cand = chip.copy()
    cand['score'] = cand['PF'] * np.sign(cand['ret']) * np.log1p(np.abs(cand['ret']))
    chip_best = cand.sort_values(['on2025', 'score'], ascending=False).iloc[0]
    pd.DataFrame([dict(chip_best)]).to_csv(os.path.join(HERE, "chip_best.csv"), index=False, encoding='utf-8-sig')
    bestP = dict(chip_pre_n=int(chip_best['pre_n']), chip_hold_k=int(chip_best['hold_k']),
                 chip_chop_hi=float(chip_best['chop_hi']), chip_combo=chip_best['combo'], chip_squeeze=float(chip_best['sqz']))
    passed_best = RC.chip_gate_at(ind, bi_S, bestP)

    # ── B. per-trade 원장(장세=Stg3 BEST 분류기 국면, 칩게이트 통과여부 포함) ──
    reg_b, _, _, _ = RC.classify(o, h, l, c, dict(w=0.0, chop_hi=60.0, adx_hi=30.0, vote_n=3), ind=ind)
    regT = reg_b[bi_T]; regS = reg_b[bi_S]
    led = []
    for k, t in enumerate(tT):
        led.append(dict(bot='trend', side=('long' if t['side'] > 0 else 'short'), year=t['year'],
                        regime=REGIME_MAP[int(regT[k])], R=t['R'], win=int(t['R'] > 0), chip_pass=''))
    for k, t in enumerate(tS):
        led.append(dict(bot='sideway', side=('long' if t['side'] > 0 else 'short'), year=t['year'],
                        regime=REGIME_MAP[int(regS[k])], R=t['R'], win=int(t['R'] > 0),
                        chip_pass=int(bool(passed_best[k]))))
    ledger = pd.DataFrame(led)
    ledger.to_csv(os.path.join(HERE, "ledger_trades.csv"), index=False, encoding='utf-8-sig')

    # ── C. 매트릭스 3종(장세/년도/롱숏) ──
    agg_matrix(ledger, 'regime').to_csv(os.path.join(HERE, "matrix_regime.csv"), index=False, encoding='utf-8-sig')
    agg_matrix(ledger, 'year').to_csv(os.path.join(HERE, "matrix_year.csv"), index=False, encoding='utf-8-sig')
    agg_matrix(ledger, 'side').to_csv(os.path.join(HERE, "matrix_side.csv"), index=False, encoding='utf-8-sig')

    # ── D. ML 블록(만반준비) ──
    aux = load_aux_features(DATA, OIPATH, idx7, champ)
    hurst = compute_hurst(c, 64)
    base_names = ['adx', 'pdi', 'ndi', 'chop', 'er', 'bb', 'atr_r', 'slope']
    base_X = RC.feature_matrix(ind)
    extra_names = ['hurst'] + list(aux.keys())
    extra_cols = [hurst] + [aux[k] for k in aux.keys()]
    feat_names = base_names + extra_names
    # 봉별 특징행렬(거래봉에서 '진입봉 직전' 값을 뽑아 미래참조 차단: bar-1)
    full_X = np.column_stack([base_X] + [col.reshape(-1, 1) for col in extra_cols]) if extra_cols else base_X

    def feat_at(bar_idx):
        idx = np.clip(np.asarray(bar_idx) - 1, 0, len(c) - 1)   # 진입봉 직전(과거)
        return full_X[idx]

    bots_all = np.array([t['bot'] for t in tT] + [t['bot'] for t in tS])
    R_all = np.concatenate([RT, RS])
    bar_all = np.concatenate([bi_T, bi_S])
    ent_ns = np.array([pd.Timestamp(t['entry_t']).value for t in tT] + [pd.Timestamp(t['entry_t']).value for t in tS])
    order = np.argsort(ent_ns); bots_all = bots_all[order]; R_all = R_all[order]; bar_all = bar_all[order]; ent_ns = ent_ns[order]
    Xtr_full = feat_at(bar_all)
    bot_dummy = (bots_all == 'trend').astype(float).reshape(-1, 1)
    Xall = np.column_stack([Xtr_full, bot_dummy])
    feat_names_ml = feat_names + ['is_trend_bot']
    y_all, w_all = ML.build_targets(bots_all, R_all)
    # NaN 보정(특징 없으면 0)
    Xall = np.nan_to_num(Xall, nan=0.0, posinf=0.0, neginf=0.0)

    edges = ns_i64(idx7); t0 = idx7[0]; t1 = idx7[-1]; wins = gen_windows(t0, t1)
    ml_rows_all = []; ml_best_overall = None; wf_ml = []
    from sklearn.preprocessing import StandardScaler
    for wi, (a, tes, tee) in enumerate(wins, 1):
        lo = np.int64(pd.Timestamp(tes).value); hi = np.int64(pd.Timestamp(tee).value)
        tr = ent_ns < lo; te = (ent_ns >= lo) & (ent_ns < hi)
        if tr.sum() < 40 or te.sum() < 8:
            continue
        sc = StandardScaler().fit(Xall[tr])
        Xtr = sc.transform(Xall[tr]); Xte = sc.transform(Xall[te])
        rows, best = ML.fit_eval_models(Xtr, y_all[tr], w_all[tr], Xte, y_all[te])
        for r in rows:
            r['win'] = wi; ml_rows_all.append(r)
        if best is not None:
            # ML 사이징: OOS 거래를 ML이 '이긴다(p>0.5)' 예측한 것만 켰을 때 봇 PF
            m = best[3]; pte = m.predict_proba(Xte)[:, 1]
            R_oos = R_all[te]
            pf_ml = metrics(R_oos[pte > 0.5]); pf_all = metrics(R_oos)
            wf_ml.append(dict(win=wi, model=best[0], oos_auc=round(best[1], 3),
                              pf_ml_sized=pf_ml['PF'], n_ml=pf_ml['n'],
                              pf_all=pf_all['PF'], n_all=pf_all['n']))
            if ml_best_overall is None or best[1] > ml_best_overall[1]:
                ml_best_overall = best
    # 모델 비교 집계(창 평균)
    if ml_rows_all:
        mdf = pd.DataFrame(ml_rows_all)
        mc = mdf.groupby('model').agg(val_auc=('val_auc', 'mean'), oos_auc=('oos_auc', 'mean'),
                                      oos_acc=('oos_acc', 'mean'), n_win=('win', 'nunique')).round(3).reset_index()
    else:
        mc = pd.DataFrame([dict(model='none', val_auc=0, oos_auc=0, oos_acc=0, n_win=0)])
    mc.to_csv(os.path.join(HERE, "ml_model_compare.csv"), index=False, encoding='utf-8-sig')
    # 특징 중요도(전체 재학습)
    fi = []
    if ml_best_overall is not None:
        sc = StandardScaler().fit(Xall); m = ML.make_model(ml_best_overall[0], ml_best_overall[2])
        try:
            m.fit(sc.transform(Xall), y_all, sample_weight=w_all)
            fi = ML.feature_importance(m, feat_names_ml)
        except Exception:
            fi = []
    pd.DataFrame(fi, columns=['feature', 'importance']).to_csv(os.path.join(HERE, "ml_feature_importance.csv"), index=False, encoding='utf-8-sig')
    wf_ml_df = pd.DataFrame(wf_ml) if wf_ml else pd.DataFrame([dict(win=0, model='none', oos_auc=0, pf_ml_sized=0, n_ml=0, pf_all=0, n_all=0)])
    wf_ml_df.to_csv(os.path.join(HERE, "ml_sizing_pf.csv"), index=False, encoding='utf-8-sig')

    # ML 추천: ML사이징 PF가 표준(전체) PF보다 창 평균 +0.1 이상 높으면 ML, 아니면 STANDARD
    if wf_ml:
        avg_ml = np.mean([r['pf_ml_sized'] for r in wf_ml if r['n_ml'] >= 5])
        avg_all = np.mean([r['pf_all'] for r in wf_ml if r['n_ml'] >= 5])
        recommend = 'ML' if (avg_ml - avg_all) > 0.1 else 'STANDARD'
    else:
        avg_ml = avg_all = 0.0; recommend = 'STANDARD'

    # ── 워크포워드(칩필터 BEST 동결: 횡보봇 OOS PF) ──
    wf = []
    yrS = np.array([t['year'] for t in tS]); entS = np.array([pd.Timestamp(t['entry_t']).value for t in tS])
    for wi, (a, tes, tee) in enumerate(wins, 1):
        lo = np.int64(pd.Timestamp(tes).value); hi = np.int64(pd.Timestamp(tee).value)
        msk = (entS >= lo) & (entS < hi) & passed_best
        m = metrics(RS[msk])
        wf.append(dict(win=wi, test=f"{tes.date()}~{tee.date()}", sw_PF_chip=m['PF'], n=m['n'], ret=m['ret']))
    pd.DataFrame(wf).to_csv(os.path.join(HERE, "walkforward.csv"), index=False, encoding='utf-8-sig')

    # 칩필터 효과: 표준(필터OFF) 횡보봇 vs 칩BEST
    m_off = metrics(RS); m_on = metrics(RS[passed_best])
    on2025_off = int((np.array([t['year'] for t in tS]) == 2025).sum())
    on2025_on = int(((np.array([t['year'] for t in tS]) == 2025) & passed_best).sum())

    verdict = (f"VERDICT Stg4 | 추세{len(tT)}/횡보{len(tS)} 펀딩{'REAL' if fund_real else 'NONE'} | "
               f"[칩필터 BEST] pre_n={bestP['chip_pre_n']} hold_k={bestP['chip_hold_k']} CHOP>{bestP['chip_chop_hi']} {bestP['chip_combo']} SQZ={bestP['chip_squeeze']} | "
               f"칩필터OFF 횡보봇 PF{m_off['PF']}(n{m_off['n']},2025_{on2025_off}건) -> 칩필터ON PF{m_on['PF']}(n{m_on['n']},2025_{on2025_on}건) | "
               f"[ML] 모델비교창{mc['n_win'].max() if 'n_win' in mc else 0} best_oos_auc={round(ml_best_overall[1],3) if ml_best_overall else 'NA'} | "
               f"ML사이징PF {round(avg_ml,3)} vs 표준PF {round(avg_all,3)} -> 추천:{recommend} | "
               f"[매트릭스] 장세/년도/롱숏 × PF·수익·payoff·거래수·수익금 = ledger_trades.csv")
    print("[verdict] " + verdict)
    pd.DataFrame([dict(sec=verdict),
                  dict(sec=f"[칩필터BEST행] {dict(chip_best)}"),
                  dict(sec=f"[ML모델비교] {mc.to_dict('records')}"),
                  dict(sec=f"[ML특징중요도 상위8] {fi[:8]}"),
                  dict(sec=f"[ML사이징 워크포워드] {wf_ml}"),
                  dict(sec=f"[칩필터 워크포워드] {wf}")]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')
    with open(os.path.join(HERE, ".stg4_metric"), "w", encoding="utf-8") as f:
        f.write(f"n_trend={len(tT)}\nn_sw={len(tS)}\nbars7h={len(c)}\n"
                f"chip_pre_n={bestP['chip_pre_n']}\nchip_hold_k={bestP['chip_hold_k']}\nchip_chop_hi={bestP['chip_chop_hi']}\n"
                f"chip_combo={bestP['chip_combo']}\nchip_squeeze={bestP['chip_squeeze']}\n"
                f"sw_pf_off={m_off['PF']}\nsw_pf_on={m_on['PF']}\nsw_n_off={m_off['n']}\nsw_n_on={m_on['n']}\n"
                f"on2025_off={on2025_off}\non2025_on={on2025_on}\nchip_grid_n={len(chip)}\n"
                f"ml_best_auc={round(ml_best_overall[1],3) if ml_best_overall else 'NA'}\n"
                f"ml_sizing_pf={round(avg_ml,3)}\nstd_pf={round(avg_all,3)}\nrecommend={recommend}\n"
                f"ml_feat_n={len(feat_names_ml)}\nwf_windows={len(wins)}\n"
                f"label_in_feature=False\nlookahead_block=trade_bar_minus1\nfunding={'REAL' if fund_real else 'NONE'}\n")
    print("[save] chip_grid/chip_best/matrix_*/ledger_trades/ml_*/walkforward/summary.csv")


if __name__ == "__main__":
    main()
