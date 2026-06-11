# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch6_FrameWork_RAUTO_Stg3_RegimeClassifier.py
# 코드길이: 약 330줄 | 내부버전: 06Prj_Ch6_Stg3_RegimeClassifier_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   목적(딱 한 가지): '장세판단(4국면) 로직'을 완성한다. 표준 임계로 분류기를 돌려, 봇 실수익(PF)으로 채점하고,
#                    표준이 부족하면 ML로 최적치를 찾는다. 이 분류기는 앞으로 모든 알파가 공유할 토대.
#   엔진 무수정(해시 대조). 분류기는 독립모듈(regime_classifier.py), 실시간 안전지표만 사용.
#   정답지 label_smc_8 = 채점(혼동행렬)에만 사용, 분류기 입력 금지(미래참조 차단).
#
#   [8개 검증 시나리오 — 사장님 확정]
#     S1 표준분류기 vs 정답지 일치율·혼동행렬   S2 국면별 봇 PF(추세봇=추세국면, 횡보봇=레인지국면서 PF최대인가)
#     S3 방향가중치 w 5단계(0/.25/.5/.75/1)      S4 임계 민감도 CHOP(60/61.8/65)·ADX(20/25/30)
#     S5 암호화폐 ADX 상향(30) 효과              S6 다수결 N(2/4 vs 3/4)
#     S7 국면 전이 안정성(휩쏘=연간 전환횟수)     S8 워크포워드 + 표준부족시 ML 최적치 탐색
#   → S3·S4·S5·S6은 90개 격자(w5×CHOP3×ADX3×vote2)로 한 번에 측정. S1·S2·S7은 격자 각 행에 기록. S8 별도.
#
#   [채점 기준 = L(봇 실수익)] 분류기가 좋다 = 추세봇이 분류기-추세국면(상승/하락)서 PF 높고, 횡보봇이
#     분류기-레인지국면(변동/죽은)서 PF 높다. L점수=추세봇_추세국면PF + 횡보봇_레인지국면PF. 분리도=그 차이.
#
# [PATH] 실행 D:\ML\verify\06Prj_Ch6_FrameWork_RAUTO_Stg3_RegimeClassifier\ . 데이터 상위 D:\ML\verify.
# [OUTPUT] grid_scores.csv / confusion.csv / regime_bot_pf.csv / walkforward.csv / ml_compare.csv / summary.csv + .stg3_metric
# [In/Out 태그]
#   regime_classifier: compute_indicators(In OHLC,P / Out 지표dict) / classify(In OHLC,P / Out regime,dir,votes) / feature_matrix
#   엔진(무수정): champ.load_data/resample_tf/compute_signals/run_strategy/load_oi_8h/load_bb_8h/NOMINAL/START_CAP/TF_MIN
#                 sdca.load_1m/resample_tf/precompute/build_1m_map/run_bot_honest(precise)/load_funding/funding_sum/BEST_PAR/DEFAULT_SLMULT/TF_MIN
#   본코드: metrics(R)->PF / get_trades(추세·횡보 거래+엔진R재계산,비용0.14%+실펀딩) / resample_label_7h(정답지→7h최빈)
#           / score_config(격자 1행 채점) / walk_forward(best동결 OOS) / ml_fallback(GradBoost OOS acc)
#   변수(동결): W_GRID=[0,.25,.5,.75,1] CHOP_GRID=[60,61.8,65] ADX_GRID=[20,25,30] VOTE_GRID=[2,3]
#               TREND_REG={0,1} RANGE_REG={2,3} COST_RT=0.0014 TRAIN_MIN=18 TEST_M=3 STEP_M=3
# ==============================================================================
import os, sys, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE); BOTS = os.path.join(HERE, "bots")
sys.path.insert(0, HERE)
import regime_classifier as RC

W_GRID = [0.0, 0.25, 0.5, 0.75, 1.0]
CHOP_GRID = [60.0, 61.8, 65.0]
ADX_GRID = [20.0, 25.0, 30.0]
VOTE_GRID = [2, 3]
TREND_REG = {0, 1}; RANGE_REG = {2, 3}
COST_RT = 0.0014
TRAIN_MIN, TEST_M, STEP_M = 18, 3, 3
REGIME_MAP = {0: 'uptrend', 1: 'downtrend', 2: 'volatile_range', 3: 'dead_range'}
NAME2INT = {'uptrend': 0, 'downtrend': 1, 'volatile_range': 2, 'dead_range': 3}


def load_engine(p, nm):
    s = importlib.util.spec_from_file_location(nm, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def ns_i64(dtindex):
    # DatetimeIndex/배열을 '나노초 int64'로 강제 통일(us 해상도 버그 방지). pd.Timestamp(x).value(ns)와 매칭.
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
        return dict(n=0, PF=0.0, ret=0.0, win=0.0)
    gp = float(R[R > 0].sum()); gl = float(-R[R < 0].sum())
    pf = round(gp / gl, 3) if gl > 0 else (999.0 if gp > 0 else 0.0)
    return dict(n=n, PF=pf, ret=round(R.sum() * 100, 2), win=round(100 * (R > 0).mean(), 1))


def resample_label_7h(DATA, idx7):
    head = list(pd.read_csv(DATA, nrows=1).columns)
    lbl = next((c for c in head if c.startswith('label_smc_8')), None) or next((c for c in head if c.startswith('label_smc')), None)
    if lbl is None:
        return None
    s = pd.read_csv(DATA, usecols=['timestamp', lbl], index_col='timestamp', parse_dates=True)[lbl]
    if getattr(s.index, 'tz', None) is not None:
        s.index = s.index.tz_localize(None)
    # 문자열이면 정수코드로
    if s.dtype == object:
        s = s.map(NAME2INT)
    # 7h봉별 최빈값(mode)
    def _mode(x):
        x = x.dropna()
        return x.value_counts().index[0] if len(x) else np.nan
    g = s.resample(f"{idx7.freqstr if hasattr(idx7,'freqstr') else '420min'}", label='left', closed='left').apply(_mode) if False else None
    # idx7에 직접 매핑(각 7h봉 시작~끝 사이 최빈)
    out = np.full(len(idx7), -1, dtype=int)
    arr_t = ns_i64(s.index); arr_v = s.values
    edges = ns_i64(idx7)
    step = int(np.median(np.diff(edges))) if len(edges) > 1 else 420 * 60 * 10**9
    for i, e in enumerate(edges):
        lo = e; hi = e + step
        m = (arr_t >= lo) & (arr_t < hi)
        if m.any():
            vals, cnts = np.unique(arr_v[m][~np.isnan(arr_v[m])] if arr_v.dtype.kind == 'f' else arr_v[m], return_counts=True)
            if len(vals):
                out[i] = int(vals[cnts.argmax()])
    return out


def get_trades(champ, sdca, DATA, OIPATH, FUND):
    df1m = champ.load_data(DATA); df7 = champ.resample_tf(df1m, champ.TF_MIN); sig = champ.compute_signals(df7)
    idx7 = df7.index; oi7 = champ.load_oi_8h(OIPATH, idx7); bb7 = champ.load_bb_8h(DATA, idx7)
    o = df7['open'].values; h = df7['high'].values; l = df7['low'].values; c = df7['close'].values
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
        tT.append(dict(bot='trend', entry_t=pd.Timestamp(t['entry_t']), R=float(R)))
    # 횡보봇 정밀필터
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
        tS.append(dict(bot='sideway', entry_t=pd.Timestamp(et), R=float(t.get('R', 0.0))))
    return tT, tS, (o, h, l, c), idx7, (ft is not None)


def trade_bar_idx(trades, idx7):
    edges = ns_i64(idx7)
    out = []
    for t in trades:
        pos = np.searchsorted(edges, np.int64(pd.Timestamp(t['entry_t']).value), side='right') - 1
        out.append(max(0, min(pos, len(edges) - 1)))
    return np.array(out)


def score_config(reg, lab7, tT, tS, bi_T, bi_S, warm):
    # S1 일치율(워밍업 제외, 라벨 유효)
    m = (np.arange(len(reg)) >= warm) & (lab7 >= 0)
    acc = round(100 * (reg[m] == lab7[m]).mean(), 1) if m.any() else 0.0
    # 봇별 국면 PF
    regT = reg[bi_T]; regS = reg[bi_S]
    RT = np.array([t['R'] for t in tT]); RS = np.array([t['R'] for t in tS])
    t_in_tr = metrics(RT[np.isin(regT, list(TREND_REG))]); t_in_rg = metrics(RT[np.isin(regT, list(RANGE_REG))])
    s_in_rg = metrics(RS[np.isin(regS, list(RANGE_REG))]); s_in_tr = metrics(RS[np.isin(regS, list(TREND_REG))])
    # 소표본 가드 + 랭킹 캡: n<10이면 0, PF는 랭킹시 5.0 상한(한 국면의 운=PF999가 격자1위 차지 방지). 원본PF는 별도 기록.
    def gpf(mm):
        return min(mm['PF'], 5.0) if mm['n'] >= 10 else 0.0
    L = round(gpf(t_in_tr) + gpf(s_in_rg), 3)
    sep = round((gpf(t_in_tr) - min(t_in_rg['PF'], 5.0)) + (gpf(s_in_rg) - min(s_in_tr['PF'], 5.0)), 3)
    flips = int((np.diff(reg[warm:]) != 0).sum())
    return dict(label_acc=acc, L_score=L, separation=sep,
                trendPF_trendreg=t_in_tr['PF'], trendPF_rangereg=t_in_rg['PF'],
                swPF_rangereg=s_in_rg['PF'], swPF_trendreg=s_in_tr['PF'],
                n_t_tr=t_in_tr['n'], n_s_rg=s_in_rg['n'], flips=flips)


def gen_windows(t0, t1):
    wins = []; ts = t0 + pd.DateOffset(months=TRAIN_MIN)
    while ts < t1:
        wins.append((t0, ts, min(ts + pd.DateOffset(months=TEST_M), t1))); ts += pd.DateOffset(months=STEP_M)
    return wins


def main():
    print("[Stg3] 장세판단(4국면) 로직 완성 — 90격자 봇PF 채점 + 워크포워드 + ML")
    open(os.path.join(HERE, ".run_start"), "w").close()
    champ = load_engine(os.path.join(BOTS, "SpTrd_Fib_V1_Champion.py"), "champ_engine")
    sdca = load_engine(os.path.join(BOTS, "SidewayDCA_Stg7_engine.py"), "sdca_engine")
    DATA = find_file(["Merged_Data_with_Regime_Features.csv", "merged_data.csv"])
    OIPATH = find_file(["Merged_Data.csv", "merged_data.csv"])
    FUND = find_file(["BTCUSDT_funding_history_8h.csv", "funding_history_8h.csv", "sample_BTCUSDT_funding_history_8h.csv"])
    if DATA is None:
        pd.DataFrame([{'x': 'no data'}]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig'); return

    tT, tS, (o, h, l, c), idx7, fund_real = get_trades(champ, sdca, DATA, OIPATH, FUND)
    lab7 = resample_label_7h(DATA, idx7)
    if lab7 is None:
        lab7 = np.full(len(idx7), -1, dtype=int)
    ind = RC.compute_indicators(o, h, l, c, RC.DEFAULT_PARAMS)   # 지표는 1회만
    bi_T = trade_bar_idx(tT, idx7); bi_S = trade_bar_idx(tS, idx7)
    warm = 2 * RC.DEFAULT_PARAMS['adx_n']
    bars_per_year = 24 * 365 / (champ.TF_MIN / 60.0)
    print(f"[준비] 7h봉 {len(c)} / 추세거래 {len(tT)} / 횡보거래 {len(tS)} / 라벨유효 {(lab7>=0).sum()} / 펀딩 {'REAL' if fund_real else 'NONE'}")

    # ── 90격자 채점(S3·S4·S5·S6 + 각 행에 S1·S2·S7) ──
    rows = []
    for w in W_GRID:
        for chi in CHOP_GRID:
            for axi in ADX_GRID:
                for vn in VOTE_GRID:
                    P = dict(w=w, chop_hi=chi, adx_hi=axi, vote_n=vn)
                    reg, _, _, _ = RC.classify(o, h, l, c, P, ind=ind)
                    sc = score_config(reg, lab7, tT, tS, bi_T, bi_S, warm)
                    sc.update(dict(w=w, chop_hi=chi, adx_hi=axi, vote_n=vn,
                                   flips_per_yr=round(sc['flips'] / (len(c) / bars_per_year), 1)))
                    rows.append(sc)
    grid = pd.DataFrame(rows)
    grid.to_csv(os.path.join(HERE, "grid_scores.csv"), index=False, encoding='utf-8-sig')
    best = grid.sort_values(['L_score', 'separation'], ascending=False).iloc[0]
    bp = dict(w=best['w'], chop_hi=best['chop_hi'], adx_hi=best['adx_hi'], vote_n=int(best['vote_n']))
    reg_b, _, _, _ = RC.classify(o, h, l, c, bp, ind=ind)

    # ── S1 혼동행렬(best) ──
    m = (np.arange(len(reg_b)) >= warm) & (lab7 >= 0)
    conf = np.zeros((4, 4), dtype=int)
    for cl, la in zip(reg_b[m], lab7[m]):
        if 0 <= cl < 4 and 0 <= la < 4:
            conf[cl, la] += 1
    cdf = pd.DataFrame(conf, index=[f"분류_{REGIME_MAP[i]}" for i in range(4)],
                       columns=[f"정답_{REGIME_MAP[i]}" for i in range(4)])
    cdf.to_csv(os.path.join(HERE, "confusion.csv"), encoding='utf-8-sig')

    # ── S2 국면별 봇 PF(best) ──
    regT = reg_b[bi_T]; regS = reg_b[bi_S]; RT = np.array([t['R'] for t in tT]); RS = np.array([t['R'] for t in tS])
    pf_rows = []
    for code in range(4):
        mt = metrics(RT[regT == code]); ms = metrics(RS[regS == code])
        pf_rows.append(dict(regime=REGIME_MAP[code], trend_n=mt['n'], trend_PF=mt['PF'], trend_R=mt['ret'],
                            sw_n=ms['n'], sw_PF=ms['PF'], sw_R=ms['ret']))
    pd.DataFrame(pf_rows).to_csv(os.path.join(HERE, "regime_bot_pf.csv"), index=False, encoding='utf-8-sig')

    # ── S8 워크포워드(best 동결): OOS 일치율 + 국면별 봇 PF 유지 ──
    t0 = idx7[0]; t1 = idx7[-1]; wins = gen_windows(t0, t1); wf = []
    edges = ns_i64(idx7)
    for k, (a, tes, tee) in enumerate(wins, 1):
        te_lo = np.int64(pd.Timestamp(tes).value); te_hi = np.int64(pd.Timestamp(tee).value)
        bm = (edges >= te_lo) & (edges < te_hi) & (np.arange(len(reg_b)) >= warm) & (lab7 >= 0)
        acc = round(100 * (reg_b[bm] == lab7[bm]).mean(), 1) if bm.any() else 0.0
        tmask = (np.array([pd.Timestamp(t['entry_t']).value for t in tT]) >= te_lo) & (np.array([pd.Timestamp(t['entry_t']).value for t in tT]) < te_hi)
        smask = (np.array([pd.Timestamp(t['entry_t']).value for t in tS]) >= te_lo) & (np.array([pd.Timestamp(t['entry_t']).value for t in tS]) < te_hi)
        tpf = metrics(RT[tmask & np.isin(regT, list(TREND_REG))]); spf = metrics(RS[smask & np.isin(regS, list(RANGE_REG))])
        wf.append(dict(win=k, test=f"{tes.date()}~{tee.date()}", OOS_label_acc=acc,
                       OOS_trendPF_trendreg=tpf['PF'], OOS_swPF_rangereg=spf['PF'], n_t=tpf['n'], n_s=spf['n']))
    pd.DataFrame(wf).to_csv(os.path.join(HERE, "walkforward.csv"), index=False, encoding='utf-8-sig')
    wf_acc = [r['OOS_label_acc'] for r in wf]

    # ── S8 ML 대체: 표준 best 일치율 vs GradBoost OOS 일치율 ──
    ml_row = {}
    try:
        from sklearn.ensemble import GradientBoostingClassifier
        X = RC.feature_matrix(ind); y = lab7
        valid = (np.arange(len(y)) >= warm) & (y >= 0) & np.isfinite(X).all(axis=1)
        oos_pred = []; oos_true = []
        for (a, tes, tee) in wins:
            te_lo = np.int64(pd.Timestamp(tes).value); te_hi = np.int64(pd.Timestamp(tee).value)
            tr = valid & (edges < te_lo); te = valid & (edges >= te_lo) & (edges < te_hi)
            if tr.sum() < 100 or te.sum() < 10:
                continue
            clf = GradientBoostingClassifier(n_estimators=120, max_depth=3, random_state=0)
            clf.fit(X[tr], y[tr]); p = clf.predict(X[te])
            oos_pred += list(p); oos_true += list(y[te])
        ml_acc = round(100 * np.mean(np.array(oos_pred) == np.array(oos_true)), 1) if oos_pred else 0.0
        std_best_acc = float(best['label_acc'])
        ml_row = dict(standard_best_label_acc=std_best_acc, ML_OOS_label_acc=ml_acc,
                      ML_better=('YES' if ml_acc > std_best_acc + 2 else 'NO'),
                      recommend=('ML' if ml_acc > std_best_acc + 2 else 'STANDARD'))
    except Exception as e:
        ml_row = dict(standard_best_label_acc=float(best['label_acc']), ML_OOS_label_acc='ERR', ML_better='NA', recommend='STANDARD', err=str(e)[:60])
    pd.DataFrame([ml_row]).to_csv(os.path.join(HERE, "ml_compare.csv"), index=False, encoding='utf-8-sig')

    verdict = (f"VERDICT Stg3 장세판단 완성 | 7h봉 {len(c)} 추세{len(tT)}/횡보{len(tS)} | "
               f"[BEST설정] w={bp['w']} CHOP>{bp['chop_hi']} ADX>{bp['adx_hi']} 다수결{bp['vote_n']}/4 | "
               f"[S1 일치율] {best['label_acc']}% (4국면 무작위25%) | "
               f"[S2 봇PF] 추세봇 추세국면 {best['trendPF_trendreg']} vs 레인지 {best['trendPF_rangereg']} / 횡보봇 레인지 {best['swPF_rangereg']} vs 추세 {best['swPF_trendreg']} | "
               f"분리도 {best['separation']} (양수=분류성공) | [S7 전환] {best['flips_per_yr']}회/년 | "
               f"[S8 워크포워드 {len(wins)}창] OOS일치율 {wf_acc} | ML {ml_row.get('ML_OOS_label_acc')}% vs 표준 {ml_row.get('standard_best_label_acc')}% -> 추천:{ml_row.get('recommend')} | "
               f"펀딩 {'REAL' if fund_real else 'NONE'}")
    print("[verdict] " + verdict)
    pd.DataFrame([dict(sec=verdict),
                  dict(sec=f"[BEST행] {dict(best)}"),
                  dict(sec=f"[국면별봇PF] {pf_rows}"),
                  dict(sec=f"[워크포워드] {wf}"),
                  dict(sec=f"[ML비교] {ml_row}")]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')
    with open(os.path.join(HERE, ".stg3_metric"), "w", encoding="utf-8") as f:
        f.write(f"n_trend={len(tT)}\nn_sw={len(tS)}\nbars7h={len(c)}\nlabel_valid={(lab7>=0).sum()}\n"
                f"best_w={bp['w']}\nbest_chop={bp['chop_hi']}\nbest_adx={bp['adx_hi']}\nbest_vote={bp['vote_n']}\n"
                f"best_label_acc={best['label_acc']}\nbest_L={best['L_score']}\nbest_sep={best['separation']}\n"
                f"trendPF_trendreg={best['trendPF_trendreg']}\ntrendPF_rangereg={best['trendPF_rangereg']}\n"
                f"swPF_rangereg={best['swPF_rangereg']}\nswPF_trendreg={best['swPF_trendreg']}\n"
                f"flips_per_yr={best['flips_per_yr']}\ngrid_n={len(grid)}\nwf_windows={len(wins)}\nwf_acc={wf_acc}\n"
                f"ml_oos_acc={ml_row.get('ML_OOS_label_acc')}\nstd_best_acc={ml_row.get('standard_best_label_acc')}\nrecommend={ml_row.get('recommend')}\n"
                f"label_in_classifier_input=False\nfunding={'REAL' if fund_real else 'NONE'}\n")
    print("[save] grid_scores/confusion/regime_bot_pf/walkforward/ml_compare/summary.csv")


if __name__ == "__main__":
    main()
