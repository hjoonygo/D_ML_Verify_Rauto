# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch5_RAUTO_AlphaUp_Stg13_MLRegimeHurst.py
# 코드길이: 약 430줄 | 내부버전: RAUTO_AlphaUp_06_Ch5_Stg13_MLRegimeHurst | 로직 전체 출력
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   엔진 무수정. "장세판별만 정확하면 확실한 알파"(Stg11 입증) → 그 판별을 ML 다특징×다TF로 끝까지 본다.
#   검색 근거: HMM/ML 다특징·다TF가 표준, Hurst지수가 추세성 강건척도(2026 논문), XGBoost BTC천장~56%.
#
#   [1단계 특징(전부 인과적·과거봉)] — 7h봉 기준, 일부는 다TF(15m/1h/4h)에서 계산해 7h에 매칭:
#     ★신규: Hurst지수(R/S, 64봉창) / 실현변동성(rv10) / 변동성백분위 / norm_atr기울기
#     기존(Stg6): er adx chop atrcmp bandw drop vol_z oi_zscore_24h
#                 + 문서장세특징 atr_ratio adx_chg ema_fan ema20_slope bb_width_pct norm_atr feat_struct/break_*
#                 + 진짜CVD(cvd_press,taker_ratio) + 마이크로(taker_imbalance,top_retail_divergence)
#     ★다TF: Hurst·rv·atr_ratio를 15m/1h/4h에서도 계산 → '_tf15','_tf60','_tf240' 접미사로 추가
#   [2단계 ML 비교] 로지스틱 / RandomForest / GradientBoosting — 시간분할 OOS 4장세 정확도 + 추세이분 AUC
#   [3단계 특징중요도] RF 중요도 상위 — Hurst가 검색말대로 강한지 확인
#   [4단계 사이징 재검] 최고 분류기의 예측장세로 Stg11식 사이징(추세장 가점) → PF·수익·MDD·청산
#   [★lookahead 차단] label_smc_*는 타깃 전용(특징 절대 미포함, check 검증). 임계·스케일러 학습기간만 fit.
#
# [PATH] 실행: D:\ML\Verify\06Prj_..._Stg13_MLRegimeHurst\ . 데이터: 상위 (4종).
# [OUTPUT] ml_model_compare.csv / feature_importance.csv / confusion_best.csv / sizing_recheck.csv / summary.csv + .stg13_metric
# ==============================================================================
import os, sys, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE); BOTS = os.path.join(HERE, "bots")
COST_RT = 0.0014
REGIME_MAP = {'uptrend': 0, 'downtrend': 1, 'volatile_range': 2, 'dead_range': 3}
REGIME_NAME = {0: 'uptrend', 1: 'downtrend', 2: 'volatile_range', 3: 'dead_range', -1: 'unknown'}
DOC_REGIME = ['atr_ratio', 'adx_chg', 'ema_fan', 'ema20_slope', 'bb_width_pct', 'norm_atr']
DOC_MICRO = ['taker_imbalance_5m_avg', 'top_retail_divergence', 'oi_change_1h_pct']
try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    HAVE_SK = True
except Exception:
    HAVE_SK = False


def load_engine(p, nm):
    s = importlib.util.spec_from_file_location(nm, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def find_file(c):
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for x in c:
            p = os.path.join(d, x)
            if os.path.exists(p):
                return p
    return None


champ = load_engine(os.path.join(BOTS, "SpTrd_Fib_V1_Champion.py"), "champ_engine")
sdca = load_engine(os.path.join(BOTS, "SidewayDCA_Stg7_engine.py"), "sdca_engine")
DATA = find_file(["Merged_Data_with_Regime_Features.csv", "merged_data.csv"])
OIPATH = find_file(["Merged_Data.csv", "merged_data.csv"])
CVDPATH = find_file(["CVD_15m_BTCUSDT.csv", "sample_CVD_15m_BTCUSDT.csv"])
FUND = find_file(["BTCUSDT_funding_history_8h.csv", "funding_history_8h.csv", "sample_BTCUSDT_funding_history_8h.csv"])
NOMINAL = champ.NOMINAL; START_CAP = champ.START_CAP; MIN_CAP = champ.MIN_CAP
TF7 = champ.TF_MIN


def hurst_rs(x):
    # R/S 헤스트 지수(간이). x=가격 배열(창). 0.5=랜덤,>0.5=추세,<0.5=평균회귀.
    x = np.asarray(x, float); n = len(x)
    if n < 16 or np.any(~np.isfinite(x)):
        return np.nan
    r = np.diff(np.log(x))
    if len(r) < 8 or np.std(r) == 0:
        return np.nan
    mean = r.mean(); dev = np.cumsum(r - mean); R = dev.max() - dev.min(); S = r.std()
    if S == 0 or R <= 0:
        return np.nan
    return np.log(R / S) / np.log(len(r))


def auc_bin(y, sc):
    y = np.asarray(y); sc = np.asarray(sc, float); ok = ~np.isnan(sc); y = y[ok]; sc = sc[ok]
    p = int((y == 1).sum()); q = int((y == 0).sum())
    if p == 0 or q == 0:
        return 0.5
    o = sc.argsort(kind='mergesort'); r = np.empty(len(sc)); r[o] = np.arange(1, len(sc) + 1)
    return float((r[y == 1].sum() - p * (p + 1) / 2) / (p * q))


def metrics(R):
    R = np.asarray(R, float); n = len(R)
    if n == 0:
        return dict(n=0, PF=0.0, ret_pct=0.0, payoff=0.0, win_pct=0.0)
    win = R[R > 0]; los = R[R < 0]; gp = float(win.sum()); gl = float(-los.sum())
    pf = round(gp / gl, 3) if gl > 0 else (999.0 if gp > 0 else 0.0)
    payoff = round(win.mean() / -los.mean(), 3) if len(win) and len(los) else 0.0
    return dict(n=n, PF=pf, ret_pct=round(R.sum() * 100, 2), payoff=payoff, win_pct=round(100 * len(win) / n, 1))


def sim(R, size, comp=True):
    cap = START_CAP; peak = START_CAP; mdd = 0.0; liq = False
    for r, s in zip(R, size):
        if comp:
            cap *= (1 + r * s)
        else:
            cap += r * s * NOMINAL
        peak = max(peak, cap)
        if peak > 0:
            mdd = min(mdd, (cap - peak) / peak)
        if cap <= MIN_CAP:
            liq = True; break
    return round(cap - START_CAP, 0), round(mdd * 100, 1), liq


def resample_last(s, tf, idx):
    return s.resample(f"{tf}min", label='left', closed='left').last().reindex(idx).values.astype('float64')


def main():
    print(f"[Stg13] ML 다특징×다TF 장세분류 + Hurst | sklearn={'O' if HAVE_SK else 'X'}")
    open(os.path.join(HERE, ".run_start"), "w").close()
    if DATA is None or not HAVE_SK:
        pd.DataFrame([{'x': '데이터없음' if DATA is None else 'sklearn없음'}]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig'); return

    head = list(pd.read_csv(DATA, nrows=1).columns)
    lbl = next((c for c in head if c.startswith('label_smc_8')), None) or next((c for c in head if c.startswith('label_smc')), None)
    feat_cols = [c for c in head if c.startswith('feat_struct') or c.startswith('feat_break')]
    reg_cols = [c for c in DOC_REGIME if c in head]

    df1m = champ.load_data(DATA); df7 = champ.resample_tf(df1m, TF7); sig = champ.compute_signals(df7)
    idx = df7.index; close = df7['close'].values; n_bar = len(idx); i_of = {t: k for k, t in enumerate(idx)}
    oi = champ.load_oi_8h(OIPATH, idx)

    raw = pd.read_csv(DATA, usecols=['timestamp', lbl] + (['volume'] if 'volume' in head else []) + reg_cols + feat_cols,
                      index_col='timestamp', parse_dates=True)
    if getattr(raw.index, 'tz', None) is not None:
        raw.index = raw.index.tz_localize(None)
    raw = raw.sort_index()
    regime = raw[lbl].resample(f"{TF7}min", label='left', closed='left').last().reindex(idx).map(REGIME_MAP).values.astype('float64')

    # ── 기본 7h 특징 ──
    fmap = {'er': sig['er'], 'adx': sig['adx'], 'chop': sig['chop'], 'atrcmp': sig['atrcmp'],
            'bandw': sig['bandw'], 'drop': sig['drop'], 'oi_zscore_24h': oi}
    for c in reg_cols + feat_cols:
        col = raw[c]
        if col.dtype == object:
            col = pd.to_numeric(col, errors='coerce')
        fmap[c] = resample_last(col, TF7, idx)
    if 'volume' in raw:
        vol = raw['volume'].resample(f"{TF7}min", label='left', closed='left').sum().reindex(idx).values.astype('float64')
        fmap['vol_z'] = np.array([(vol[i]-np.nanmean(vol[max(0,i-19):i+1]))/(np.nanstd(vol[max(0,i-19):i+1]) or 1) for i in range(n_bar)])
    # 마이크로
    oih = list(pd.read_csv(OIPATH, nrows=1).columns)
    mcols = [c for c in DOC_MICRO if c in oih]
    if mcols:
        md = pd.read_csv(OIPATH, usecols=['timestamp']+mcols, index_col='timestamp', parse_dates=True)
        if getattr(md.index, 'tz', None) is not None:
            md.index = md.index.tz_localize(None)
        md = md.sort_index()
        for c in mcols:
            fmap[c] = resample_last(md[c], TF7, idx)
    # CVD
    if CVDPATH:
        ch = list(pd.read_csv(CVDPATH, nrows=1).columns)
        if 'taker_buy' in ch and 'volume' in ch:
            cd = pd.read_csv(CVDPATH, usecols=['timestamp', 'volume', 'taker_buy']+(['delta'] if 'delta' in ch else []),
                             index_col='timestamp', parse_dates=True)
            if getattr(cd.index, 'tz', None) is not None:
                cd.index = cd.index.tz_localize(None)
            cd = cd.sort_index()
            rr = cd.resample(f"{TF7}min", label='left', closed='left').sum().reindex(idx)
            v = rr['volume'].values.astype('float64'); tb = rr['taker_buy'].values.astype('float64')
            dl = rr['delta'].values.astype('float64') if 'delta' in cd else (2*tb-v)
            fmap['cvd_press'] = np.divide(dl, v, out=np.zeros(n_bar), where=v > 0)
            fmap['taker_ratio'] = np.divide(tb, v, out=np.full(n_bar, .5), where=v > 0)

    # ── ★신규: Hurst·실현변동성·변동성백분위 (7h) ──
    logret = np.concatenate([[0.0], np.diff(np.log(close))])
    rv10 = np.array([np.std(logret[max(0, i-9):i+1]) for i in range(n_bar)])
    fmap['rv10'] = rv10
    fmap['rv_pctile'] = np.array([(rv10[i] >= rv10[max(0, i-49):i+1]).mean() for i in range(n_bar)])
    hurst = np.full(n_bar, np.nan)
    for i in range(n_bar):
        if i >= 64:
            hurst[i] = hurst_rs(close[i-64:i+1])
    fmap['hurst'] = hurst
    na = fmap['norm_atr'] if 'norm_atr' in fmap else fmap.get('atr_ratio', np.zeros(n_bar))
    fmap['natr_slope'] = np.array([na[i]-na[max(0, i-6)] for i in range(n_bar)])

    # ── ★다TF: Hurst·rv·atr_ratio를 15m/1h/4h에서 → 7h매칭 ──
    for tf, suf in [(15, '_tf15'), (60, '_tf60'), (240, '_tf240')]:
        ctf = df1m['close'].resample(f"{tf}min", label='left', closed='left').last().dropna()
        cv = ctf.values; lr = np.concatenate([[0.0], np.diff(np.log(cv))])
        rvt = pd.Series([np.std(lr[max(0, j-9):j+1]) for j in range(len(cv))], index=ctf.index)
        hu = pd.Series([hurst_rs(cv[j-64:j+1]) if j >= 64 else np.nan for j in range(len(cv))], index=ctf.index)
        fmap['rv'+suf] = rvt.resample(f"{TF7}min", label='left', closed='left').last().reindex(idx).values.astype('float64')
        fmap['hurst'+suf] = hu.resample(f"{TF7}min", label='left', closed='left').last().reindex(idx).values.astype('float64')

    fmap = {k: v for k, v in fmap.items() if 'label' not in k.lower()}   # lookahead 차단
    FEATS = list(fmap.keys())
    X = np.column_stack([fmap[f] for f in FEATS]).astype('float64')
    X = np.where(np.isnan(X), np.nanmean(X, axis=0), X); X = np.where(np.isnan(X), 0.0, X)

    valid = ~np.isnan(regime)
    order = np.argsort(idx.values); cut = int(n_bar*0.7)
    tr = np.array([b for b in order[:cut] if valid[b]]); te = np.array([b for b in order[cut:] if valid[b]])
    yreg = regime.astype(int)
    sc = StandardScaler().fit(X[tr]); Xz = sc.transform(X)   # 학습기간만 fit

    # ── 2단계: ML 비교 ──
    models = {'LogReg': LogisticRegression(max_iter=1000, C=0.5, class_weight='balanced'),
              'RandForest': RandomForestClassifier(n_estimators=300, max_depth=7, random_state=0, class_weight='balanced'),
              'GradBoost': GradientBoostingClassifier(n_estimators=200, max_depth=3, random_state=0)}
    maj = round(100*float(pd.Series(yreg[tr]).value_counts(normalize=True).max()), 1)
    comp_rows = []; best_name = None; best_acc = -1; best_model = None
    for nm, mdl in models.items():
        try:
            Xfit = Xz if nm != 'RandForest' else X
            mdl.fit(Xfit[tr], yreg[tr])
            pred = mdl.predict(Xfit[te]); acc = round(100*float((pred == yreg[te]).mean()), 1)
            # 추세이분 AUC(P_up+P_down)
            proba = mdl.predict_proba(Xfit[te])
            ptrend = proba[:, 0] + proba[:, 1] if proba.shape[1] >= 2 else proba[:, 0]
            ytr_bin = np.isin(yreg[te], [0, 1]).astype(int)
            auc = round(auc_bin(ytr_bin, ptrend), 3)
            comp_rows.append(dict(model=nm, acc4=acc, baseline=maj, beats=('YES' if acc > maj else 'NO'), trend_auc=auc))
            if acc > best_acc:
                best_acc = acc; best_name = nm; best_model = mdl; best_X = Xfit
        except Exception as e:
            comp_rows.append(dict(model=nm, err=str(e)[:40]))
    pd.DataFrame(comp_rows).to_csv(os.path.join(HERE, "ml_model_compare.csv"), index=False, encoding='utf-8-sig')

    # ── 3단계: 특징중요도(RF) ──
    try:
        rf = models['RandForest']
        imp = sorted(zip(FEATS, rf.feature_importances_), key=lambda x: -x[1])
        pd.DataFrame([dict(feature=f, importance=round(float(v), 4)) for f, v in imp]).to_csv(
            os.path.join(HERE, "feature_importance.csv"), index=False, encoding='utf-8-sig')
        hurst_rank = [i for i, (f, _) in enumerate(imp) if 'hurst' in f]
        top_feat = imp[0][0]
    except Exception:
        hurst_rank = []; top_feat = 'NA'

    # 혼동행렬(best)
    predA = best_model.predict(best_X)
    conf = np.zeros((4, 4), int)
    for a, p in zip(yreg[te], predA[te]):
        conf[int(a), int(p)] += 1
    pd.DataFrame(conf, index=[f'실제_{REGIME_NAME[i]}' for i in range(4)],
                 columns=[f'예측_{REGIME_NAME[i]}' for i in range(4)]).to_csv(os.path.join(HERE, "confusion_best.csv"), encoding='utf-8-sig')

    # ── 4단계: 최고 분류기로 사이징 재검 ──
    ft = fr = None
    if FUND:
        try:
            ft, fr = sdca.load_funding(FUND)
        except Exception:
            pass

    def fund_pay(side, et, xt):
        if ft is None:
            return 0.0
        fs = sdca.funding_sum(ft, fr, int(pd.Timestamp(et).value), int(pd.Timestamp(xt).value))
        return side*fs if fs is not None else 0.0
    bb7 = champ.load_bb_8h(DATA, idx)
    ttr = champ.run_strategy(df7, sig, 0, 'none', 0.8, gate_mode='er', gate_er=0.45,
                             dz_oi=oi, gate_bb=bb7, fib=(0.3, 0.5, 0.6), split_mode='A', split_n=3)
    pred_all = best_model.predict(best_X)   # 각 7h봉 예측장세
    recs = []
    for t in ttr:
        R = t['side']*(t['exit']-t['entry'])/t['entry'] - COST_RT - fund_pay(t['side'], t['entry_t'], t['exit_t'])
        pos = i_of.get(t['entry_t'], None)
        if pos is None:
            p2 = idx.searchsorted(pd.Timestamp(t['entry_t']))-1; pos = max(0, p2)
        pr = pred_all[pos] if 0 <= pos < len(pred_all) else -1
        recs.append(dict(side='롱' if t['side'] > 0 else '숏', pred_reg=REGIME_NAME[int(pr)] if pr >= 0 else 'unknown',
                         R=float(R), is_test=pos >= cut))
    dft = pd.DataFrame(recs)
    # 사이징: 예측이 추세장(상승/하락)이면 가점, 횡보면 감점 (보수 배수)
    base_R = dft.R.values
    size = np.where(dft.pred_reg.isin(['uptrend', 'downtrend']), 1.5, 0.6)
    R_sized = base_R * size
    mb = metrics(base_R); ms = metrics(R_sized)
    prof_b, mdd_b, liq_b = sim(base_R, np.ones(len(base_R)))
    prof_s, mdd_s, liq_s = sim(base_R, size)
    tem = dft.is_test.values
    mb_oos = metrics(base_R[tem]); ms_oos = metrics(R_sized[tem])
    pd.DataFrame([dict(seg='전체', kind='base', **mb, profit=round(float(base_R.sum()*NOMINAL))),
                  dict(seg='전체', kind='ML사이징', **ms, profit=round(float(R_sized.sum()*NOMINAL))),
                  dict(seg='검증OOS', kind='base', **mb_oos),
                  dict(seg='검증OOS', kind='ML사이징', **ms_oos)]).to_csv(
        os.path.join(HERE, "sizing_recheck.csv"), index=False, encoding='utf-8-sig')

    beats_any = any(r.get('beats') == 'YES' for r in comp_rows)
    flag = (f"ML판별 기준선돌파({best_name} {best_acc}%) → 사이징 재검 유효성은 sizing_recheck 참조"
            if beats_any else f"ML판별도 기준선미달(best {best_name} {best_acc}%) — 장세판별 한계 재확인")
    verdict = (f"VERDICT Stg13 | ML×다특징({len(FEATS)})×다TF + Hurst | "
               f"best {best_name} acc {best_acc}%(기준선{maj}%) | 모델비교 {[(r.get('model'),r.get('acc4')) for r in comp_rows]} | "
               f"Hurst중요도순위 {hurst_rank} top특징 {top_feat} | "
               f"사이징재검(추세장1.5/횡보0.6): base {mb['ret_pct']}%/MDD{mdd_b} -> ML {ms['ret_pct']}%/MDD{mdd_s}(청산{'Y' if liq_s else 'N'}) | "
               f"OOS base {mb_oos['ret_pct']}% -> ML {ms_oos['ret_pct']}% | => {flag}")
    print("[verdict] " + verdict)
    pd.DataFrame([dict(sec=verdict), dict(sec=f"[특징 {len(FEATS)}개] {', '.join(FEATS)}")]).to_csv(
        os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')
    with open(os.path.join(HERE, ".stg13_metric"), "w", encoding="utf-8") as f:
        f.write(f"best_model={best_name}\nbest_acc={best_acc}\nbaseline={maj}\nbeats_any={'YES' if beats_any else 'NO'}\n"
                f"n_feats={len(FEATS)}\nhurst_rank={hurst_rank}\ntop_feat={top_feat}\nhas_label_in_feats={'label' in '|'.join(FEATS).lower()}\n"
                f"base_ret={mb['ret_pct']}\nml_ret={ms['ret_pct']}\nbase_mdd={mdd_b}\nml_mdd={mdd_s}\nml_liq={'YES' if liq_s else 'NO'}\n"
                f"oos_base_ret={mb_oos['ret_pct']}\noos_ml_ret={ms_oos['ret_pct']}\nfunding={'REAL' if ft is not None else 'NONE'}\n"
                f"model_rows={len(comp_rows)}\n")
    print("[save] ml_model_compare/feature_importance/confusion_best/sizing_recheck/summary.csv")


if __name__ == "__main__":
    main()
