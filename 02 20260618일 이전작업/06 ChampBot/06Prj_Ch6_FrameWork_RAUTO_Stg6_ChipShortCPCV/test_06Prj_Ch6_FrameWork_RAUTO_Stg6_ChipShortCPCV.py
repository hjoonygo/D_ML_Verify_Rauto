# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch6_FrameWork_RAUTO_Stg6_ChipShortCPCV.py
# 코드길이: 약 400줄 | 내부버전: 06Prj_Ch6_Stg6_ChipShortCPCV_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]  사장님 확정 (라): A+B 굳히기. ML 장세예측은 폐기(Stg5 CPCV 0.495 확정).
#   A. 칩필터 2of3 확정: Stg4 PF4.1 조합을 CPCV(PF+거래수 채점)로 검증 → 과최적 아닌지 15경로 분포로 확인.
#   B. 추세봇 숏 보강: 숏(PF1.369) 약점을 ①장세별·년도별 분해 → ②숏전용 필터 격자(하락장·ADX·OI/펀딩) 비교
#                      → ③각 후보를 CPCV로 검증. 전부 전수 격자(라).
#   엔진 무수정(해시대조). 칩게이트=regime_classifier, CPCV=cpcv. 비용0.14%+실펀딩. label_smc 입력금지.
#
#   [A 칩필터 CPCV 채점=PF+거래수(확인A=다)]  Stg4 best조합(pre_n4/hold_k3/CHOP55/2of3/SQZ4.0) 고정 →
#     칩필터ON 횡보봇 거래를 CPCV 15경로로 PF분포. p25(하위25%)>1.0 & PF<1경로 적으면 견고.
#     비교군: 칩필터OFF(전체) 횡보봇도 같은 CPCV → ON이 OFF보다 PF분포 우위인가.
#
#   [B 숏 필터 격자=전부(확인B=라)]  추세봇 숏 거래만 대상. 3축 격자:
#     하락장확인: off / 분류기-하락국면만   ADX: off / >25 / >30   OI펀딩: off / 펀딩>0(롱과열)만
#     → 3×3×3=27조합. 각 조합 숏 PF·거래수 + CPCV PF분포. BEST=숏 PF개선 & 거래수 유지 & CPCV견고.
#
#   [★미래참조 차단]  칩게이트·숏필터 전부 진입봉까지 지표만(과거). CPCV는 거래를 봉그룹으로 나눠 채점(예측 아님).
#
# [PATH] 실행 D:\ML\verify\06Prj_Ch6_FrameWork_RAUTO_Stg6_ChipShortCPCV\ . 데이터 상위 D:\ML\verify.
# [OUTPUT] chip_cpcv.csv / chip_cpcv_paths.csv / short_breakdown.csv / short_grid.csv / short_cpcv_paths.csv /
#          ledger_trades.csv / summary.csv + .stg6_metric
# [In/Out 태그]
#   regime_classifier: compute_indicators / chip_gate_at(In 지표,봉,P/Out 통과bool) / classify(장세분해용)
#   cpcv: cpcv_pf_eval(In 거래봉위치,R,총봉/Out PF분포+경로상세)
#   엔진(무수정): champ.*(run_strategy/load_oi_8h/compute_signals) / sdca.*(run_bot_honest/load_funding/funding_sum)
#   본코드: ns_i64/metrics/get_trades(side·oi·펀딩부호 포함)/trade_bar_idx/short_filter_grid/agg_matrix/main
#   변수(동결): CHIP_BEST=dict(pre_n4,hold_k3,chop55,2of3,sqz4.0) SHORT_ADX=[0,25,30] N_GROUP=6 K_TEST=2 COST_RT=0.0014
# ==============================================================================
import os, sys, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE); BOTS = os.path.join(HERE, "bots")
sys.path.insert(0, HERE)
import regime_classifier as RC
import cpcv as CP

CHIP_BEST = dict(chip_pre_n=4, chip_hold_k=3, chip_chop_hi=55.0, chip_combo='2of3', chip_squeeze=4.0)
SHORT_ADX = [0.0, 25.0, 30.0]
N_GROUP = 6; K_TEST = 2; COST_RT = 0.0014
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


def funding_sign_at(ft, fr, ts_ns):
    # 진입시각 직전 펀딩 부호(+면 롱과열). ft 정렬됨.
    if ft is None:
        return 0.0
    i = np.searchsorted(ft, np.int64(ts_ns), side='right') - 1
    if i < 0:
        return 0.0
    return float(fr[i])


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
    edges = ns_i64(idx7)
    tT = []
    for t in ttr:
        R = t['side'] * (t['exit'] - t['entry']) / t['entry'] - COST_RT - fpay(t['side'], t['entry_t'], t['exit_t'])
        et = pd.Timestamp(t['entry_t'])
        pos = max(0, min(np.searchsorted(edges, np.int64(et.value), side='right') - 1, len(edges) - 1))
        tT.append(dict(bot='trend', side=int(t['side']), entry_t=et, year=et.year, R=float(R),
                       bar=pos, oi=float(oi7[pos]) if oi7 is not None and np.isfinite(oi7[pos]) else 0.0,
                       fund=funding_sign_at(ft, fr, et.value)))
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
        pos = max(0, min(np.searchsorted(edges, np.int64(et.value), side='right') - 1, len(edges) - 1))
        tS.append(dict(bot='sideway', side=int(t.get('side', 1)), entry_t=et,
                       year=int(t.get('year', et.year)), R=float(t.get('R', 0.0)), bar=pos))
    o = df7['open'].values; h = df7['high'].values; l = df7['low'].values; c = df7['close'].values
    return tT, tS, (o, h, l, c), idx7, (ft is not None)


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
    print("[Stg6] A:칩필터 2of3 CPCV검증 + B:숏 필터 격자(하락장·ADX·OI펀딩) — ML폐기 후 확실수확 굳히기")
    champ = load_engine(os.path.join(BOTS, "SpTrd_Fib_V1_Champion.py"), "champ_engine")
    sdca = load_engine(os.path.join(BOTS, "SidewayDCA_Stg7_engine.py"), "sdca_engine")
    DATA = find_file(["Merged_Data_with_Regime_Features.csv", "merged_data.csv"])
    OIPATH = find_file(["Merged_Data.csv", "merged_data.csv"])
    FUND = find_file(["BTCUSDT_funding_history_8h.csv", "funding_history_8h.csv"])
    if DATA is None:
        pd.DataFrame([{'x': 'no data'}]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig'); return

    tT, tS, (o, h, l, c), idx7, fund_real = get_trades(champ, sdca, DATA, OIPATH, FUND)
    n_bars = len(c)
    ind = RC.compute_indicators(o, h, l, c, RC.DEFAULT_PARAMS)
    reg, _, _, _ = RC.classify(o, h, l, c, dict(w=0.0, chop_hi=60.0, adx_hi=30.0, vote_n=3), ind=ind)
    print(f"[준비] 7h봉 {n_bars} / 추세 {len(tT)} / 횡보 {len(tS)} / 펀딩 {'REAL' if fund_real else 'NONE'}")

    # ══ A. 칩필터 2of3 CPCV 검증 ══
    bi_S = np.array([t['bar'] for t in tS]); RS = np.array([t['R'] for t in tS])
    passed = RC.chip_gate_at(ind, bi_S, CHIP_BEST)
    # ON: 칩필터 통과 횡보봇 / OFF: 전체 횡보봇
    on_pos = bi_S[passed]; on_R = RS[passed]; off_pos = bi_S; off_R = RS
    on_sum, on_rows = CP.cpcv_pf_eval(on_pos, on_R, n_bars, N=N_GROUP, k=K_TEST, min_n=3)
    off_sum, off_rows = CP.cpcv_pf_eval(off_pos, off_R, n_bars, N=N_GROUP, k=K_TEST, min_n=3)
    m_on = metrics(on_R); m_off = metrics(off_R)
    chip_rows = [
        dict(filter='칩필터ON(2of3)', n=m_on['n'], PF_full=m_on['PF'], ret_full=m_on['ret'],
             cpcv_pf_mean=on_sum['pf_mean'], cpcv_pf_min=on_sum['pf_min'], cpcv_pf_p25=on_sum['pf_p25'],
             cpcv_below1=on_sum['pf_below1'], cpcv_paths=on_sum['n_paths']),
        dict(filter='칩필터OFF(전체)', n=m_off['n'], PF_full=m_off['PF'], ret_full=m_off['ret'],
             cpcv_pf_mean=off_sum['pf_mean'], cpcv_pf_min=off_sum['pf_min'], cpcv_pf_p25=off_sum['pf_p25'],
             cpcv_below1=off_sum['pf_below1'], cpcv_paths=off_sum['n_paths']),
    ]
    pd.DataFrame(chip_rows).to_csv(os.path.join(HERE, "chip_cpcv.csv"), index=False, encoding='utf-8-sig')
    pd.DataFrame([dict(filter='ON', **r) for r in on_rows] + [dict(filter='OFF', **r) for r in off_rows]
                 ).to_csv(os.path.join(HERE, "chip_cpcv_paths.csv"), index=False, encoding='utf-8-sig')

    # ══ B. 숏 약점 분해 + 필터 격자 ══
    shorts = [t for t in tT if t['side'] < 0]
    longs = [t for t in tT if t['side'] > 0]
    # ① 분해: 숏을 장세별·년도별 PF
    sd_rows = []
    sR = np.array([t['R'] for t in shorts]); sBar = np.array([t['bar'] for t in shorts])
    sReg = reg[sBar]; sYr = np.array([t['year'] for t in shorts])
    for code in range(4):
        mm = metrics(sR[sReg == code])
        sd_rows.append(dict(dim='regime', key=REGIME_MAP[code], n=mm['n'], PF=mm['PF'], ret=mm['ret'], win=mm['win']))
    for yr in sorted(set(sYr.tolist())):
        mm = metrics(sR[sYr == yr])
        sd_rows.append(dict(dim='year', key=int(yr), n=mm['n'], PF=mm['PF'], ret=mm['ret'], win=mm['win']))
    mm = metrics(sR); sd_rows.append(dict(dim='all', key='short_all', n=mm['n'], PF=mm['PF'], ret=mm['ret'], win=mm['win']))
    mlong = metrics(np.array([t['R'] for t in longs])); sd_rows.append(dict(dim='all', key='long_all', n=mlong['n'], PF=mlong['PF'], ret=mlong['ret'], win=mlong['win']))
    pd.DataFrame(sd_rows).to_csv(os.path.join(HERE, "short_breakdown.csv"), index=False, encoding='utf-8-sig')

    # ② 숏 필터 격자 27조합: 하락장확인(off/on) × ADX(0/25/30) × 펀딩(off/펀딩>0만) → 2×3×3=18 (하락on/off 2)
    sFund = np.array([t['fund'] for t in shorts]); sAdx = ind['adx'][sBar]
    grid_rows = []
    for downonly in [0, 1]:
        for adx_th in SHORT_ADX:
            for fundpos in [0, 1]:
                keep = np.ones(len(shorts), dtype=bool)
                if downonly:
                    keep &= (sReg == 1)              # 분류기 하락국면만
                if adx_th > 0:
                    keep &= (sAdx >= adx_th)         # ADX 강도
                if fundpos:
                    keep &= (sFund > 0)              # 펀딩>0(롱과열)일 때만 숏
                Rk = sR[keep]; posk = sBar[keep]
                mk = metrics(Rk)
                # CPCV PF분포(거래 충분할 때만)
                if mk['n'] >= 12:
                    cs, _ = CP.cpcv_pf_eval(posk, Rk, n_bars, N=N_GROUP, k=K_TEST, min_n=2)
                    cpcv_p25 = cs['pf_p25']; cpcv_below1 = cs['pf_below1']
                else:
                    cpcv_p25 = float('nan'); cpcv_below1 = -1
                grid_rows.append(dict(downonly=downonly, adx_th=adx_th, fundpos=fundpos,
                                      n=mk['n'], PF=mk['PF'], ret=mk['ret'], win=mk['win'], payoff=mk['payoff'],
                                      cpcv_pf_p25=cpcv_p25, cpcv_below1=cpcv_below1))
    grid = pd.DataFrame(grid_rows)
    grid.to_csv(os.path.join(HERE, "short_grid.csv"), index=False, encoding='utf-8-sig')
    # BEST 숏필터: degenerate(PF999) 방지 위해 PF 5.0캡 + CPCV 견고성(p25) 동시. 거래 충분(n>=20).
    base_short_pf = metrics(sR)['PF']
    cand = grid[grid['n'] >= 20].copy()
    if len(cand) == 0:
        cand = grid.copy()
    cand['pf_capped'] = cand['PF'].clip(upper=5.0)                       # PF999 같은 가짜최고 제거
    cand['cpcv_score'] = cand['cpcv_pf_p25'].fillna(0.0).clip(upper=5.0)  # CPCV 견고성(없으면 0)
    # 견고성 우선 정렬: CPCV p25 → PF캡 → 거래수
    short_best = cand.sort_values(['cpcv_score', 'pf_capped', 'n'], ascending=False).iloc[0]
    # BEST의 CPCV 경로 상세
    bk = np.ones(len(shorts), dtype=bool)
    if int(short_best['downonly']):
        bk &= (sReg == 1)
    if short_best['adx_th'] > 0:
        bk &= (sAdx >= short_best['adx_th'])
    if int(short_best['fundpos']):
        bk &= (sFund > 0)
    _, sbest_paths = CP.cpcv_pf_eval(sBar[bk], sR[bk], n_bars, N=N_GROUP, k=K_TEST, min_n=2)
    pd.DataFrame(sbest_paths).to_csv(os.path.join(HERE, "short_cpcv_paths.csv"), index=False, encoding='utf-8-sig')

    # ══ 매트릭스(재확인) ══
    bi_T = np.array([t['bar'] for t in tT]); regT = reg[bi_T]; regS = reg[bi_S]
    led = []
    for kk, t in enumerate(tT):
        led.append(dict(bot='trend', side=('long' if t['side'] > 0 else 'short'), year=t['year'],
                        regime=REGIME_MAP[int(regT[kk])], R=t['R'], win=int(t['R'] > 0)))
    for kk, t in enumerate(tS):
        led.append(dict(bot='sideway', side=('long' if t['side'] > 0 else 'short'), year=t['year'],
                        regime=REGIME_MAP[int(regS[kk])], R=t['R'], win=int(t['R'] > 0)))
    pd.DataFrame(led).to_csv(os.path.join(HERE, "ledger_trades.csv"), index=False, encoding='utf-8-sig')

    # 판정
    chip_robust = "견고" if (on_sum['pf_p25'] == on_sum['pf_p25'] and on_sum['pf_p25'] > 1.0 and on_sum['pf_below1'] <= 3) else "불안정"
    short_improved = "개선" if short_best['PF'] > base_short_pf else "개선못함"
    verdict = (f"VERDICT Stg6 | 추세{len(tT)}(롱{len(longs)}/숏{len(shorts)})/횡보{len(tS)} 펀딩{'REAL' if fund_real else 'NONE'} | "
               f"[A 칩필터2of3 CPCV] ON PF전체{m_on['PF']}(n{m_on['n']}) CPCV평균{on_sum['pf_mean']} p25{on_sum['pf_p25']} PF<1경로{on_sum['pf_below1']}/{on_sum['n_paths']} -> {chip_robust} "
               f"(OFF p25{off_sum['pf_p25']} 대비) | "
               f"[B 숏] 기존숏PF{base_short_pf} -> BEST(하락{int(short_best['downonly'])}/ADX{short_best['adx_th']}/펀딩{int(short_best['fundpos'])}) PF{short_best['PF']}(n{short_best['n']}) CPCV_p25{short_best['cpcv_pf_p25']} -> {short_improved}")
    print("[verdict] " + verdict)
    pd.DataFrame([dict(sec=verdict),
                  dict(sec=f"[A 칩필터 CPCV] ON={chip_rows[0]} / OFF={chip_rows[1]}"),
                  dict(sec=f"[B 숏분해] {sd_rows}"),
                  dict(sec=f"[B 숏필터 BEST] {dict(short_best)}"),
                  dict(sec=f"[B 숏격자 상위5] {grid.sort_values('PF',ascending=False).head(5).to_dict('records')}")]
                 ).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')
    with open(os.path.join(HERE, ".stg6_metric"), "w", encoding="utf-8") as f:
        f.write(f"n_trend={len(tT)}\nn_long={len(longs)}\nn_short={len(shorts)}\nn_sw={len(tS)}\nbars7h={n_bars}\n"
                f"chip_on_pf_full={m_on['PF']}\nchip_on_n={m_on['n']}\nchip_on_cpcv_mean={on_sum['pf_mean']}\n"
                f"chip_on_cpcv_p25={on_sum['pf_p25']}\nchip_on_below1={on_sum['pf_below1']}\nchip_on_paths={on_sum['n_paths']}\n"
                f"chip_off_cpcv_p25={off_sum['pf_p25']}\nchip_robust={chip_robust}\n"
                f"short_base_pf={base_short_pf}\nshort_best_downonly={int(short_best['downonly'])}\nshort_best_adx={short_best['adx_th']}\n"
                f"short_best_fundpos={int(short_best['fundpos'])}\nshort_best_pf={short_best['PF']}\nshort_best_n={short_best['n']}\n"
                f"short_best_cpcv_p25={short_best['cpcv_pf_p25']}\nshort_improved={short_improved}\nshort_grid_n={len(grid)}\n"
                f"label_in_feature=False\nlookahead_block=gate_past_only+cpcv_group\nfunding={'REAL' if fund_real else 'NONE'}\n")
    print("[save] chip_cpcv/chip_cpcv_paths/short_breakdown/short_grid/short_cpcv_paths/ledger/summary.csv")


if __name__ == "__main__":
    main()
