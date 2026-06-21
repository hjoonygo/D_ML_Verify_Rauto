# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch5_RAUTO_ConceptRefine_Stg5_MetaVolDefense.py
# 코드길이: 약 360줄 | 내부버전: RAUTO_ConceptRefine_06_Ch5_Stg5_MetaVolDefense_v2(문서기준 진짜CVD) | 전체 출력
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   "회복 못 하는 출혈(약회복)만 골라 방어"가 가능한지 정직하게(시간분할 표본외) 검증. 엔진 무수정.
#   ★Basic_Trading_Environment_Setup.docx 기준으로 '추정 없이' 실제 데이터 컬럼만 사용.
#   세 무기: (A)메타라벨링 OOS  (B)변동성 타게팅  (C)진짜 CVD+거래량+문서 마이크로/장세특징.
#   ★안전장치: '잭팟 보존율' — 방어가 출혈 직후 회복거래를 몇 % 지키나(85% 미만=무효).
#
#   [라벨 y(미래=예측대상)] 손실=엔진R<0. 2+연속손실 run.
#     in_weak: run 종료 후 3거래 누적R<+2% (약회복) / in_long: run 지속>=10일.
#   [특징 X(전부 인과적·실시간 안전)] — 문서 3.2 기준, 헤더 자동감지로 '있는 것만':
#     엔진신호: er adx chop atrcmp bandw drop
#     계산: rvol absret signflip vol_z
#     ★진짜CVD(CVD_15m_BTCUSDT.csv): cvd_press(delta/vol) taker_ratio(taker_buy/vol) cvd_slope(최근10봉 순매수비)
#       delta = taker_buy - taker_sell (=2*taker_buy - volume), 누적=CVD. 15분->7h 합산.
#     문서 장세특징(Regime_Features, 4h기반 shift안전): atr_ratio adx_chg ema_fan ema20_slope bb_width_pct norm_atr
#       + feat_struct_* feat_break_* (실시간 안전 입력)
#     문서 마이크로(Merged_Data.csv): oi_zscore_24h(검증알파) taker_imbalance_5m_avg top_retail_divergence
#   [★lookahead 차단] label_smc_*(정답지)는 특징에서 하드 제외. label_ 접두 컬럼 전부 차단. 모든 특징 과거봉만.
#
# [PATH] 실행: D:\ML\verify\06Prj_..._Stg5_MetaVolDefense\ . 데이터: 상위 D:\ML\verify\ (3종+CVD_15m).
# [DATA] Merged_Data_with_Regime_Features.csv / Merged_Data.csv / CVD_15m_BTCUSDT.csv / funding_history_8h.csv
# [OUTPUT] stg5_summary.csv + metalabel_oos.csv + voltarget_sweep.csv + defense_trades.csv + .stg5_metric
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

COST_RT = 0.0014; WEAK_THR = 2.0; LONG_DAYS = 10.0
# 문서 3.2.1 연속 장세특징(실시간 안전). label_smc_*는 절대 제외(정답지=lookahead).
DOC_REGIME = ['atr_ratio', 'adx_chg', 'ema_fan', 'ema20_slope', 'bb_width_pct', 'norm_atr']
DOC_MICRO = ['oi_zscore_24h', 'taker_imbalance_5m_avg', 'top_retail_divergence', 'oi_change_1h_pct']


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
CVDPATH = find_file(["CVD_15m_BTCUSDT.csv", "sample_CVD_15m_BTCUSDT.csv"])
TF = champ.TF_MIN


def _strip_tz(df):
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    return df.sort_index()


def load_main_feats(path, idx):
    # 헤더 자동감지: 문서 장세특징 + feat_*(실시간안전). label_*는 제외(lookahead).
    head = list(pd.read_csv(path, nrows=1).columns)
    feat_cols = [c for c in head if c.startswith('feat_struct') or c.startswith('feat_break')]
    reg_cols = [c for c in DOC_REGIME if c in head]
    use = ['timestamp'] + (['volume'] if 'volume' in head else []) + reg_cols + feat_cols
    df = _strip_tz(pd.read_csv(path, usecols=use, index_col='timestamp', parse_dates=True))
    out = {}
    if 'volume' in df:
        vol = df['volume'].resample(f"{TF}min", label='left', closed='left').sum().reindex(idx).values.astype('float64')
        out['__volume__'] = vol
    for c in reg_cols + feat_cols:
        col = df[c]
        if col.dtype == object:   # feat_struct 같은 범주형은 숫자화
            col = pd.to_numeric(col, errors='coerce')
        out[c] = col.resample(f"{TF}min", label='left', closed='left').last().reindex(idx).values.astype('float64')
    return out, reg_cols + feat_cols


def load_cvd(path, idx):
    if path is None:
        return {}, "CVD파일없음"
    head = list(pd.read_csv(path, nrows=1).columns)
    if 'taker_buy' not in head or 'volume' not in head:
        return {}, f"CVD컬럼부족({head})"
    use = ['timestamp', 'volume', 'taker_buy'] + (['delta'] if 'delta' in head else [])
    df = _strip_tz(pd.read_csv(path, usecols=use, index_col='timestamp', parse_dates=True))
    r = df.resample(f"{TF}min", label='left', closed='left').sum().reindex(idx)
    vol = r['volume'].values.astype('float64'); tb = r['taker_buy'].values.astype('float64')
    delta = r['delta'].values.astype('float64') if 'delta' in df else (2 * tb - vol)
    n = len(idx)
    cvd_press = np.divide(delta, vol, out=np.zeros(n), where=vol > 0)
    taker_ratio = np.divide(tb, vol, out=np.full(n, 0.5), where=vol > 0)
    cvd_slope = np.zeros(n)
    for i in range(n):
        ds = np.nansum(delta[max(0, i - 9):i + 1]); vs = np.nansum(vol[max(0, i - 9):i + 1])
        cvd_slope[i] = ds / vs if vs > 0 else 0.0
    return {'cvd_press': cvd_press, 'taker_ratio': taker_ratio, 'cvd_slope': cvd_slope}, "진짜CVD(taker_buy/delta 15m→7h)"


def load_micro(path, idx):
    head = list(pd.read_csv(path, nrows=1).columns)
    cols = [c for c in DOC_MICRO if c in head and c != 'oi_zscore_24h']  # oi_z는 엔진로더로 별도
    if not cols:
        return {}, []
    df = _strip_tz(pd.read_csv(path, usecols=['timestamp'] + cols, index_col='timestamp', parse_dates=True))
    out = {c: df[c].resample(f"{TF}min", label='left', closed='left').last().reindex(idx).values.astype('float64') for c in cols}
    return out, cols


def auc_rank(y, s):
    y = np.asarray(y); s = np.asarray(s, float); ok = ~np.isnan(s); y = y[ok]; s = s[ok]
    p = int((y == 1).sum()); q = int((y == 0).sum())
    if p == 0 or q == 0:
        return 0.5
    o = s.argsort(kind='mergesort'); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1)
    return float((r[y == 1].sum() - p * (p + 1) / 2) / (p * q))


def logreg_fit(X, y, it=800, lr=0.3, l2=1e-3):
    w = np.zeros(X.shape[1]); b = 0.0; m = len(y)
    for _ in range(it):
        p = 1 / (1 + np.exp(-np.clip(X @ w + b, -30, 30)))
        w -= lr * (X.T @ (p - y) / m + l2 * w); b -= lr * float((p - y).mean())
    return w, b


def predict(X, w, b):
    return 1 / (1 + np.exp(-np.clip(X @ w + b, -30, 30)))


def streak_targets(trades):
    R = np.array([t['R'] for t in trades]); loss = R < 0; n = len(trades)
    iw = np.zeros(n, int); il = np.zeros(n, int); rec = []
    i = 0
    while i < n:
        if loss[i]:
            j = i
            while j + 1 < n and loss[j + 1]:
                j += 1
            if j - i + 1 >= 2:
                r3 = float(R[j + 1:j + 4].sum()) * 100 if j + 1 < n else 0.0
                dd = (trades[j]['exit_t'] - trades[i]['entry_t']).total_seconds() / 86400
                if r3 < WEAK_THR:
                    iw[i:j + 1] = 1
                if dd >= LONG_DAYS:
                    il[i:j + 1] = 1
                if j + 1 < n:
                    rec.append(j + 1)
            i = j + 1
        else:
            i += 1
    return iw, il, np.array(rec, int)


def sim(R, size):
    cap = 1.0; peak = 1.0; mdd = 0.0
    for r, s in zip(R, size):
        cap *= (1 + r * s); peak = max(peak, cap); mdd = min(mdd, (cap - peak) / peak)
    return round((cap - 1) * 100, 1), round(mdd * 100, 1)


def main():
    print(f"[Stg5 v2] 문서기준 진짜CVD+문서특징 방어진단 | sklearn={'O' if HAVE_SK else 'X'}")
    open(os.path.join(HERE, ".run_start"), "w").close()
    if DATA is None or OIPATH is None:
        pd.DataFrame([{'x': '★검증불가: 데이터 없음'}]).to_csv(os.path.join(HERE, "stg5_summary.csv"), index=False, encoding='utf-8-sig')
        print("[abort]"); return
    print(f"[files] main={os.path.basename(DATA)} oi={os.path.basename(OIPATH)} cvd={os.path.basename(CVDPATH) if CVDPATH else '없음'}")

    df1m = champ.load_data(DATA); df_tf = champ.resample_tf(df1m, TF); sig = champ.compute_signals(df_tf)
    idx = df_tf.index; close = df_tf['close'].values; n_bar = len(close); i_of = {t: k for k, t in enumerate(idx)}
    oi_arr = champ.load_oi_8h(OIPATH, idx); bb_arr = champ.load_bb_8h(DATA, idx)

    main_feats, main_names = load_main_feats(DATA, idx)
    cvd_feats, cvd_mode = load_cvd(CVDPATH, idx)
    micro_feats, micro_names = load_micro(OIPATH, idx)
    print(f"[CVD] {cvd_mode} | 문서장세특징 {main_names} | 마이크로 {micro_names}")

    vol = main_feats.get('__volume__', np.ones(n_bar))
    vol_z = np.zeros(n_bar)
    for i in range(n_bar):
        w = vol[max(0, i - 19):i + 1]; mu = np.nanmean(w); sd = np.nanstd(w)
        vol_z[i] = (vol[i] - mu) / sd if sd > 0 else 0.0
    logret = np.zeros(n_bar); logret[1:] = np.diff(np.log(close))
    rv = np.array([np.std(logret[max(0, k - 9):k + 1]) for k in range(n_bar)])
    absret = np.abs(np.concatenate([[0.0], close[1:] / close[:-1] - 1.0]))
    signflip = np.array([int(np.sum(np.diff(np.sign(logret[max(1, k - 9):k + 1])) != 0)) for k in range(n_bar)])

    # 전체 특징맵(7h) — label_* 절대 미포함
    fmap = {'er': sig['er'], 'adx': sig['adx'], 'chop': sig['chop'], 'atrcmp': sig['atrcmp'],
            'bandw': sig['bandw'], 'drop': sig['drop'], 'rvol': rv, 'absret': absret, 'signflip': signflip,
            'vol_z': vol_z, 'oi_zscore_24h': oi_arr}
    fmap.update(cvd_feats); fmap.update(micro_feats)
    for k in main_names:
        fmap[k] = main_feats[k]
    fmap = {k: v for k, v in fmap.items() if 'label' not in k.lower()}   # ★lookahead 하드차단
    FEATS = list(fmap.keys())

    ft = fr = None; fnote = "FALLBACK"
    fpath = find_file(["BTCUSDT_funding_history_8h.csv", "funding_history_8h.csv", "sample_BTCUSDT_funding_history_8h.csv"])
    if fpath:
        try:
            ft, fr = sdca.load_funding(fpath); fnote = f"REAL({sdca.load_funding.n_loaded})"
        except Exception:
            pass

    trades = champ.run_strategy(df_tf, sig, 0, 'none', 0.8, gate_mode='er', gate_er=0.45,
                                dz_oi=oi_arr, gate_bb=bb_arr, fib=(0.3, 0.5, 0.6), split_mode='A', split_n=3)
    n = len(trades); print(f"[engine] 거래 {n}건 | 특징 {len(FEATS)}개: {FEATS}")

    def realR(t):
        g = t['side'] * (t['exit'] - t['entry']) / t['entry']; fp = 0.0
        if ft is not None:
            fs = sdca.funding_sum(ft, fr, int(pd.Timestamp(t['entry_t']).value), int(pd.Timestamp(t['exit_t']).value))
            fp = t['side'] * fs if fs is not None else 0.0
        return g - COST_RT - fp
    R = np.array([realR(t) for t in trades])

    X = np.array([[fmap[f][i_of[t['entry_t']]] for f in FEATS] for t in trades], float)
    X = np.where(np.isnan(X), np.nanmean(X, axis=0), X)
    X = np.where(np.isnan(X), 0.0, X)
    iw, il, rec = streak_targets(trades)
    order = np.argsort([pd.Timestamp(t['entry_t']).value for t in trades]); cut = int(n * 0.7)
    tr = order[:cut]; te = order[cut:]
    mu = X[tr].mean(0); sd = X[tr].std(0); sd[sd == 0] = 1; Xz = (X - mu) / sd

    uni = []
    for k, f in enumerate(FEATS):
        a = auc_rank(iw, X[:, k]); a = round(max(a, 1 - a), 3)
        uni.append(dict(feature=f, auc_weak=a, mean_weak=round(float(X[iw == 1, k].mean()), 4),
                        mean_other=round(float(X[iw == 0, k].mean()), 4)))
    uni = pd.DataFrame(uni).sort_values('auc_weak', ascending=False)
    uni.to_csv(os.path.join(HERE, "metalabel_oos.csv"), index=False, encoding='utf-8-sig')

    def fit_eval(y):
        w, b = logreg_fit(Xz[tr], y[tr].astype(float))
        lr_te = round(auc_rank(y[te], predict(Xz[te], w, b)), 3); lr_tr = round(auc_rank(y[tr], predict(Xz[tr], w, b)), 3)
        rf_te = None; p_full = predict(Xz, w, b)
        if HAVE_SK and y[tr].sum() >= 5:
            try:
                rf = RandomForestClassifier(n_estimators=200, max_depth=4, random_state=0, class_weight='balanced')
                rf.fit(Xz[tr], y[tr]); rf_te = round(auc_rank(y[te], rf.predict_proba(Xz[te])[:, 1]), 3)
            except Exception:
                pass
        return lr_tr, lr_te, rf_te, p_full
    w_tr, w_te, w_rf, p_weak = fit_eval(iw)
    l_tr, l_te, l_rf, _ = fit_eval(il)
    print(f"[메타] weak 학습{w_tr}/검증{w_te}(RF{w_rf}) | long 학습{l_tr}/검증{l_te}(RF{l_rf})")

    base = np.ones(n); thr = np.quantile(p_weak[tr], 0.70); defn = base.copy(); defn[p_weak > thr] = 0.5
    cumR_b, mdd_b = sim(R, base); cumR_d, mdd_d = sim(R, defn)
    jack_meta = round(100 * defn[rec].mean(), 1) if len(rec) else 100.0

    rv_t = np.array([rv[i_of[t['entry_t']]] for t in trades]); rv_t[rv_t <= 0] = np.nanmedian(rv_t)
    sweep = []
    for q in [0.4, 0.5, 0.6, 0.7]:
        tgt = np.nanquantile(rv_t, q); size = np.clip(tgt / rv_t, 0.3, 2.0)
        cr, md = sim(R, size); jk = round(100 * size[rec].mean(), 1) if len(rec) else 100.0
        sweep.append(dict(target_q=q, cumR=cr, MDD=md, jackpot_keep=jk, avg_size=round(float(size.mean()), 2)))
    sw = pd.DataFrame(sweep); sw.to_csv(os.path.join(HERE, "voltarget_sweep.csv"), index=False, encoding='utf-8-sig')
    best = sw.iloc[(sw.cumR / sw.MDD.abs()).values.argmax()]

    pd.DataFrame([dict(entry_t=t['entry_t'].strftime('%Y-%m-%d'), R_pct=round(R[k] * 100, 3),
                       in_weak=int(iw[k]), in_long=int(il[k]), p_weak=round(float(p_weak[k]), 3),
                       meta_size=round(float(defn[k]), 2)) for k, t in enumerate(trades)]).to_csv(
        os.path.join(HERE, "defense_trades.csv"), index=False, encoding='utf-8-sig')

    nw = int(iw.sum()); nl = int(il.sum()); nj = len(rec)
    top3 = ", ".join(f"{r.feature}({r.auc_weak})" for r in uni.head(3).itertuples())
    meta_ok = (w_te >= 0.58) and (jack_meta >= 85)
    vt_ok = (best['MDD'] > mdd_b) and (best['cumR'] >= cumR_b * 0.8) and (best['jackpot_keep'] >= 85)
    flag = "방어유효(채택검토)" if (meta_ok or vt_ok) else "방어무효(④보수노출 확정→페이퍼)"
    verdict = (f"VERDICT Stg5v2 | 펀딩={fnote} | CVD={cvd_mode} | 특징{len(FEATS)}개 | 거래{n} 약회복{nw} 장기{nl} 잭팟{nj} | "
               f"단변량Top3(약회복):{top3} | 메타 weak검증AUC {w_te}(RF{w_rf})/long {l_te}(RF{l_rf}) | "
               f"메타방어: 기본{cumR_b}%/MDD{mdd_b}->방어{cumR_d}%/MDD{mdd_d}, 잭팟보존{jack_meta}% | "
               f"볼타게팅best(q{best['target_q']}): {best['cumR']}%/MDD{best['MDD']}, 잭팟보존{best['jackpot_keep']}% | => {flag}")
    print("[verdict] " + verdict)

    out = [dict(sec=verdict), dict(sec=f'─ 사용 특징 {len(FEATS)}개(label_smc 제외): {", ".join(FEATS)} ─'),
           dict(sec='─ 단변량 분리력(약회복 출혈, AUC 높은순) ─')]
    for r in uni.itertuples():
        out.append(dict(sec=f"  {r.feature}: AUC {r.auc_weak} (약회복 {r.mean_weak} vs 그외 {r.mean_other})"))
    out.append(dict(sec='─ 변동성 타게팅 스윕 ─'))
    for r in sw.itertuples():
        out.append(dict(sec=f"  q{r.target_q}: cumR{r.cumR}% MDD{r.MDD}% 잭팟보존{r.jackpot_keep}% 평균노출{r.avg_size}"))
    pd.DataFrame(out).to_csv(os.path.join(HERE, "stg5_summary.csv"), index=False, encoding='utf-8-sig')

    with open(os.path.join(HERE, ".stg5_metric"), "w", encoding="utf-8") as f:
        f.write(f"n_trades={n}\nn_weak={nw}\nn_long={nl}\nn_jack={nj}\ncvd_mode={cvd_mode}\nn_feats={len(FEATS)}\n"
                f"feats={'|'.join(FEATS)}\nhas_label_in_feats={'label' in '|'.join(FEATS).lower()}\n"
                f"weak_te={w_te}\nweak_tr={w_tr}\nweak_rf={w_rf}\nlong_te={l_te}\nlong_rf={l_rf}\n"
                f"base_cum={cumR_b}\nbase_mdd={mdd_b}\ndef_cum={cumR_d}\ndef_mdd={mdd_d}\njack_meta={jack_meta}\n"
                f"vt_cum={best['cumR']}\nvt_mdd={best['MDD']}\nvt_jack={best['jackpot_keep']}\n"
                f"top_feature={uni.iloc[0]['feature']}\nhave_sklearn={HAVE_SK}\nverdict_flag={flag}\n")
    print("[save] stg5_summary/metalabel_oos/voltarget_sweep/defense_trades.csv")


if __name__ == "__main__":
    main()
