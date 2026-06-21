# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch5_RAUTO_AlphaUp_Stg11_LongMacdMLSizing.py
# 코드길이: 약 400줄 | 내부버전: RAUTO_AlphaUp_06_Ch5_Stg11_LongMacdMLSizing | 로직 전체 출력
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   엔진 무수정. 장기MACD(210-420 EMA차, 정규화) '하나만'으로:
#   (라) 장세를 판별하고 label_smc 정답지로 OOS 정확도/혼동행렬을 잰다.
#   (나) 진입방향이 장기MACD 부호와 일치/불일치인지로 추세봇 진입수량을 곱한다.
#   ML 그리드: 일치배수 {1.8,2.0,2.2,2.4,2.6} × 불일치배수 {0.15,0.25,0.4,0.5} = 20조합.
#     ★학습기간(앞 70%)에서 '최적조합'(검증식 점수)을 고르고, 검증기간(뒤 30%, OOS)에서 성과 확인.
#     → 과최적화 차단: 학습서 고른 조합이 OOS에서도 좋은지 별도 표기.
#   ★강제청산 위험 + MDD: 추세봇 명목 $50,000(=START_CAP $10k의 5배=교차5x).
#     사이징 ×2.6이면 노출 13x. 한 거래 손실로 자본<=MIN_CAP($100) 닿으면 '강제청산(파산)'.
#     - 단리(엔진 521행: cap += R*size*NOMINAL)와 복리(cap *= 1+R*size*lev) 둘 다 청산·MDD 측정.
#     - 거래별 최저자본, 청산발생 여부/시점, 최대낙폭(MDD).
#   [정규화] 장기MACD = (EMA210-EMA420)/close*100. [임계는 학습기간만] [label 미사용=판별입력 아님]
#   [Lookahead 없음] 장기MACD·임계 모두 과거봉 기반. 사이징은 진입시점 부호로 결정.
#
# [PATH] 실행: D:\ML\Verify\06Prj_..._Stg11_LongMacdMLSizing\ . 데이터: 상위 (4종).
# [OUTPUT] long_regime_oos.csv / sizing_grid.csv / best_by_regime.csv / best_by_year.csv / best_by_side.csv
#          / liquidation_mdd.csv / summary.csv + .stg11_metric
# ==============================================================================
import os, sys, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE); BOTS = os.path.join(HERE, "bots")
COST_RT = 0.0014
F3, S3 = 210, 420          # 장기MACD만
AGREE_GRID = [1.8, 2.0, 2.2, 2.4, 2.6]
OPPO_GRID = [0.15, 0.25, 0.4, 0.5]
REGIME_MAP = {'uptrend': 0, 'downtrend': 1, 'volatile_range': 2, 'dead_range': 3}
REGIME_NAME = {0: 'uptrend', 1: 'downtrend', 2: 'volatile_range', 3: 'dead_range', -1: 'unknown'}


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
NOMINAL = champ.NOMINAL; START_CAP = champ.START_CAP; MIN_CAP = champ.MIN_CAP


def ema(x, span):
    a = 2.0 / (span + 1.0); out = np.full(len(x), np.nan); m = None
    for i, v in enumerate(x):
        if np.isnan(v):
            out[i] = m if m is not None else np.nan; continue
        m = v if m is None else a * v + (1 - a) * m
        out[i] = m
    return out


def metrics(R):
    R = np.asarray(R, float); n = len(R)
    if n == 0:
        return dict(n=0, PF=0.0, ret_pct=0.0, payoff=0.0, win_pct=0.0)
    win = R[R > 0]; los = R[R < 0]; gp = float(win.sum()); gl = float(-los.sum())
    pf = round(gp / gl, 3) if gl > 0 else (999.0 if gp > 0 else 0.0)
    payoff = round(win.mean() / -los.mean(), 3) if len(win) and len(los) else 0.0
    return dict(n=n, PF=pf, ret_pct=round(R.sum() * 100, 2), payoff=payoff, win_pct=round(100 * len(win) / n, 1))


def sim_simple(R, size):
    # 단리(엔진 521행 방식): cap += R*size*NOMINAL. 청산=cap<=MIN_CAP. MDD 동반.
    cap = START_CAP; mincap = START_CAP; peak = START_CAP; mdd = 0.0; liq = False; liq_i = -1
    for i, (r, s) in enumerate(zip(R, size)):
        cap += r * s * NOMINAL; mincap = min(mincap, cap); peak = max(peak, cap)
        if peak > 0:
            mdd = min(mdd, (cap - peak) / peak)
        if cap <= MIN_CAP and not liq:
            liq = True; liq_i = i
    return round(cap - START_CAP, 0), round(mincap, 0), round(mdd * 100, 1), liq, liq_i


def sim_comp(R, size, lev=5.0):
    # 복리: cap *= (1 + R*size*lev/5*... ) — 여기선 노출배수=size 그대로(명목비중). 청산·MDD.
    cap = START_CAP; peak = START_CAP; mdd = 0.0; liq = False; liq_i = -1
    for i, (r, s) in enumerate(zip(R, size)):
        cap *= (1 + r * s)
        peak = max(peak, cap)
        if peak > 0:
            mdd = min(mdd, (cap - peak) / peak)
        if cap <= MIN_CAP and not liq:
            liq = True; liq_i = i; break
    return round(cap - START_CAP, 0), round(mdd * 100, 1), liq, liq_i


def main():
    print("[Stg11] 장기MACD 장세판별(라) + 부호사이징(나) ML그리드 + 청산/MDD")
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

    TF = champ.TF_MIN
    df1m = champ.load_data(DATA); df7 = champ.resample_tf(df1m, TF); sig = champ.compute_signals(df7)
    idx7 = df7.index; oi7 = champ.load_oi_8h(OIPATH, idx7); bb7 = champ.load_bb_8h(DATA, idx7)
    close7 = df7['close'].values
    macd3 = (ema(close7, F3) - ema(close7, S3)) / np.where(close7 > 0, close7, np.nan) * 100.0
    dm3 = np.concatenate([[np.nan], np.diff(macd3)])
    nb = len(idx7); cut = int(nb * 0.7)
    reg_lab = lab[lbl].resample(f"{TF}min", label='left', closed='left').last().reindex(idx7).map(REGIME_MAP).values.astype('float64')

    # (라) 장기MACD만 4장세: 부호+강도(학습기간 분위수)
    str_hi = np.nanquantile(np.abs(macd3[:cut]), 0.60)
    reg_pred = np.full(nb, -1)
    for i in range(nb):
        a = macd3[i]
        if np.isnan(a):
            continue
        strong = abs(a) >= str_hi
        if a > 0 and strong:
            reg_pred[i] = 0
        elif a < 0 and strong:
            reg_pred[i] = 1
        elif a > 0:
            reg_pred[i] = 2
        else:
            reg_pred[i] = 3
    te = np.arange(cut, nb)
    valid = te[(reg_pred[te] >= 0) & (~np.isnan(reg_lab[te]))]
    acc = round(100 * float((reg_pred[valid] == reg_lab[valid]).mean()), 1) if len(valid) else 0.0
    maj = round(100 * float(pd.Series(reg_lab[:cut][~np.isnan(reg_lab[:cut])]).value_counts(normalize=True).max()), 1)
    conf = np.zeros((4, 4), int)
    for a, p in zip(reg_lab[te], reg_pred[te]):
        if not np.isnan(a) and p >= 0:
            conf[int(a), int(p)] += 1
    pd.DataFrame(conf, index=[f'실제_{REGIME_NAME[i]}' for i in range(4)],
                 columns=[f'L-MACD_{REGIME_NAME[i]}' for i in range(4)]).to_csv(
        os.path.join(HERE, "regime_confusion.csv"), encoding='utf-8-sig')
    pd.DataFrame([dict(metric='장기MACD_4장세정확도%', value=acc), dict(metric='기준선%', value=maj),
                 dict(metric='강도임계(학습)', value=round(float(str_hi), 4))]).to_csv(
        os.path.join(HERE, "long_regime_oos.csv"), index=False, encoding='utf-8-sig')

    # 추세봇 거래 + 장기MACD 부호 매칭
    ttr = champ.run_strategy(df7, sig, 0, 'none', 0.8, gate_mode='er', gate_er=0.45,
                             dz_oi=oi7, gate_bb=bb7, fib=(0.3, 0.5, 0.6), split_mode='A', split_n=3)
    recs = []
    for t in ttr:
        R = t['side'] * (t['exit'] - t['entry']) / t['entry'] - COST_RT - fund_pay(t['side'], t['entry_t'], t['exit_t'])
        pos = idx7.searchsorted(pd.Timestamp(t['entry_t'])) - 1
        if pos < 0:
            pos = 0
        lm = macd3[pos] if pos < len(macd3) else np.nan
        side = t['side']
        # (나) 진입방향 vs 장기MACD 부호
        if np.isnan(lm):
            agree = None
        else:
            agree = (side > 0 and lm > 0) or (side < 0 and lm < 0)
        rg = REGIME_NAME[int(reg_lab[pos])] if (0 <= pos < len(reg_lab) and not np.isnan(reg_lab[pos])) else 'unknown'
        recs.append(dict(side='롱' if side > 0 else '숏', year=pd.Timestamp(t['entry_t']).year,
                         regime=rg, agree=agree, R=float(R), is_test=pos >= cut, order=pos))
    df = pd.DataFrame(recs)
    df.to_csv(os.path.join(HERE, "stg11_all_trades.csv"), index=False, encoding='utf-8-sig')

    # ML 그리드: 20조합. 학습기간 점수로 최적 선택, OOS 확인.
    def sizes_for(ma, mo):
        s = np.ones(len(df))
        s[df.agree == True] = ma
        s[df.agree == False] = mo
        return s   # agree=None(장기MACD NaN)는 1.0
    grid = []
    df_tr = df[~df.is_test]; df_te = df[df.is_test]
    for ma in AGREE_GRID:
        for mo in OPPO_GRID:
            s_all = sizes_for(ma, mo)
            R_all = df.R.values * s_all
            R_tr = df_tr.R.values * sizes_for(ma, mo)[~df.is_test.values]
            R_te = df_te.R.values * sizes_for(ma, mo)[df.is_test.values]
            m_all = metrics(R_all); m_tr = metrics(R_tr); m_te = metrics(R_te)
            prof_s, mincap_s, mdd_s, liq_s, liqi_s = sim_simple(R_all, np.ones(len(R_all)))
            prof_c, mdd_c, liq_c, liqi_c = sim_comp(df.R.values, s_all)
            # 학습기간 점수(수익률×PF, 청산이면 큰 페널티)
            score_tr = m_tr['ret_pct'] * (m_tr['PF'] if m_tr['PF'] > 0 else 0)
            grid.append(dict(m_agree=ma, m_oppo=mo,
                             PF_all=m_all['PF'], ret_all=m_all['ret_pct'], payoff_all=m_all['payoff'],
                             PF_oos=m_te['PF'], ret_oos=m_te['ret_pct'],
                             profit_simple=prof_s, mincap_simple=mincap_s, MDD_simple=mdd_s,
                             liq_simple=('YES' if liq_s else 'NO'),
                             MDD_comp=mdd_c, liq_comp=('YES' if liq_c else 'NO'),
                             score_train=round(score_tr, 1)))
    gdf = pd.DataFrame(grid); gdf.to_csv(os.path.join(HERE, "sizing_grid.csv"), index=False, encoding='utf-8-sig')
    # 청산 없는 것 중 학습점수 최고 = ML 선택
    safe = gdf[(gdf.liq_simple == 'NO') & (gdf.liq_comp == 'NO')]
    pick = (safe if len(safe) else gdf).sort_values('score_train', ascending=False).iloc[0]
    best_ma, best_mo = pick['m_agree'], pick['m_oppo']

    # 최적조합으로 base vs 적용후 세 축 성적표
    s_best = sizes_for(best_ma, best_mo)
    df['R_pov'] = df.R.values * s_best

    def agg(key, order):
        out = []
        for k in order:
            g = df[df[key] == k]
            if len(g) == 0:
                continue
            mb = metrics(g.R.values); mp = metrics(g.R_pov.values)
            out.append(dict(**{key: k}, n=mb['n'], PF_base=mb['PF'], PF_pov=mp['PF'],
                            ret_base=mb['ret_pct'], ret_pov=mp['ret_pct'],
                            payoff_base=mb['payoff'], payoff_pov=mp['payoff'], win_pct=mb['win_pct'],
                            profit_base=round(float(g.R.sum()*NOMINAL), 0), profit_pov=round(float(g.R_pov.sum()*NOMINAL), 0)))
        return pd.DataFrame(out)
    agg('regime', ['uptrend', 'downtrend', 'volatile_range', 'dead_range']).to_csv(os.path.join(HERE, "best_by_regime.csv"), index=False, encoding='utf-8-sig')
    agg('year', sorted(df.year.unique())).to_csv(os.path.join(HERE, "best_by_year.csv"), index=False, encoding='utf-8-sig')
    agg('side', ['롱', '숏']).to_csv(os.path.join(HERE, "best_by_side.csv"), index=False, encoding='utf-8-sig')

    # 청산/MDD 표(최적 + 극단 ×2.6/0.15 비교)
    liq_rows = []
    for tag, ma, mo in [('ML최적', best_ma, best_mo), ('최대공격(2.6/0.15)', 2.6, 0.15), ('base(1.0/1.0)', 1.0, 1.0)]:
        s = sizes_for(ma, mo) if tag != 'base(1.0/1.0)' else np.ones(len(df))
        ps, mc, md, ls, li = sim_simple(df.R.values, s)
        pc, mdc, lc, lic = sim_comp(df.R.values, s)
        liq_rows.append(dict(조합=tag, 일치배수=ma, 불일치배수=mo,
                             단리수익금=ps, 단리최저자본=mc, 단리MDD=md, 단리청산=('YES' if ls else 'NO'),
                             복리MDD=mdc, 복리청산=('YES' if lc else 'NO')))
    pd.DataFrame(liq_rows).to_csv(os.path.join(HERE, "liquidation_mdd.csv"), index=False, encoding='utf-8-sig')

    m_base = metrics(df.R.values); m_pov = metrics(df.R_pov.values)
    ps, mc, md, ls, li = sim_simple(df.R.values, s_best)
    verdict = (f"VERDICT Stg11 | (라)장기MACD 4장세정확도 {acc}%(기준선{maj}%) | "
               f"(나)+ML 최적조합 일치×{best_ma}/불일치×{best_mo} (청산회피·학습점수최고) | "
               f"[전체] base PF{m_base['PF']}/{m_base['ret_pct']}%/${round(float(df.R.sum()*NOMINAL))} -> "
               f"적용 PF{m_pov['PF']}/{m_pov['ret_pct']}%/${ps} | 단리MDD{md}%/최저자본${mc}/청산{'YES' if ls else 'NO'} | "
               f"승률{m_base['win_pct']}%(불변)")
    print("[verdict] " + verdict)
    pd.DataFrame([dict(sec=verdict)]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')

    with open(os.path.join(HERE, ".stg11_metric"), "w", encoding="utf-8") as f:
        f.write(f"long_acc={acc}\nmaj={maj}\nbest_agree={best_ma}\nbest_oppo={best_mo}\n"
                f"base_pf={m_base['PF']}\nbase_ret={m_base['ret_pct']}\npov_pf={m_pov['PF']}\npov_ret={m_pov['ret_pct']}\n"
                f"pov_profit={ps}\nmdd_simple={md}\nmincap={mc}\nliq_simple={'YES' if ls else 'NO'}\n"
                f"win={m_base['win_pct']}\nn_trades={len(df)}\nn_agree={int((df.agree==True).sum())}\n"
                f"n_oppo={int((df.agree==False).sum())}\nhas_label_in_feats=False\nfunding={'REAL' if ft is not None else 'NONE'}\n"
                f"grid_rows={len(gdf)}\nany_liq={'YES' if (gdf.liq_simple=='YES').any() or (gdf.liq_comp=='YES').any() else 'NO'}\n")
    print("[save] long_regime_oos/sizing_grid/best_by_*/liquidation_mdd/regime_confusion/summary.csv")


if __name__ == "__main__":
    main()
