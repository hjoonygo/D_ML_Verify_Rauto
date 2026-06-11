# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch5_RAUTO_ConceptRefine_Stg4_StreakML.py
# 코드길이: 약 320줄 | 내부버전: RAUTO_ConceptRefine_06_Ch5_Stg4_StreakML | 로직 축약/생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   추세봇의 '연속손실 출혈 구간'을 진입 시점의 시장특징으로 미리 가를 수 있는지(=방어적 심판이
#   가능한지) ML로 진단한다. ★엔진 무수정(bots/ 원본). 엔진을 돌려 거래를 얻고, 라벨과 특징만 바깥계산.
#
#   [라벨 y] 손실=엔진R<0. 연속손실 run(중간에 이긴 거래 없이 R<0 연달은 최대구간) 길이 2+이면
#     in_streak=1(그 출혈에 속한 거래). streak_start=1은 그 run의 첫 거래(진짜 조기경보 대상).
#     ※라벨은 '미래 결과'라 예측 대상 — 허용. 특징은 전부 인과적이어야 함(아래).
#
#   [특징 X — 전부 인과적(과거봉만), 진입봉 i에서 알 수 있는 값] 엔진 compute_signals(과거봉만 보증)에서:
#     er(추세효율) adx chop atrcmp bandw drop  + 데이터 atr_ratio(7h) + oi_z(정산값) +
#     realized_vol(최근10봉 로그수익 표준편차) abs_ret(직전봉 변화) signflips(최근10봉 부호변경수).
#     ※모두 진입 '결정 시점(봉마감)'에 알 수 있는 값. 미래 안 봄.
#
#   [ML 다양하게]
#     ① 단변량: 특징별 in_streak/out 평균·효과크기·단일특징 AUC(순위기반, 과적합 없음).
#     ② 다변량: numpy 로지스틱회귀를 '시간분할(앞=학습, 뒤=검증)'로 학습→검증AUC. 정직한 표본외 예측력.
#        in_streak(출혈 중인지) / streak_start(출혈 시작인지) 둘 다.
#     ③ (sklearn 있으면) RandomForest 특징중요도 + KMeans 군집(출혈에도 종류가 있나). 없으면 생략.
#     ④ 횡보봇 성과: in_streak 구간 vs 정상 구간, 그리고 저ER vs 고ER 구간에서 횡보봇이 버는지.
#
#   [판정 기준] 검증AUC가 0.5면 '진입 시점 예측 불가'(심판은 늦은 반응만 가능 → 챔피언 논리 흔들림).
#     0.65+면 '인과적으로 가를 수 있음'(방어적 심판 토대 있음).
#
# [미래참조] 엔진 무수정. 특징 X는 전부 과거봉(<=i). 라벨 y만 미래(예측대상). 시간분할로 표본외만 평가.
# [PATH] 실행: D:\ML\verify\06Prj_Ch5_RAUTO_ConceptRefine_Stg4_StreakML\ . 데이터: 상위 D:\ML\verify\ .
# [DATA] (상위) Merged_Data_with_Regime_Features.csv(OHLC+atr_ratio) / Merged_Data.csv(oi_zscore_24h) / 펀딩8h
# [OUTPUT] (실행폴더) streakml_summary.csv + streakml_univariate.csv + streakml_features.csv + .streakml_metric
# [함수 In->Out] load_engine/find_file / col_7h(path,col,idx) / auc_rank(y,score) / zscore / logreg_fit/predict
#                build_features() / streak_labels(trades) / main()
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
    from sklearn.cluster import KMeans
    HAVE_SK = True
except Exception:
    HAVE_SK = False


def load_engine(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


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


def col_7h(path, col, idx):
    # 임의 컬럼을 7h봉에 last로 매칭(load_oi_8h와 동일 방식, 미래참조 없음=봉닫힘값)
    try:
        df = pd.read_csv(path, usecols=['timestamp', col], index_col='timestamp', parse_dates=True)
    except Exception:
        return np.full(len(idx), np.nan)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    df = df.sort_index()
    r = df[col].resample(f"{champ.TF_MIN}min", label='left', closed='left').last()
    return r.reindex(idx).values.astype('float64')


def auc_rank(y, score):
    y = np.asarray(y); score = np.asarray(score, float)
    ok = ~np.isnan(score)
    y = y[ok]; score = score[ok]
    npos = int((y == 1).sum()); nneg = int((y == 0).sum())
    if npos == 0 or nneg == 0:
        return 0.5
    order = score.argsort(kind='mergesort')
    ranks = np.empty(len(score)); ranks[order] = np.arange(1, len(score) + 1)
    a = (ranks[y == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg)
    return float(a)


def zfit(X):
    mu = np.nanmean(X, axis=0); sd = np.nanstd(X, axis=0); sd[sd == 0] = 1.0
    return mu, sd


def logreg_fit(X, y, iters=800, lr=0.3, l2=1e-3):
    w = np.zeros(X.shape[1]); b = 0.0; m = len(y)
    for _ in range(iters):
        z = X @ w + b; p = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
        gw = X.T @ (p - y) / m + l2 * w; gb = float((p - y).mean())
        w -= lr * gw; b -= lr * gb
    return w, b


def predict(X, w, b):
    return 1.0 / (1.0 + np.exp(-np.clip(X @ w + b, -30, 30)))


def streak_labels(trades):
    R = np.array([t['R'] for t in trades]); loss = R < 0
    n = len(trades); in_streak = np.zeros(n, int); start = np.zeros(n, int); slen = np.zeros(n, int)
    i = 0
    while i < n:
        if loss[i]:
            j = i
            while j + 1 < n and loss[j + 1]:
                j += 1
            L = j - i + 1
            if L >= 2:
                in_streak[i:j + 1] = 1; start[i] = 1; slen[i:j + 1] = L
            i = j + 1
        else:
            i += 1
    return in_streak, start, slen


def main():
    print(f"[Stg4] 연속손실 ML 진단 (엔진 무수정) | sklearn={'O' if HAVE_SK else 'X(numpy폴백)'}")
    open(os.path.join(HERE, ".run_start"), "w").close()
    if DATA is None or OIPATH is None:
        pd.DataFrame([{'x': '★검증불가: 데이터/OI 없음'}]).to_csv(
            os.path.join(HERE, "streakml_summary.csv"), index=False, encoding='utf-8-sig')
        print("[abort]"); return

    df1m = champ.load_data(DATA)
    df_tf = champ.resample_tf(df1m, champ.TF_MIN)
    sig = champ.compute_signals(df_tf)
    oi_arr = champ.load_oi_8h(OIPATH, df_tf.index)
    bb_arr = champ.load_bb_8h(DATA, df_tf.index)
    atrr = col_7h(DATA, 'atr_ratio', df_tf.index)
    trades = champ.run_strategy(df_tf, sig, 0, 'none', 0.8, gate_mode='er', gate_er=0.45,
                                dz_oi=oi_arr, gate_bb=bb_arr, fib=(0.3, 0.5, 0.6), split_mode='A', split_n=3)
    print(f"[engine] 거래 {len(trades)}건")

    idx = df_tf.index; close = df_tf['close'].values; n = len(close)
    i_of = {t: k for k, t in enumerate(idx)}
    # 인과적 보조특징(과거봉만)
    logret = np.zeros(n); logret[1:] = np.diff(np.log(close))
    rv = np.array([np.std(logret[max(0, i - 9):i + 1]) for i in range(n)])
    absret = np.abs(np.concatenate([[0.0], close[1:] / close[:-1] - 1.0]))
    signflip = np.array([int(np.sum(np.diff(np.sign(logret[max(1, i - 9):i + 1])) != 0)) for i in range(n)])

    FEATS = ['er', 'adx', 'chop', 'atrcmp', 'bandw', 'drop', 'atr_ratio', 'oi_z', 'rvol', 'absret', 'signflip']
    rows = []
    for t in trades:
        i = i_of[t['entry_t']]
        rows.append(dict(entry_t=t['entry_t'].strftime('%Y-%m-%d %H:%M'), year=t['year'], side=t['side'],
                         R_pct=round(t['R'] * 100, 4),
                         er=sig['er'][i], adx=sig['adx'][i], chop=sig['chop'][i], atrcmp=sig['atrcmp'][i],
                         bandw=sig['bandw'][i], drop=sig['drop'][i], atr_ratio=atrr[i],
                         oi_z=oi_arr[i], rvol=rv[i], absret=absret[i], signflip=signflip[i]))
    df = pd.DataFrame(rows)
    ins, start, slen = streak_labels(trades)
    df['in_streak'] = ins; df['streak_start'] = start; df['streak_len'] = slen
    df.to_csv(os.path.join(HERE, "streakml_features.csv"), index=False, encoding='utf-8-sig')

    X = df[FEATS].values.astype('float64')
    X = np.where(np.isnan(X), np.nanmean(X, axis=0), X)   # 결측은 평균대체(인과 유지)

    # ── ① 단변량: 특징별 분리력 ──
    uni = []
    for k, f in enumerate(FEATS):
        col = X[:, k]; yi = df['in_streak'].values
        mi = float(col[yi == 1].mean()); mo = float(col[yi == 0].mean())
        sd = float(col.std()) or 1.0
        eff = (mi - mo) / sd
        a = auc_rank(yi, col); a = max(a, 1 - a)   # 방향무관 분리력
        uni.append(dict(feature=f, mean_in=round(mi, 4), mean_out=round(mo, 4),
                        effect_size=round(eff, 3), auc=round(a, 3)))
    uni = pd.DataFrame(uni).sort_values('auc', ascending=False)
    uni.to_csv(os.path.join(HERE, "streakml_univariate.csv"), index=False, encoding='utf-8-sig')

    # ── ② 다변량 로지스틱: 시간분할(앞70% 학습 → 뒤30% 검증) ──
    order = df['entry_t'].values.argsort()
    cut = int(len(df) * 0.7)
    tr_idx = order[:cut]; te_idx = order[cut:]
    mu, sd = zfit(X[tr_idx]); Xz = (X - mu) / sd

    def fit_eval(y):
        w, b = logreg_fit(Xz[tr_idx], y[tr_idx])
        ptr = predict(Xz[tr_idx], w, b); pte = predict(Xz[te_idx], w, b)
        return round(auc_rank(y[tr_idx], ptr), 3), round(auc_rank(y[te_idx], pte), 3)
    auc_in_tr, auc_in_te = fit_eval(df['in_streak'].values.astype(float))
    auc_st_tr, auc_st_te = fit_eval(df['streak_start'].values.astype(float))
    print(f"[다변량] in_streak 학습AUC{auc_in_tr}/검증AUC{auc_in_te} | streak_start 학습{auc_st_tr}/검증{auc_st_te}")

    # ── ③ sklearn 옵션: RF 중요도 + KMeans ──
    rf_line = "sklearn 없음(생략)"; km_line = ""
    if HAVE_SK:
        try:
            rf = RandomForestClassifier(n_estimators=200, max_depth=4, random_state=0, class_weight='balanced')
            rf.fit(Xz[tr_idx], df['in_streak'].values[tr_idx])
            imp = sorted(zip(FEATS, rf.feature_importances_), key=lambda x: -x[1])[:5]
            rf_te = round(auc_rank(df['in_streak'].values[te_idx], rf.predict_proba(Xz[te_idx])[:, 1]), 3)
            rf_line = f"RF검증AUC{rf_te} 중요특징:" + ",".join(f"{f}{round(v,2)}" for f, v in imp)
            insmask = df['in_streak'].values == 1
            if insmask.sum() >= 6:
                km = KMeans(n_clusters=3, n_init=5, random_state=0).fit(Xz[insmask])
                km_line = f" | 출혈군집3개 크기:{list(np.bincount(km.labels_))}"
        except Exception as e:
            rf_line = f"sklearn 오류:{e}"

    # ── ④ 횡보봇 성과 (in_streak 기간 vs 정상) — 횡보봇 z=1.0 직접 재실행(자기완결) ──
    sd_line = "횡보 재실행 실패(겹침 생략)"
    try:
        s1m = sdca.load_1m(DATA)
        s8 = sdca.resample_tf(s1m, sdca.TF_MIN)
        ssig = sdca.precompute(s8)
        sss, sse = sdca.build_1m_map(s1m, s8)
        mO = s1m['open'].values; mH = s1m['high'].values; mL = s1m['low'].values
        mT = s1m.index.values.astype('datetime64[ns]').astype('int64')
        ft = fr = None
        fpath = find_file(["BTCUSDT_funding_history_8h.csv", "funding_history_8h.csv",
                           "sample_BTCUSDT_funding_history_8h.csv"])
        if fpath:
            try:
                ft, fr = sdca.load_funding(fpath)
            except Exception:
                pass
        strades, _, _, _ = sdca.run_bot_honest(
            s8, ssig, sdca.BEST_PAR, mO, mH, mL, mT, sss, sse, ft, fr, sdca.DEFAULT_SLMULT,
            filter_mode='precise', atr_lo=sdca.ATR_LO, atr_hi=sdca.ATR_HI, filter_scens=sdca.FILTER_SCENS,
            oi_filter=True, oi_z_hi=1.0, oi_filter_scens=sdca.OI_FILTER_SCENS)
        s = pd.DataFrame([{'entry_t': t['entry_t'], 'R_real_pct': t['R'] * 100} for t in strades])
        if len(s) > 0:
            s['entry_t'] = pd.to_datetime(s['entry_t'])
            # in_streak 구간 = 각 출혈 run의 [첫진입, 마지막청산]
            R = np.array([t['R'] for t in trades]); loss = R < 0
            spans = []; i = 0
            while i < len(trades):
                if loss[i]:
                    j = i
                    while j + 1 < len(trades) and loss[j + 1]:
                        j += 1
                    if j - i + 1 >= 2:
                        spans.append((trades[i]['entry_t'], trades[j]['exit_t']))
                    i = j + 1
                else:
                    i += 1
            inmask = np.zeros(len(s), bool)
            for a, b in spans:
                inmask |= ((s['entry_t'] >= a) & (s['entry_t'] <= b)).values
            sd_in = round(float(s.loc[inmask, 'R_real_pct'].sum()), 2)
            sd_out = round(float(s.loc[~inmask, 'R_real_pct'].sum()), 2)
            sd_line = f"횡보봇: 추세출혈기간 {sd_in}%({int(inmask.sum())}건) / 그외 {sd_out}%({int((~inmask).sum())}건)"
    except Exception as e:
        sd_line = f"횡보겹침 오류:{e}"

    nstreak = int(df['in_streak'].sum()); nstart = int(df['streak_start'].sum())
    top3 = ", ".join(f"{r.feature}(AUC{r.auc})" for r in uni.head(3).itertuples())
    feasible = "예측가능(심판토대有)" if auc_in_te >= 0.65 else ("약함" if auc_in_te >= 0.58 else "예측불가(심판은 늦은반응만)")
    verdict = (f"VERDICT Stg4 | 거래{len(trades)} 출혈거래{nstreak} 출혈시작{nstart} | "
               f"단변량 분리력Top3: {top3} | "
               f"다변량 검증AUC: in_streak {auc_in_te}(학습{auc_in_tr}) / streak_start {auc_st_te}(학습{auc_st_tr}) -> {feasible} | "
               f"{rf_line}{km_line} | {sd_line}")
    print("[verdict] " + verdict)

    out = [dict(sec=verdict), dict(sec='─ 단변량 분리력(AUC 높은순) ─')]
    for r in uni.itertuples():
        out.append(dict(sec=f"  {r.feature}: AUC{r.auc} 효과크기{r.effect_size} (출혈{r.mean_in} vs 정상{r.mean_out})"))
    pd.DataFrame(out).to_csv(os.path.join(HERE, "streakml_summary.csv"), index=False, encoding='utf-8-sig')

    with open(os.path.join(HERE, ".streakml_metric"), "w", encoding="utf-8") as f:
        f.write(f"n_trades={len(trades)}\nn_streak={nstreak}\nn_start={nstart}\n"
                f"auc_in_te={auc_in_te}\nauc_in_tr={auc_in_tr}\nauc_st_te={auc_st_te}\nauc_st_tr={auc_st_tr}\n"
                f"top_feature={uni.iloc[0]['feature']}\ntop_auc={uni.iloc[0]['auc']}\n"
                f"have_sklearn={HAVE_SK}\nfeasible={feasible}\n")
    print("[save] streakml_summary/univariate/features.csv")


if __name__ == "__main__":
    main()
