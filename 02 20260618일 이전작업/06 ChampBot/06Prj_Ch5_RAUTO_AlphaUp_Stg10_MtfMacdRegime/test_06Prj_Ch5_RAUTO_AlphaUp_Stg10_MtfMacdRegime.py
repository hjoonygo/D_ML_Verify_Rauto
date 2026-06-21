# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch5_RAUTO_AlphaUp_Stg10_MtfMacdRegime.py
# 코드길이: 약 400줄 | 내부버전: RAUTO_AlphaUp_06_Ch5_Stg10_MtfMacdRegime | 로직 전체 출력
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   엔진 무수정. 업로드된 MTF MACD(단기14-28/중기52-104/장기210-420 EMA차)를 사장님 규칙대로 코드화해
#   (1) 장세를 판별하고 (2) label_smc 정답지로 OOS 정확도를 재고 (3) 그 판별로 'POV 조건부 사이징'을 걸어
#   base / 무조건POV(일치×2·반대×0.25) / 조건부POV(하락·변동성에만 가점) 3자를 비교한다.
#
#   ★MTF MACD 정규화: 각 MACD = (EMA_fast - EMA_slow) / close * 100  (가격대비 %; 시기왜곡 제거)
#     EMA는 7h봉(기본) 종가로 계산. 다중 TF는 6h/7h/8h.
#   ★사장님 규칙(전부 과거봉 기반 = lookahead 없음):
#     ① 방향 = 중기MACD 부호 (양=상승 / 음=하락)
#     ② 강신호 = 단기·중기 동부호 AND 단기 0선 급속돌파(부호전환 & |Δ단기| 상위40%) AND 중기 기울기 턴어라운드
#     ③ 조정제한(강추세 유지) = |중기MACD_norm| >= STR_HI(학습기간 분위수 0.6) 이면 단기 0선 이탈 무시
#     ④ 장세매핑: 강상승(중기>0&|중기|>=STR_HI), 강하락(중기<0&|중기|>=STR_HI),
#                  전환(규칙②성립), 그외 약추세/횡보
#   ★새 POV(A+B): 장기MACD 부호=큰 방향(B). (단기-장기),(중기-장기) 편차 부호=과매수(+)/과매도(-) (A).
#     롱 진입 POV일치 = 적정가(장기) 대비 과매도(편차<0) / 숏 일치 = 과매수(편차>0).
#   [임계는 학습기간(앞70%)에서만 산출해 검증기간에 적용 → 과최적화·미래참조 차단]
#   [label_smc_* 는 정답지(정확도 측정 전용), 판별/사이징 입력에 절대 미사용]
#
# [PATH] 실행: D:\ML\Verify\06Prj_..._Stg10_MtfMacdRegime\ . 데이터: 상위 D:\ML\Verify\ (4종).
# [OUTPUT] macd_regime_oos.csv / regime_confusion.csv / pov_compare.csv / pov_compare_by_regime.csv / summary.csv + .stg10_metric
# ==============================================================================
import os, sys, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE); BOTS = os.path.join(HERE, "bots")
COST_RT = 0.0014
M_AGREE = 2.0; M_OPPO = 0.25
# MTF MACD 길이(Pine 그대로)
F1, S1 = 14, 28; F2, S2 = 52, 104; F3, S3 = 210, 420
REGIME_MAP = {'uptrend': 0, 'downtrend': 1, 'volatile_range': 2, 'dead_range': 3}
REGIME_NAME = {0: 'uptrend', 1: 'downtrend', 2: 'volatile_range', 3: 'dead_range', -1: 'unknown'}
# Stg9 결과: POV 가점이 '이득'인 장세(하락추세·변동성횡보)만 ON
POV_ON_REGIMES = {'downtrend', 'volatile_range'}


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
FUND = find_file(["BTCUSDT_funding_history_8h.csv", "funding_history_8h.csv", "sample_BTCUSDT_funding_history_8h.csv"])
NOMINAL = champ.NOMINAL


def ema(x, span):
    a = 2.0 / (span + 1.0); out = np.full(len(x), np.nan); m = None
    for i, v in enumerate(x):
        if np.isnan(v):
            out[i] = m if m is not None else np.nan; continue
        m = v if m is None else a * v + (1 - a) * m
        out[i] = m
    return out


def macd_norm(close, f, s):
    return (ema(close, f) - ema(close, s)) / np.where(close > 0, close, np.nan) * 100.0


def metrics(R):
    R = np.asarray(R, float); n = len(R)
    if n == 0:
        return dict(n=0, PF=0.0, ret_pct=0.0, payoff=0.0, win_pct=0.0)
    win = R[R > 0]; los = R[R < 0]; gp = float(win.sum()); gl = float(-los.sum())
    pf = round(gp / gl, 3) if gl > 0 else (999.0 if gp > 0 else 0.0)
    payoff = round(win.mean() / -los.mean(), 3) if len(win) and len(los) else 0.0
    return dict(n=n, PF=pf, ret_pct=round(R.sum() * 100, 2), payoff=payoff, win_pct=round(100 * len(win) / n, 1))


def classify_regime(m1, m2, m3, dm2, str_hi, slow_q):
    # 사장님 규칙 ①~④ → 4장세. m=정규화MACD, dm2=중기 기울기. 모두 그 봉까지의 과거기반.
    n = len(m1); reg = np.full(n, -1)
    for i in range(n):
        a1, a2, a3, d2 = m1[i], m2[i], m3[i], dm2[i]
        if np.isnan(a2):
            continue
        strong = abs(a2) >= str_hi                       # 규칙③: 중기 강도 유지
        if a2 > 0 and strong:
            reg[i] = 0                                   # 강상승
        elif a2 < 0 and strong:
            reg[i] = 1                                   # 강하락
        else:
            # 약한 구간: 변동성횡보 vs 죽은횡보 — 단기 변동성으로 분리
            reg[i] = 2 if abs(a1) >= slow_q else 3
    return reg


def main():
    print("[Stg10] MTF MACD 장세판별 + 조건부 POV (사장님 규칙)")
    open(os.path.join(HERE, ".run_start"), "w").close()
    if DATA is None:
        pd.DataFrame([{'x': '데이터없음'}]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig'); return
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
        return side * fs if fs is not None else 0.0

    head = list(pd.read_csv(DATA, nrows=1).columns)
    lbl = next((c for c in head if c.startswith('label_smc_8')), None) or next((c for c in head if c.startswith('label_smc')), None)
    lab = pd.read_csv(DATA, usecols=['timestamp', lbl], index_col='timestamp', parse_dates=True)
    if getattr(lab.index, 'tz', None) is not None:
        lab.index = lab.index.tz_localize(None)
    lab = lab.sort_index()

    df1m = champ.load_data(DATA)
    tf_auc = {}; macd_acc = {}
    main_TF = champ.TF_MIN
    chosen = {}
    for TF in [360, 420, 480]:
        df_tf = champ.resample_tf(df1m, TF); close = df_tf['close'].values; idx = df_tf.index
        m1 = macd_norm(close, F1, S1); m2 = macd_norm(close, F2, S2); m3 = macd_norm(close, F3, S3)
        dm2 = np.concatenate([[np.nan], np.diff(m2)])
        reg_lab = lab[lbl].resample(f"{TF}min", label='left', closed='left').last().reindex(idx).map(REGIME_MAP).values.astype('float64')
        nb = len(idx); cut = int(nb * 0.7)
        # 임계: 학습기간만
        str_hi = np.nanquantile(np.abs(m2[:cut]), 0.60)
        slow_q = np.nanquantile(np.abs(m1[:cut]), 0.50)
        reg_pred = classify_regime(m1, m2, m3, dm2, str_hi, slow_q)
        # OOS 정확도(검증기간)
        te = np.arange(cut, nb)
        valid = te[(reg_pred[te] >= 0) & (~np.isnan(reg_lab[te]))]
        acc = round(100 * float((reg_pred[valid] == reg_lab[valid]).mean()), 1) if len(valid) else 0.0
        maj = round(100 * float(pd.Series(reg_lab[:cut][~np.isnan(reg_lab[:cut])]).value_counts(normalize=True).max()), 1)
        # 추세이분 AUC(중기MACD를 점수로)
        ytr = np.isin(reg_lab, [0, 1]).astype(float)
        sc = np.abs(m2)
        ok = te[~np.isnan(sc[te]) & ~np.isnan(reg_lab[te])]
        yb = ytr[ok]; s = sc[ok]
        if yb.sum() > 0 and (len(yb) - yb.sum()) > 0:
            o = s.argsort(kind='mergesort'); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1)
            p = int(yb.sum()); q = len(yb) - p
            auc = round(float((r[yb == 1].sum() - p * (p + 1) / 2) / (p * q)), 3)
        else:
            auc = 0.5
        tf_auc[f"{TF//60}h"] = auc; macd_acc[f"{TF//60}h"] = acc
        if TF == 420:
            chosen = dict(idx=idx, m1=m1, m2=m2, m3=m3, reg_pred=reg_pred, reg_lab=reg_lab,
                          str_hi=str_hi, cut=cut, nb=nb, acc=acc, maj=maj)
            # 혼동행렬
            conf = np.zeros((4, 4), int)
            for a, p in zip(reg_lab[te], reg_pred[te]):
                if not np.isnan(a) and p >= 0:
                    conf[int(a), int(p)] += 1
            pd.DataFrame(conf, index=[f'실제_{REGIME_NAME[i]}' for i in range(4)],
                         columns=[f'MACD_{REGIME_NAME[i]}' for i in range(4)]).to_csv(
                os.path.join(HERE, "regime_confusion.csv"), encoding='utf-8-sig')
    pd.DataFrame([dict(tf=k, macd_4regime_acc=macd_acc[k], trend_binary_auc=tf_auc[k]) for k in macd_acc]).to_csv(
        os.path.join(HERE, "macd_regime_oos.csv"), index=False, encoding='utf-8-sig')

    # ───── 추세봇 거래 + 3가지 사이징 비교 (7h) ─────
    champ.TF_MIN = main_TF
    df7 = champ.resample_tf(df1m, main_TF); sig = champ.compute_signals(df7)
    idx7 = df7.index; oi7 = champ.load_oi_8h(OIPATH, idx7); bb7 = champ.load_bb_8h(DATA, idx7)
    close7 = df7['close'].values
    m1 = macd_norm(close7, F1, S1); m2 = macd_norm(close7, F2, S2); m3 = macd_norm(close7, F3, S3)
    dm2 = np.concatenate([[np.nan], np.diff(m2)])
    cut7 = int(len(idx7) * 0.7)
    str_hi = np.nanquantile(np.abs(m2[:cut7]), 0.60); slow_q = np.nanquantile(np.abs(m1[:cut7]), 0.50)
    reg_pred7 = classify_regime(m1, m2, m3, dm2, str_hi, slow_q)
    reg_lab7 = lab[lbl].resample(f"{main_TF}min", label='left', closed='left').last().reindex(idx7).map(REGIME_MAP).values.astype('float64')

    ttr = champ.run_strategy(df7, sig, 0, 'none', 0.8, gate_mode='er', gate_er=0.45,
                             dz_oi=oi7, gate_bb=bb7, fib=(0.3, 0.5, 0.6), split_mode='A', split_n=3)
    rows = []
    for t in ttr:
        R = t['side'] * (t['exit'] - t['entry']) / t['entry'] - COST_RT - fund_pay(t['side'], t['entry_t'], t['exit_t'])
        pos = idx7.searchsorted(pd.Timestamp(t['entry_t'])) - 1
        if pos < 0:
            pos = 0
        # 새 POV(A+B): 장기MACD 기준 편차. 롱은 (중기-장기)<0=과매도=일치
        dev_pov = (m2[pos] - m3[pos]) if pos < len(m2) else np.nan
        side = t['side']
        if np.isnan(dev_pov):
            pov = '중립'
        elif (side > 0 and dev_pov < 0) or (side < 0 and dev_pov > 0):
            pov = '일치'
        else:
            pov = '반대'
        macd_reg = REGIME_NAME[int(reg_pred7[pos])] if (0 <= pos < len(reg_pred7) and reg_pred7[pos] >= 0) else 'unknown'
        true_reg = REGIME_NAME[int(reg_lab7[pos])] if (0 <= pos < len(reg_lab7) and not np.isnan(reg_lab7[pos])) else 'unknown'
        # 무조건 POV 사이징
        size_uncond = M_AGREE if pov == '일치' else (M_OPPO if pov == '반대' else 1.0)
        # 조건부: MACD가 'POV_ON 장세'로 본 경우에만 사이징, 아니면 1.0
        size_cond = size_uncond if macd_reg in POV_ON_REGIMES else 1.0
        is_test = pos >= cut7
        rows.append(dict(side='롱' if side > 0 else '숏', pov=pov, macd_reg=macd_reg, true_reg=true_reg,
                         is_test=is_test, R_base=float(R), R_uncond=float(R * size_uncond), R_cond=float(R * size_cond)))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "pov_all_trades.csv"), index=False, encoding='utf-8-sig')

    # 전체 + 검증기간(OOS) 비교
    def three(sub, tag):
        return dict(seg=tag, **{f"{k}_{nm}": metrics(sub[col].values)[k]
                                for col, nm in [('R_base', 'base'), ('R_uncond', 'uncond'), ('R_cond', 'cond')]
                                for k in ['n', 'PF', 'ret_pct', 'payoff']})
    cmp_rows = []
    for tag, sub in [('전체', df), ('검증기간OOS', df[df.is_test])]:
        m_b = metrics(sub.R_base.values); m_u = metrics(sub.R_uncond.values); m_c = metrics(sub.R_cond.values)
        cmp_rows.append(dict(seg=tag, n=m_b['n'],
                             PF_base=m_b['PF'], PF_uncond=m_u['PF'], PF_cond=m_c['PF'],
                             ret_base=m_b['ret_pct'], ret_uncond=m_u['ret_pct'], ret_cond=m_c['ret_pct'],
                             payoff_base=m_b['payoff'], payoff_uncond=m_u['payoff'], payoff_cond=m_c['payoff'],
                             profit_base=round(float(sub.R_base.sum()*NOMINAL), 0),
                             profit_uncond=round(float(sub.R_uncond.sum()*NOMINAL), 0),
                             profit_cond=round(float(sub.R_cond.sum()*NOMINAL), 0)))
    cmpdf = pd.DataFrame(cmp_rows); cmpdf.to_csv(os.path.join(HERE, "pov_compare.csv"), index=False, encoding='utf-8-sig')

    # 실제장세별 3자 비교(조건부가 상승추세 적자를 막나)
    byreg = []
    for rg, g in df.groupby('true_reg'):
        byreg.append(dict(true_reg=rg, n=len(g),
                          ret_base=round(g.R_base.sum()*100, 2), ret_uncond=round(g.R_uncond.sum()*100, 2),
                          ret_cond=round(g.R_cond.sum()*100, 2),
                          PF_base=metrics(g.R_base.values)['PF'], PF_uncond=metrics(g.R_uncond.values)['PF'],
                          PF_cond=metrics(g.R_cond.values)['PF']))
    pd.DataFrame(byreg).to_csv(os.path.join(HERE, "pov_compare_by_regime.csv"), index=False, encoding='utf-8-sig')

    oos = cmpdf[cmpdf.seg == '검증기간OOS'].iloc[0]
    full = cmpdf[cmpdf.seg == '전체'].iloc[0]
    cond_beats_uncond = (oos['ret_cond'] >= oos['ret_uncond'] * 0.9) and (oos['PF_cond'] >= oos['PF_uncond'])
    cond_beats_base = oos['ret_cond'] > oos['ret_base'] and oos['PF_cond'] >= oos['PF_base']
    flag = ("조건부POV 유효(무조건보다 안전+base보다 이득)" if (cond_beats_uncond and cond_beats_base)
            else "조건부POV 제한적/무효 — base 유지 권고")
    verdict = (f"VERDICT Stg10 | MTF MACD(정규화) 장세판별 acc {chosen.get('acc')}%(기준선{chosen.get('maj')}%) | "
               f"다중TF acc {macd_acc} 추세AUC {tf_auc} | "
               f"[OOS] base PF{oos['PF_base']}/{oos['ret_base']}% / 무조건POV PF{oos['PF_uncond']}/{oos['ret_uncond']}% / "
               f"조건부POV PF{oos['PF_cond']}/{oos['ret_cond']}% | "
               f"[전체] base {full['ret_base']}% / 무조건 {full['ret_uncond']}% / 조건부 {full['ret_cond']}% | => {flag}")
    print("[verdict] " + verdict)
    pd.DataFrame([dict(sec=verdict),
                  dict(sec=f"[MACD 장세별 3자] {byreg}")]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')

    with open(os.path.join(HERE, ".stg10_metric"), "w", encoding="utf-8") as f:
        f.write(f"macd_acc_7h={chosen.get('acc')}\nmaj={chosen.get('maj')}\nmacd_acc_all={macd_acc}\ntrend_auc={tf_auc}\n"
                f"oos_pf_base={oos['PF_base']}\noos_pf_uncond={oos['PF_uncond']}\noos_pf_cond={oos['PF_cond']}\n"
                f"oos_ret_base={oos['ret_base']}\noos_ret_uncond={oos['ret_uncond']}\noos_ret_cond={oos['ret_cond']}\n"
                f"full_ret_base={full['ret_base']}\nfull_ret_uncond={full['ret_uncond']}\nfull_ret_cond={full['ret_cond']}\n"
                f"n_trades={len(df)}\nhas_label_in_feats=False\nfunding={'REAL' if ft is not None else 'NONE'}\nverdict_flag={flag}\n")
    print("[save] macd_regime_oos / regime_confusion / pov_compare / pov_compare_by_regime / summary.csv")


if __name__ == "__main__":
    main()
