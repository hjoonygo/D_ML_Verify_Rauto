# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch5_RAUTO_ConceptRefine_Stg6_RegimeReferee.py
# 코드길이: 약 430줄 | 내부버전: RAUTO_ConceptRefine_06_Ch5_Stg6_RegimeReferee | 로직 전체 출력
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   챔피언 시스템의 심장 '장세 심판'이 데이터로 성립하는지 정직하게(시간분할 OOS) 검증. 엔진 무수정.
#   ★출혈예측(Stg5)과 다른 점: 제대로 된 정답지 label_smc(4장세)와 전용 실시간특징 feat_*가 있다.
#   8시나리오:
#     1) 4장세(label_smc) OOS 분류정확도 vs 다수클래스 기준선
#     2) 장세별 one-vs-rest AUC + 4x4 혼동행렬(어디서 헷갈리나)
#     3) 추세 vs 비추세 이분 OOS AUC (라우팅 핵심 신호)
#     4) 변동성 방향 상태(확대/축소/정체, 인과적) 분류 + 그 상태별 추세봇 성과·잭팟 집중
#     5) 봇 x 실제장세: 추세봇/횡보봇 R을 실제 장세별로 (라우팅 전제 검증)
#     6) ★라우팅 시뮬: OOS 예측 추세장에서만 추세봇 풀노출, 비추세장 축소 → 검증기간 자본곡선 vs 항상풀
#     7) 다중 TF(4h/8h/12h/1d) 추세이분 OOS AUC (어느 봉에서 가장 또렷한가)
#     8) 종합판정: 라우팅이 OOS에서 잭팟 지키며(보존>=85%) MDD 의미있게↓/수익↑ ? → 심판채택 / 아니면 두봇병행
#
#   [라벨 y(정답지=타깃 전용, 절대 특징 아님)] label_smc_8: uptrend0/downtrend1/volatile_range2/dead_range3.
#   [특징 X(실시간 안전, 인과적)] feat_struct_*/feat_break_* + atr_ratio adx_chg ema_fan ema20_slope
#     bb_width_pct norm_atr + 엔진 er adx chop atrcmp bandw drop + CVD(진짜) + 마이크로(oi_z/taker/top_retail) + vol_z
#   [★lookahead 하드차단] label_* 접두 컬럼은 특징에서 전부 제외(정답지). 모든 특징 과거봉만. 시간분할 OOS.
#   [변동성 방향] norm_atr 최근6봉 기울기 부호로 확대/축소/정체(과거봉만=인과적 '상태', 예측 아님).
#
# [PATH] 실행: D:\ML\Verify\06Prj_..._Stg6_RegimeReferee\ . 데이터: 상위 D:\ML\Verify\ (4종).
# [OUTPUT] stg6_summary.csv + regime_oos.csv + bot_by_regime.csv + routing_sim.csv + .stg6_metric
# ==============================================================================
import os, sys, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
BOTS = os.path.join(HERE, "bots")
try:
    from sklearn.ensemble import RandomForestClassifier
    HAVE_SK = True
except Exception:
    HAVE_SK = False

COST_RT = 0.0014
REGIME_MAP = {'uptrend': 0, 'downtrend': 1, 'volatile_range': 2, 'dead_range': 3}
REGIME_NAME = {0: 'uptrend', 1: 'downtrend', 2: 'volatile_range', 3: 'dead_range'}
DOC_REGIME = ['atr_ratio', 'adx_chg', 'ema_fan', 'ema20_slope', 'bb_width_pct', 'norm_atr']
DOC_MICRO = ['taker_imbalance_5m_avg', 'top_retail_divergence', 'oi_change_1h_pct']
SWING = 8                  # label_smc_8 (중간 스윙)
TFS = [240, 480, 720, 1440]   # 다중 TF: 4h/8h/12h/1d


def load_engine(p, nm):
    s = importlib.util.spec_from_file_location(nm, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def find_file(cands):
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for c in cands:
            p = os.path.join(d, c)
            if os.path.exists(p):
                return p
    return None


champ = load_engine(os.path.join(BOTS, "SpTrd_Fib_V1_Champion.py"), "champ_engine")
sdca = load_engine(os.path.join(BOTS, "SidewayDCA_Stg7_engine.py"), "sdca_engine")
DATA = find_file(["Merged_Data_with_Regime_Features.csv", "merged_data.csv"])
OIPATH = find_file(["Merged_Data.csv", "merged_data.csv"])
CVDPATH = find_file(["CVD_15m_BTCUSDT.csv", "sample_CVD_15m_BTCUSDT.csv"])
TF7 = champ.TF_MIN


def _tz(df):
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    return df.sort_index()


def resample_last(s, tf, idx):
    return s.resample(f"{tf}min", label='left', closed='left').last().reindex(idx).values.astype('float64')


def auc_rank(y, sc):
    y = np.asarray(y); sc = np.asarray(sc, float); ok = ~np.isnan(sc); y = y[ok]; sc = sc[ok]
    p = int((y == 1).sum()); q = int((y == 0).sum())
    if p == 0 or q == 0:
        return 0.5
    o = sc.argsort(kind='mergesort'); r = np.empty(len(sc)); r[o] = np.arange(1, len(sc) + 1)
    return float((r[y == 1].sum() - p * (p + 1) / 2) / (p * q))


def logreg_fit(X, y, it=600, lr=0.3, l2=1e-3):
    w = np.zeros(X.shape[1]); b = 0.0; m = len(y)
    for _ in range(it):
        p = 1 / (1 + np.exp(-np.clip(X @ w + b, -30, 30)))
        w -= lr * (X.T @ (p - y) / m + l2 * w); b -= lr * float((p - y).mean())
    return w, b


def predict(X, w, b):
    return 1 / (1 + np.exp(-np.clip(X @ w + b, -30, 30)))


def sim(R, size):
    cap = 1.0; peak = 1.0; mdd = 0.0
    for r, s in zip(R, size):
        cap *= (1 + r * s); peak = max(peak, cap); mdd = min(mdd, (cap - peak) / peak)
    return round((cap - 1) * 100, 1), round(mdd * 100, 1)


def main():
    print(f"[Stg6] 장세 심판 OOS 검증 | sklearn={'O' if HAVE_SK else 'X'}")
    open(os.path.join(HERE, ".run_start"), "w").close()
    if DATA is None:
        pd.DataFrame([{'x': '데이터없음'}]).to_csv(os.path.join(HERE, "stg6_summary.csv"), index=False, encoding='utf-8-sig')
        print("[abort]"); return

    head = list(pd.read_csv(DATA, nrows=1).columns)
    lbl_col = f'label_smc_{SWING}' if f'label_smc_{SWING}' in head else next((c for c in head if c.startswith('label_smc')), None)
    if lbl_col is None:
        pd.DataFrame([{'x': 'label_smc 없음 — 장세심판 불가'}]).to_csv(os.path.join(HERE, "stg6_summary.csv"), index=False, encoding='utf-8-sig')
        print("[abort] label_smc 없음"); return
    feat_cols = [c for c in head if c.startswith('feat_struct') or c.startswith('feat_break')]
    reg_cols = [c for c in DOC_REGIME if c in head]
    print(f"[label] {lbl_col} | 장세특징 {reg_cols+feat_cols}")

    # 1분 원본 로드(라벨+특징+volume) — 한 번
    raw = _tz(pd.read_csv(DATA, usecols=['timestamp', lbl_col] + (['volume'] if 'volume' in head else []) + reg_cols + feat_cols,
                          index_col='timestamp', parse_dates=True))

    # 엔진 7h 신호 + 거래
    df1m = champ.load_data(DATA); df_tf = champ.resample_tf(df1m, TF7); sig = champ.compute_signals(df_tf)
    idx = df_tf.index; n_bar = len(idx); i_of = {t: k for k, t in enumerate(idx)}
    oi_arr = champ.load_oi_8h(OIPATH, idx); bb_arr = champ.load_bb_8h(DATA, idx)

    # 7h 특징/라벨
    lab_str = raw[lbl_col].resample(f"{TF7}min", label='left', closed='left').last().reindex(idx)
    regime = lab_str.map(REGIME_MAP).values.astype('float64')
    feats7 = {}
    for c in reg_cols + feat_cols:
        col = raw[c]
        if col.dtype == object:
            col = pd.to_numeric(col, errors='coerce')
        feats7[c] = resample_last(col, TF7, idx)
    vol = (raw['volume'].resample(f"{TF7}min", label='left', closed='left').sum().reindex(idx).values.astype('float64')
           if 'volume' in raw else np.ones(n_bar))
    vol_z = np.array([(vol[i] - np.nanmean(vol[max(0, i-19):i+1])) / (np.nanstd(vol[max(0, i-19):i+1]) or 1) for i in range(n_bar)])
    # 마이크로
    micro = {}
    oih = list(pd.read_csv(OIPATH, nrows=1).columns)
    mcols = [c for c in DOC_MICRO if c in oih]
    if mcols:
        md = _tz(pd.read_csv(OIPATH, usecols=['timestamp'] + mcols, index_col='timestamp', parse_dates=True))
        for c in mcols:
            micro[c] = resample_last(md[c], TF7, idx)
    # CVD(진짜)
    cvd = {}; cvd_mode = "CVD없음"
    if CVDPATH:
        ch = list(pd.read_csv(CVDPATH, nrows=1).columns)
        if 'taker_buy' in ch and 'volume' in ch:
            cd = _tz(pd.read_csv(CVDPATH, usecols=['timestamp', 'volume', 'taker_buy'] + (['delta'] if 'delta' in ch else []),
                                 index_col='timestamp', parse_dates=True))
            rr = cd.resample(f"{TF7}min", label='left', closed='left').sum().reindex(idx)
            v = rr['volume'].values.astype('float64'); tb = rr['taker_buy'].values.astype('float64')
            dl = rr['delta'].values.astype('float64') if 'delta' in cd else (2*tb - v)
            cvd['cvd_press'] = np.divide(dl, v, out=np.zeros(n_bar), where=v > 0)
            cvd['taker_ratio'] = np.divide(tb, v, out=np.full(n_bar, .5), where=v > 0)
            cvd_mode = "진짜CVD(taker_buy/delta)"

    # 특징맵(label 절대 제외)
    fmap = {'er': sig['er'], 'adx': sig['adx'], 'chop': sig['chop'], 'atrcmp': sig['atrcmp'],
            'bandw': sig['bandw'], 'drop': sig['drop'], 'vol_z': vol_z, 'oi_zscore_24h': oi_arr}
    fmap.update(feats7); fmap.update(micro); fmap.update(cvd)
    fmap = {k: v for k, v in fmap.items() if 'label' not in k.lower()}
    FEATS = list(fmap.keys())
    X = np.column_stack([fmap[f] for f in FEATS]).astype('float64')
    X = np.where(np.isnan(X), np.nanmean(X, axis=0), X); X = np.where(np.isnan(X), 0.0, X)

    valid = ~np.isnan(regime)
    bars_order = np.argsort(idx.values)
    cut = int(n_bar * 0.7)
    tr = np.array([b for b in bars_order[:cut] if valid[b]]); te = np.array([b for b in bars_order[cut:] if valid[b]])
    mu = X[tr].mean(0); sd = X[tr].std(0); sd[sd == 0] = 1; Xz = (X - mu) / sd
    yreg = regime.astype(int)

    # ── 시나리오1·2: 4장세 OvR ──
    probs = np.zeros((n_bar, 4))
    for cls in range(4):
        yb = (yreg == cls).astype(float)
        if yb[tr].sum() >= 5:
            w, b = logreg_fit(Xz[tr], yb[tr]); probs[:, cls] = predict(Xz, w, b)
    pred = probs.argmax(1)
    acc = round(float((pred[te] == yreg[te]).mean()) * 100, 1)
    maj = round(float(pd.Series(yreg[tr]).value_counts(normalize=True).max()) * 100, 1)
    perclass_auc = {REGIME_NAME[c]: round(auc_rank((yreg[te] == c).astype(int), probs[te, c]), 3) for c in range(4)}
    conf = np.zeros((4, 4), int)
    for a, p in zip(yreg[te], pred[te]):
        conf[a, p] += 1

    # ── 시나리오3: 추세 이분 OOS AUC (7h) ──
    ytr_bin = np.isin(yreg, [0, 1]).astype(float)
    wb, bb = logreg_fit(Xz[tr], ytr_bin[tr]); p_trend = predict(Xz, wb, bb)
    auc_bin7 = round(auc_rank(ytr_bin[te], p_trend[te]), 3)
    rf_bin7 = None
    if HAVE_SK and ytr_bin[tr].sum() >= 5:
        try:
            rf = RandomForestClassifier(n_estimators=200, max_depth=5, random_state=0, class_weight='balanced')
            rf.fit(Xz[tr], ytr_bin[tr]); rf_bin7 = round(auc_rank(ytr_bin[te], rf.predict_proba(Xz[te])[:, 1]), 3)
        except Exception:
            pass

    # ── 거래 ──
    trades = champ.run_strategy(df_tf, sig, 0, 'none', 0.8, gate_mode='er', gate_er=0.45,
                                dz_oi=oi_arr, gate_bb=bb_arr, fib=(0.3, 0.5, 0.6), split_mode='A', split_n=3)
    ft = fr = None
    fpath = find_file(["BTCUSDT_funding_history_8h.csv", "funding_history_8h.csv", "sample_BTCUSDT_funding_history_8h.csv"])
    if fpath:
        try:
            ft, fr = sdca.load_funding(fpath)
        except Exception:
            pass

    def realR(t):
        g = t['side'] * (t['exit'] - t['entry']) / t['entry']; fp = 0.0
        if ft is not None:
            fs = sdca.funding_sum(ft, fr, int(pd.Timestamp(t['entry_t']).value), int(pd.Timestamp(t['exit_t']).value))
            fp = t['side'] * fs if fs is not None else 0.0
        return g - COST_RT - fp
    R = np.array([realR(t) for t in trades]); n = len(trades)
    tre_bar = np.array([i_of[t['entry_t']] for t in trades])
    tr_regime = yreg[tre_bar]

    # ── 시나리오4: 변동성 방향 상태 ──
    natr = feats7.get('norm_atr', feats7.get('atr_ratio', np.zeros(n_bar)))
    slope = np.array([natr[i] - natr[max(0, i-6)] for i in range(n_bar)])
    sst = np.nanstd(slope) or 1.0
    voldir_bar = np.where(slope > 0.3*sst, 1, np.where(slope < -0.3*sst, -1, 0))  # 1확대/-1축소/0정체
    tr_voldir = voldir_bar[tre_bar]
    loss = R < 0; rec = []
    i = 0
    while i < n:
        if loss[i]:
            j = i
            while j+1 < n and loss[j+1]:
                j += 1
            if j-i+1 >= 2 and j+1 < n:
                rec.append(j+1)
            i = j+1
        else:
            i += 1
    rec = np.array(rec, int)
    jack_in_expand = round(100*float(np.mean(tr_voldir[rec] == 1)), 1) if len(rec) else 0.0
    voldir_R = {('확대' if d == 1 else '축소' if d == -1 else '정체'): round(float(R[tr_voldir == d].sum())*100, 1) for d in [1, -1, 0]}

    # ── 시나리오5: 봇 x 실제장세 ──
    botreg = {REGIME_NAME[c]: round(float(R[tr_regime == c].sum())*100, 1) for c in range(4)}
    # 횡보봇
    sdca_reg = {}
    try:
        s1 = sdca.load_1m(DATA); s8 = sdca.resample_tf(s1, sdca.TF_MIN); ss = sdca.precompute(s8)
        s_ss, s_se = sdca.build_1m_map(s1, s8)
        mO = s1['open'].values; mH = s1['high'].values; mL = s1['low'].values
        mT = s1.index.values.astype('datetime64[ns]').astype('int64')
        strd, _, _, _ = sdca.run_bot_honest(s8, ss, sdca.BEST_PAR, mO, mH, mL, mT, s_ss, s_se, ft, fr,
                                            sdca.DEFAULT_SLMULT, filter_mode='precise', atr_lo=sdca.ATR_LO, atr_hi=sdca.ATR_HI,
                                            filter_scens=sdca.FILTER_SCENS, oi_filter=True, oi_z_hi=1.0, oi_filter_scens=sdca.OI_FILTER_SCENS)
        # 횡보 거래를 7h regime에 매칭
        lab7 = pd.Series(regime, index=idx)
        for t in strd:
            et = pd.Timestamp(t['entry_t'])
            pos = lab7.index.searchsorted(et) - 1
            if 0 <= pos < n_bar and not np.isnan(regime[pos]):
                rn = REGIME_NAME[int(regime[pos])]; sdca_reg[rn] = sdca_reg.get(rn, 0.0) + float(t['R'])*100
        sdca_reg = {k: round(float(v), 1) for k, v in sdca_reg.items()}
    except Exception as e:
        sdca_reg = {'오류': str(e)[:40]}

    # ── 시나리오6: 라우팅 시뮬 (검증기간, OOS 예측 추세장 게이트) ──
    te_set = set(te.tolist())
    is_test = np.array([tre_bar[k] in te_set for k in range(n)])
    pred_trend_tr = (p_trend[tre_bar] >= 0.5)
    R_te = R[is_test]
    base_size = np.ones(is_test.sum())
    route_size = np.where(pred_trend_tr[is_test], 1.0, 0.4)   # 예측 비추세면 추세봇 노출 0.4
    cumR_b, mdd_b = sim(R_te, base_size); cumR_r, mdd_r = sim(R_te, route_size)
    rec_te = [k for k in rec if is_test[k]]
    jack_keep = round(100*float(np.mean([1.0 if pred_trend_tr[k] else 0.4 for k in rec_te])), 1) if rec_te else 100.0

    # ── 시나리오7: 다중 TF 추세이분 OOS AUC ──
    tf_auc = {}
    for tf in TFS:
        li = raw[lbl_col].resample(f"{tf}min", label='left', closed='left').last()
        yb = li.map(REGIME_MAP); ybin = yb.isin([0, 1]).astype(float).values
        Xtf = []
        for c in reg_cols + feat_cols:
            col = raw[c]
            if col.dtype == object:
                col = pd.to_numeric(col, errors='coerce')
            Xtf.append(col.resample(f"{tf}min", label='left', closed='left').last().values)
        Xtf = np.column_stack(Xtf).astype('float64')
        ok = ~np.isnan(yb.values) & ~np.isnan(Xtf).any(1)
        Xtf = Xtf[ok]; ybin = ybin[ok]
        if len(ybin) < 50:
            tf_auc[f"{tf//60}h" if tf < 1440 else "1d"] = None; continue
        ct = int(len(ybin)*0.7); mt = Xtf[:ct].mean(0); st = Xtf[:ct].std(0); st[st == 0] = 1; Xz2 = (Xtf-mt)/st
        w2, b2 = logreg_fit(Xz2[:ct], ybin[:ct])
        tf_auc[f"{tf//60}h" if tf < 1440 else "1d"] = round(auc_rank(ybin[ct:], predict(Xz2[ct:], w2, b2)), 3)

    # ── 저장 ──
    pd.DataFrame([dict(metric='4장세_정확도%', value=acc), dict(metric='다수클래스기준선%', value=maj),
                  dict(metric='추세이분_검증AUC_7h', value=auc_bin7), dict(metric='추세이분_RF_7h', value=rf_bin7)]
                 + [dict(metric=f'AUC_{k}', value=v) for k, v in perclass_auc.items()]
                 + [dict(metric=f'TF_{k}_추세AUC', value=v) for k, v in tf_auc.items()]).to_csv(
        os.path.join(HERE, "regime_oos.csv"), index=False, encoding='utf-8-sig')
    cm = pd.DataFrame(conf, index=[f'실제_{REGIME_NAME[i]}' for i in range(4)], columns=[f'예측_{REGIME_NAME[i]}' for i in range(4)])
    cm.to_csv(os.path.join(HERE, "confusion.csv"), encoding='utf-8-sig')
    pd.DataFrame([dict(bot='추세봇', **botreg), dict(bot='횡보봇', **sdca_reg)]).to_csv(
        os.path.join(HERE, "bot_by_regime.csv"), index=False, encoding='utf-8-sig')
    pd.DataFrame([dict(seg='검증기간 항상풀', cumR=cumR_b, MDD=mdd_b),
                  dict(seg='검증기간 라우팅', cumR=cumR_r, MDD=mdd_r, jackpot_keep=jack_keep)]).to_csv(
        os.path.join(HERE, "routing_sim.csv"), index=False, encoding='utf-8-sig')

    route_ok = (mdd_r > mdd_b) and (cumR_r >= cumR_b * 0.9) and (jack_keep >= 85)
    flag = "심판채택검토" if route_ok else "두봇병행이 나음(라우팅 무효)"
    best_tf = max([(k, v) for k, v in tf_auc.items() if v is not None], key=lambda x: x[1], default=('?', 0))
    verdict = (f"VERDICT Stg6 | CVD={cvd_mode} | label={lbl_col} 특징{len(FEATS)}개 | "
               f"4장세정확도 {acc}%(기준선{maj}%) | 추세이분 검증AUC {auc_bin7}(RF{rf_bin7}) | "
               f"장세별AUC {perclass_auc} | 변동성: 잭팟이 확대국면 비율 {jack_in_expand}%, R(확대/축소/정체) {voldir_R} | "
               f"봇x장세 추세봇 {botreg} / 횡보봇 {sdca_reg} | "
               f"라우팅(검증기간): 항상풀 {cumR_b}%/MDD{mdd_b} -> 라우팅 {cumR_r}%/MDD{mdd_r}, 잭팟보존{jack_keep}% | "
               f"다중TF 추세AUC {tf_auc}(best {best_tf[0]}={best_tf[1]}) | => {flag}")
    print("[verdict] " + verdict)

    out = [dict(sec=verdict), dict(sec=f'─ 특징 {len(FEATS)}개(label_smc 제외): {", ".join(FEATS)} ─'),
           dict(sec='─ 4장세 혼동행렬(행=실제, 열=예측) ─')]
    for i in range(4):
        out.append(dict(sec=f"  실제 {REGIME_NAME[i]}: " + ", ".join(f"{REGIME_NAME[j]}={conf[i,j]}" for j in range(4))))
    pd.DataFrame(out).to_csv(os.path.join(HERE, "stg6_summary.csv"), index=False, encoding='utf-8-sig')

    with open(os.path.join(HERE, ".stg6_metric"), "w", encoding="utf-8") as f:
        f.write(f"label={lbl_col}\nn_feats={len(FEATS)}\nhas_label_in_feats={'label' in '|'.join(FEATS).lower()}\n"
                f"cvd_mode={cvd_mode}\nacc4={acc}\nmaj={maj}\nauc_bin7={auc_bin7}\nrf_bin7={rf_bin7}\n"
                f"perclass={perclass_auc}\njack_expand={jack_in_expand}\n"
                f"route_base_cum={cumR_b}\nroute_base_mdd={mdd_b}\nroute_cum={cumR_r}\nroute_mdd={mdd_r}\nroute_jack={jack_keep}\n"
                f"tf_auc={tf_auc}\nverdict_flag={flag}\nhave_sklearn={HAVE_SK}\nn_trades={n}\n")
    print("[save] stg6_summary/regime_oos/bot_by_regime/routing_sim/confusion.csv")


if __name__ == "__main__":
    main()
