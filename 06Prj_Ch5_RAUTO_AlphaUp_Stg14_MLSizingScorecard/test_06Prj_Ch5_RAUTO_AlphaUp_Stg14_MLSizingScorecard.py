# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch5_RAUTO_AlphaUp_Stg14_MLSizingScorecard.py
# 코드길이: 약 430줄 | 내부버전: RAUTO_AlphaUp_06_Ch5_Stg14_MLSizingScorecard | 로직 전체 출력
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   엔진 무수정. Stg13에서 입증된 ML 장세분류(GradBoost 63.2%)를 재현해 추세봇 진입마다 장세를 예측하고,
#   '추세장이면 키우고 횡보면 줄이는' 사이징을 장세별/연도별/롱숏별 5지표로 분해한다.
#   ★2025 집중: ML이 2025를 어떤 장세로 봤는지 + 사이징 후 2025 손익이 base보다 나아지는지 따로 본다.
#   ★배수 그리드: 추세장배수{1.3,1.5,1.7} × 횡보배수{0.5,0.6,0.7} = 9조합.
#     최적선택 규칙(ML): (1)복리MDD <= -35% 위반 제외 (2)2025 비적자 우선 (3)그중 OOS수익 최고.
#   [특징 35개(Stg13과 동일, Hurst·다TF 포함)] label_smc 타깃전용(특징 제외, check 검증).
#   [모델] GradBoost(Stg13 best). 학습기간(앞70%)만 fit → 전 구간 예측(검증은 OOS만).
#   [Lookahead 차단] 특징 과거봉, 스케일러·모델 학습기간만 fit, label 미포함.
#
# [PATH] 실행: D:\ML\Verify\06Prj_..._Stg14_MLSizingScorecard\ . 데이터: 상위 (4종).
# [OUTPUT] grid_with_risk.csv / best_by_regime.csv / best_by_year.csv / best_by_side.csv
#          / y2025_focus.csv / all_trades.csv / summary.csv + .stg14_metric
# ==============================================================================
import os, sys, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE); BOTS = os.path.join(HERE, "bots")
COST_RT = 0.0014
TREND_GRID = [1.3, 1.5, 1.7]
RANGE_GRID = [0.5, 0.6, 0.7]
MDD_LIMIT = -35.0
REGIME_MAP = {'uptrend': 0, 'downtrend': 1, 'volatile_range': 2, 'dead_range': 3}
REGIME_NAME = {0: 'uptrend', 1: 'downtrend', 2: 'volatile_range', 3: 'dead_range', -1: 'unknown'}
DOC_REGIME = ['atr_ratio', 'adx_chg', 'ema_fan', 'ema20_slope', 'bb_width_pct', 'norm_atr']
DOC_MICRO = ['taker_imbalance_5m_avg', 'top_retail_divergence', 'oi_change_1h_pct']
TREND_REGS = {'uptrend', 'downtrend'}
try:
    from sklearn.ensemble import GradientBoostingClassifier
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
    x = np.asarray(x, float); n = len(x)
    if n < 16 or np.any(~np.isfinite(x)):
        return np.nan
    r = np.diff(np.log(x))
    if len(r) < 8 or np.std(r) == 0:
        return np.nan
    dev = np.cumsum(r - r.mean()); R = dev.max() - dev.min(); S = r.std()
    return np.log(R / S) / np.log(len(r)) if (S > 0 and R > 0) else np.nan


def metrics(R):
    R = np.asarray(R, float); n = len(R)
    if n == 0:
        return dict(n=0, PF=0.0, ret_pct=0.0, payoff=0.0, win_pct=0.0)
    win = R[R > 0]; los = R[R < 0]; gp = float(win.sum()); gl = float(-los.sum())
    pf = round(gp / gl, 3) if gl > 0 else (999.0 if gp > 0 else 0.0)
    payoff = round(win.mean() / -los.mean(), 3) if len(win) and len(los) else 0.0
    return dict(n=n, PF=pf, ret_pct=round(R.sum() * 100, 2), payoff=payoff, win_pct=round(100 * len(win) / n, 1))


def sim_comp(R, size):
    cap = START_CAP; peak = START_CAP; mdd = 0.0; liq = False
    for r, s in zip(R, size):
        cap *= (1 + r * s); peak = max(peak, cap)
        if peak > 0:
            mdd = min(mdd, (cap - peak) / peak)
        if cap <= MIN_CAP:
            liq = True; break
    return round(cap - START_CAP, 0), round(mdd * 100, 1), liq


def resample_last(s, tf, idx):
    return s.resample(f"{tf}min", label='left', closed='left').last().reindex(idx).values.astype('float64')


def main():
    print(f"[Stg14] ML 장세사이징 세축분해 + 2025집중 + 배수최적화 | sklearn={'O' if HAVE_SK else 'X'}")
    open(os.path.join(HERE, ".run_start"), "w").close()
    if DATA is None or not HAVE_SK:
        pd.DataFrame([{'x': 'no data/sklearn'}]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig'); return

    head = list(pd.read_csv(DATA, nrows=1).columns)
    lbl = next((c for c in head if c.startswith('label_smc_8')), None) or next((c for c in head if c.startswith('label_smc')), None)
    feat_cols = [c for c in head if c.startswith('feat_struct') or c.startswith('feat_break')]
    reg_cols = [c for c in DOC_REGIME if c in head]

    df1m = champ.load_data(DATA); df7 = champ.resample_tf(df1m, TF7); sig = champ.compute_signals(df7)
    idx = df7.index; close = df7['close'].values; n_bar = len(idx); i_of = {t: k for k, t in enumerate(idx)}
    oi = champ.load_oi_8h(OIPATH, idx); bb7 = champ.load_bb_8h(DATA, idx)
    raw = pd.read_csv(DATA, usecols=['timestamp', lbl] + (['volume'] if 'volume' in head else []) + reg_cols + feat_cols,
                      index_col='timestamp', parse_dates=True)
    if getattr(raw.index, 'tz', None) is not None:
        raw.index = raw.index.tz_localize(None)
    raw = raw.sort_index()
    regime = raw[lbl].resample(f"{TF7}min", label='left', closed='left').last().reindex(idx).map(REGIME_MAP).values.astype('float64')

    # 특징 구성(Stg13 동일)
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
    oih = list(pd.read_csv(OIPATH, nrows=1).columns)
    for c in [x for x in DOC_MICRO if x in oih]:
        md = pd.read_csv(OIPATH, usecols=['timestamp', c], index_col='timestamp', parse_dates=True)
        if getattr(md.index, 'tz', None) is not None:
            md.index = md.index.tz_localize(None)
        fmap[c] = resample_last(md.sort_index()[c], TF7, idx)
    if CVDPATH:
        ch = list(pd.read_csv(CVDPATH, nrows=1).columns)
        if 'taker_buy' in ch and 'volume' in ch:
            cd = pd.read_csv(CVDPATH, usecols=['timestamp', 'volume', 'taker_buy']+(['delta'] if 'delta' in ch else []),
                             index_col='timestamp', parse_dates=True)
            if getattr(cd.index, 'tz', None) is not None:
                cd.index = cd.index.tz_localize(None)
            rr = cd.sort_index().resample(f"{TF7}min", label='left', closed='left').sum().reindex(idx)
            v = rr['volume'].values.astype('float64'); tb = rr['taker_buy'].values.astype('float64')
            dl = rr['delta'].values.astype('float64') if 'delta' in cd else (2*tb-v)
            fmap['cvd_press'] = np.divide(dl, v, out=np.zeros(n_bar), where=v > 0)
            fmap['taker_ratio'] = np.divide(tb, v, out=np.full(n_bar, .5), where=v > 0)
    logret = np.concatenate([[0.0], np.diff(np.log(close))])
    rv10 = np.array([np.std(logret[max(0, i-9):i+1]) for i in range(n_bar)])
    fmap['rv10'] = rv10
    fmap['rv_pctile'] = np.array([(rv10[i] >= rv10[max(0, i-49):i+1]).mean() for i in range(n_bar)])
    fmap['hurst'] = np.array([hurst_rs(close[i-64:i+1]) if i >= 64 else np.nan for i in range(n_bar)])
    na = fmap.get('norm_atr', fmap.get('atr_ratio', np.zeros(n_bar)))
    fmap['natr_slope'] = np.array([na[i]-na[max(0, i-6)] for i in range(n_bar)])
    for tf, suf in [(15, '_tf15'), (60, '_tf60'), (240, '_tf240')]:
        ctf = df1m['close'].resample(f"{tf}min", label='left', closed='left').last().dropna()
        cv = ctf.values; lr = np.concatenate([[0.0], np.diff(np.log(cv))])
        rvt = pd.Series([np.std(lr[max(0, j-9):j+1]) for j in range(len(cv))], index=ctf.index)
        hu = pd.Series([hurst_rs(cv[j-64:j+1]) if j >= 64 else np.nan for j in range(len(cv))], index=ctf.index)
        fmap['rv'+suf] = rvt.resample(f"{TF7}min", label='left', closed='left').last().reindex(idx).values.astype('float64')
        fmap['hurst'+suf] = hu.resample(f"{TF7}min", label='left', closed='left').last().reindex(idx).values.astype('float64')
    fmap = {k: v for k, v in fmap.items() if 'label' not in k.lower()}
    FEATS = list(fmap.keys())
    X = np.column_stack([fmap[f] for f in FEATS]).astype('float64')
    X = np.where(np.isnan(X), np.nanmean(X, axis=0), X); X = np.where(np.isnan(X), 0.0, X)
    valid = ~np.isnan(regime); order = np.argsort(idx.values); cut = int(n_bar*0.7)
    tr = np.array([b for b in order[:cut] if valid[b]]); yreg = regime.astype(int)
    mdl = GradientBoostingClassifier(n_estimators=200, max_depth=3, random_state=0)
    mdl.fit(X[tr], yreg[tr])
    pred_all = mdl.predict(X)
    te_mask_bar = np.arange(n_bar) >= cut
    acc_oos = round(100*float((pred_all[(np.arange(n_bar) >= cut) & valid] == yreg[(np.arange(n_bar) >= cut) & valid]).mean()), 1)

    # 거래
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
    ttr = champ.run_strategy(df7, sig, 0, 'none', 0.8, gate_mode='er', gate_er=0.45,
                             dz_oi=oi, gate_bb=bb7, fib=(0.3, 0.5, 0.6), split_mode='A', split_n=3)
    recs = []
    for t in ttr:
        R = t['side']*(t['exit']-t['entry'])/t['entry'] - COST_RT - fund_pay(t['side'], t['entry_t'], t['exit_t'])
        pos = i_of.get(t['entry_t'], None)
        if pos is None:
            pos = max(0, idx.searchsorted(pd.Timestamp(t['entry_t']))-1)
        pr = pred_all[pos] if 0 <= pos < len(pred_all) else -1
        recs.append(dict(side='롱' if t['side'] > 0 else '숏', year=pd.Timestamp(t['entry_t']).year,
                         pred_reg=REGIME_NAME[int(pr)] if pr >= 0 else 'unknown',
                         true_reg=REGIME_NAME[int(regime[pos])] if (0 <= pos < n_bar and not np.isnan(regime[pos])) else 'unknown',
                         R=float(R), is_test=pos >= cut))
    df = pd.DataFrame(recs)

    # 배수 그리드 9조합
    def size_arr(tg, rg):
        return np.where(df.pred_reg.isin(TREND_REGS), tg, rg)
    grid = []
    for tg in TREND_GRID:
        for rg in RANGE_GRID:
            s = size_arr(tg, rg); Rs = df.R.values * s
            m_all = metrics(Rs); m_oos = metrics(Rs[df.is_test.values])
            prof, mdd, liq = sim_comp(df.R.values, s)
            # 2025 손익
            y25 = df.year == 2025
            r25 = round(float((df.R.values[y25] * s[y25]).sum()*100), 2) if y25.any() else 0.0
            grid.append(dict(trend_x=tg, range_x=rg, PF_all=m_all['PF'], ret_all=m_all['ret_pct'],
                             ret_oos=m_oos['ret_pct'], PF_oos=m_oos['PF'], MDD=mdd, liq=('YES' if liq else 'NO'),
                             y2025_ret=r25, profit=prof))
    gdf = pd.DataFrame(grid); gdf.to_csv(os.path.join(HERE, "grid_with_risk.csv"), index=False, encoding='utf-8-sig')
    # 최적: MDD>=-35 & 청산X & 2025>=0 우선, 그중 OOS수익 최고
    ok = gdf[(gdf.MDD >= MDD_LIMIT) & (gdf.liq == 'NO')]
    ok_pos = ok[ok.y2025_ret >= 0]
    pick = (ok_pos if len(ok_pos) else ok if len(ok) else gdf).sort_values('ret_oos', ascending=False).iloc[0]
    best_tg, best_rg = pick['trend_x'], pick['range_x']
    s_best = size_arr(best_tg, best_rg); df['R_ml'] = df.R.values * s_best
    df.to_csv(os.path.join(HERE, "all_trades.csv"), index=False, encoding='utf-8-sig')

    def agg(key, order):
        out = []
        for k in order:
            g = df[df[key] == k]
            if len(g) == 0:
                continue
            mb = metrics(g.R.values); mm = metrics(g.R_ml.values)
            out.append(dict(**{key: k}, n=mb['n'], PF_base=mb['PF'], PF_ml=mm['PF'],
                            ret_base=mb['ret_pct'], ret_ml=mm['ret_pct'], payoff_base=mb['payoff'], payoff_ml=mm['payoff'],
                            win_pct=mb['win_pct'], profit_base=round(float(g.R.sum()*NOMINAL)), profit_ml=round(float(g.R_ml.sum()*NOMINAL))))
        return pd.DataFrame(out)
    agg('true_reg', ['uptrend', 'downtrend', 'volatile_range', 'dead_range']).to_csv(os.path.join(HERE, "best_by_regime.csv"), index=False, encoding='utf-8-sig')
    by_year = agg('year', sorted(df.year.unique())); by_year.to_csv(os.path.join(HERE, "best_by_year.csv"), index=False, encoding='utf-8-sig')
    agg('side', ['롱', '숏']).to_csv(os.path.join(HERE, "best_by_side.csv"), index=False, encoding='utf-8-sig')

    # 2025 집중: ML이 2025를 어떤 장세로 봤나 + 손익
    y25 = df[df.year == 2025]
    pred_dist = dict(y25.pred_reg.value_counts()) if len(y25) else {}
    y25_focus = [dict(metric='2025 거래수', value=len(y25)),
                 dict(metric='2025 base 수익률%', value=round(float(y25.R.sum()*100), 2) if len(y25) else 0),
                 dict(metric='2025 ML 수익률%', value=round(float(y25.R_ml.sum()*100), 2) if len(y25) else 0),
                 dict(metric='2025 base 수익금$', value=round(float(y25.R.sum()*NOMINAL)) if len(y25) else 0),
                 dict(metric='2025 ML 수익금$', value=round(float(y25.R_ml.sum()*NOMINAL)) if len(y25) else 0)]
    for k, v in pred_dist.items():
        y25_focus.append(dict(metric=f'2025 ML예측_{k}', value=int(v)))
    pd.DataFrame(y25_focus).to_csv(os.path.join(HERE, "y2025_focus.csv"), index=False, encoding='utf-8-sig')

    mb = metrics(df.R.values); mm = metrics(df.R_ml.values)
    prof_b, mdd_b, _ = sim_comp(df.R.values, np.ones(len(df)))
    prof_m, mdd_m, liq_m = sim_comp(df.R.values, s_best)
    y25b = round(float(y25.R.sum()*100), 2) if len(y25) else 0; y25m = round(float(y25.R_ml.sum()*100), 2) if len(y25) else 0
    verdict = (f"VERDICT Stg14 | ML장세 OOS정확도 {acc_oos}% | 최적배수 추세×{best_tg}/횡보×{best_rg} "
               f"(MDD>={MDD_LIMIT}·2025비적자 우선) | [전체] base PF{mb['PF']}/{mb['ret_pct']}%/MDD{mdd_b} -> "
               f"ML PF{mm['PF']}/{mm['ret_pct']}%/MDD{mdd_m}(청산{'Y' if liq_m else 'N'}) | "
               f"★2025: base {y25b}% -> ML {y25m}% | 2025 ML예측분포 {pred_dist}")
    print("[verdict] " + verdict)
    pd.DataFrame([dict(sec=verdict), dict(sec=f"[2025 집중] {y25_focus}")]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')
    with open(os.path.join(HERE, ".stg14_metric"), "w", encoding="utf-8") as f:
        f.write(f"acc_oos={acc_oos}\nbest_tg={best_tg}\nbest_rg={best_rg}\nbase_pf={mb['PF']}\nbase_ret={mb['ret_pct']}\n"
                f"ml_pf={mm['PF']}\nml_ret={mm['ret_pct']}\nbase_mdd={mdd_b}\nml_mdd={mdd_m}\nml_liq={'YES' if liq_m else 'NO'}\n"
                f"y2025_base={y25b}\ny2025_ml={y25m}\ny2025_pred={pred_dist}\nn_trades={len(df)}\nn_feats={len(FEATS)}\n"
                f"has_label_in_feats={'label' in '|'.join(FEATS).lower()}\ngrid_rows={len(gdf)}\nfunding={'REAL' if ft is not None else 'NONE'}\n")
    print("[save] grid_with_risk/best_by_*/y2025_focus/all_trades/summary.csv")


if __name__ == "__main__":
    main()
