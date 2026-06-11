# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch6_FrameWork_RAUTO_Stg9_WhipsawCooldownCPCV.py
# 코드길이: 약 330줄 | 내부버전: 06Prj_Ch6_Stg9_WhipsawCooldownCPCV_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]  사장님 아이디어=휩쏘 누적 방어기제(쿨다운). 검색확인 표준기법.
#   Stg8 결론: 진입시점엔 휩쏘 못가림. 우회=연속 sl이 K번이면 '지금 휩쏘장' 사후인식 → M봉 진입중단.
#   엔진 무수정(해시). 쿨다운은 거래목록 사후필터링(제외만, 포지션 안건드림). label_smc 입력금지.
#
#   [격자]  K(연속sl 임계)=[2,3,4] × M(쉬는봉)=[3,5,8,13] = 12조합. + 기준(쿨다운 없음).
#   [각 조합 평가]  전체 PF/수익 + 2025 PF/수익 + CPCV 15경로 4년 견고성(p25, PF<1경로) + 제외거래 년도분포.
#   [BEST 판정]  ★2025 과최적 방지: 2025 PF 개선 + 전체수익 유지 + CPCV p25>기준 + 제외가 2025에 집중(딴해 안건드림).
#                Stg8 진입필터는 좋은해 거래까지 잘라 CPCV 죽었음. 쿨다운은 나쁜구간만 발동 → CPCV 통과가 핵심검증.
#
#   [★미래참조 차단]  쿨다운은 '과거 거래결과'로만 발동(미래 안봄). 각 거래 시점에 직전 연속sl만 카운트. CPCV 봉그룹 채점.
#
# [PATH] 실행 D:\ML\verify\06Prj_Ch6_FrameWork_RAUTO_Stg9_WhipsawCooldownCPCV\ . 데이터 상위 D:\ML\verify.
# [OUTPUT] cooldown_grid.csv / cooldown_cpcv_paths.csv / cooldown_excl_byyear.csv / baseline_year.csv /
#          ledger_trades.csv / summary.csv + .stg9_metric
# [In/Out 태그]
#   cooldown: apply_cooldown(In 거래,봉분,K,M/Out keep_idx,제외수,발동수) / cooldown_stats_by_year
#   cpcv: cpcv_pf_eval(In 거래봉,R,총봉/Out PF분포)
#   regime_classifier: compute_indicators / classify
#   엔진(무수정): champ.run_strategy(none)/compute_signals/load_oi_8h/load_bb_8h/load_data/resample_tf/TF_MIN
#                 sdca.load_funding/funding_sum
#   본코드: ns_i64/metrics/get_trend_trades/trade_bar_pos/main
#   변수(동결): K_LIST=[2,3,4] M_LIST=[3,5,8,13] N_GROUP=6 K_TEST=2 COST_RT=0.0014 BAR_MIN=420
# ==============================================================================
import os, sys, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE); BOTS = os.path.join(HERE, "bots")
sys.path.insert(0, HERE)
import regime_classifier as RC
import cpcv as CP
import cooldown as CD

K_LIST = [2, 3, 4]; M_LIST = [3, 5, 8, 13]
N_GROUP = 6; K_TEST = 2; COST_RT = 0.0014; BAR_MIN = 420; TARGET_YEAR = 2025
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


def get_trend_trades(champ, sdca, df7, sig, oi7, bb7, ft, fr, idx7):
    def fpay(side, et, xt):
        if ft is None:
            return 0.0
        fs = sdca.funding_sum(ft, fr, int(pd.Timestamp(et).value), int(pd.Timestamp(xt).value))
        return side * fs if fs is not None else 0.0
    ttr = champ.run_strategy(df7, sig, 0, 'none', 0.8, dz_oi=oi7, gate_mode='none',
                             gate_bb=bb7, fib=(0.3, 0.5, 0.6), split_mode='A', split_n=3)
    edges = ns_i64(idx7); out = []
    for t in ttr:
        R = t['side'] * (t['exit'] - t['entry']) / t['entry'] - COST_RT - fpay(t['side'], t['entry_t'], t['exit_t'])
        et = pd.Timestamp(t['entry_t'])
        pos = max(0, min(np.searchsorted(edges, np.int64(et.value), side='right') - 1, len(edges) - 1))
        out.append(dict(side=int(t['side']), entry_t=et, exit_t=pd.Timestamp(t['exit_t']), year=et.year,
                        R=float(R), reason=t.get('reason', '?'), bars=int(t.get('bars', 0)), bar=pos))
    return out


def main():
    print("[Stg9] 휩쏘 쿨다운(연속sl K번->M봉 진입중단) K×M격자 + CPCV 4년견고성 (사장님 아이디어, 검색확인 표준기법)")
    champ = load_engine(os.path.join(BOTS, "SpTrd_Fib_V1_Champion.py"), "champ_engine")
    sdca = load_engine(os.path.join(BOTS, "SidewayDCA_Stg7_engine.py"), "sdca_engine")
    DATA = find_file(["Merged_Data_with_Regime_Features.csv", "merged_data.csv"])
    OIPATH = find_file(["Merged_Data.csv", "merged_data.csv"])
    FUND = find_file(["BTCUSDT_funding_history_8h.csv", "funding_history_8h.csv"])
    if DATA is None:
        pd.DataFrame([{'x': 'no data'}]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig'); return

    df1m = champ.load_data(DATA); df7 = champ.resample_tf(df1m, champ.TF_MIN); sig = champ.compute_signals(df7)
    idx7 = df7.index; oi7 = champ.load_oi_8h(OIPATH, idx7); bb7 = champ.load_bb_8h(DATA, idx7)
    ft = fr = None
    if FUND:
        try:
            ft, fr = sdca.load_funding(FUND)
        except Exception:
            ft = fr = None
    fund_real = ft is not None
    o = df7['open'].values; h = df7['high'].values; l = df7['low'].values; c = df7['close'].values
    n_bars = len(c)
    trades = get_trend_trades(champ, sdca, df7, sig, oi7, bb7, ft, fr, idx7)
    print(f"[준비] 추세봇 {len(trades)}건 / 7h봉 {n_bars} / 펀딩 {'REAL' if fund_real else 'NONE'}")

    allR = np.array([t['R'] for t in trades]); allpos = np.array([t['bar'] for t in trades])
    yrs = np.array([t['year'] for t in trades])
    is25 = yrs == TARGET_YEAR

    # ── 기준(쿨다운 없음) ──
    base_all = metrics(allR); base_25 = metrics(allR[is25])
    cs_base, _ = CP.cpcv_pf_eval(allpos, allR, n_bars, N=N_GROUP, k=K_TEST, min_n=3)
    # 년도별 기준
    by = []
    for y in sorted(set(yrs.tolist())):
        m = metrics(allR[yrs == y]); by.append(dict(year=int(y), n=m['n'], PF=m['PF'], ret=m['ret'], win=m['win']))
    pd.DataFrame(by).to_csv(os.path.join(HERE, "baseline_year.csv"), index=False, encoding='utf-8-sig')

    # ── 격자: K × M ──
    grid_rows = []; best = None; best_paths = []; excl_rows = []
    for K in K_LIST:
        for M in M_LIST:
            keep, n_exc, n_trig = CD.apply_cooldown(trades, BAR_MIN, K, M)
            if len(keep) == 0:
                continue
            Rk = allR[keep]; posk = allpos[keep]; is25k = is25[keep]
            m_all = metrics(Rk); m_25 = metrics(Rk[is25k])
            cs, paths = CP.cpcv_pf_eval(posk, Rk, n_bars, N=N_GROUP, k=K_TEST, min_n=3)
            yr_exc = CD.cooldown_stats_by_year(trades, keep)
            exc_2025 = yr_exc.get(TARGET_YEAR, 0); exc_other = n_exc - exc_2025
            row = dict(K=K, M=M, n=m_all['n'], PF_all=m_all['PF'], ret_all=m_all['ret'],
                       PF_2025=m_25['PF'], ret_2025=m_25['ret'], n_excluded=n_exc, n_trigger=n_trig,
                       exc_2025=exc_2025, exc_other=exc_other,
                       cpcv_pf_mean=cs['pf_mean'], cpcv_pf_p25=cs['pf_p25'], cpcv_below1=cs['pf_below1'])
            grid_rows.append(row)
            excl_rows.append(dict(K=K, M=M, **{f'y{y}': yr_exc.get(y, 0) for y in sorted(set(yrs.tolist()))}))
    grid = pd.DataFrame(grid_rows)
    grid.to_csv(os.path.join(HERE, "cooldown_grid.csv"), index=False, encoding='utf-8-sig')
    pd.DataFrame(excl_rows).to_csv(os.path.join(HERE, "cooldown_excl_byyear.csv"), index=False, encoding='utf-8-sig')

    # ── BEST: 2025 PF 개선 + 전체수익 유지(기준의 90%+) + CPCV 견고(p25>=기준) + degenerate아님 ──
    improved = "개선"
    cand = grid[(grid['PF_all'] < 900) & (grid['PF_2025'] > base_25['PF']) &
                (grid['ret_all'] >= base_all['ret'] * 0.9) &
                (grid['cpcv_pf_p25'] >= cs_base['pf_p25'])].copy()
    if len(cand) == 0:
        improved = "2025개선+4년견고 동시충족 실패"
        cand = grid[(grid['PF_all'] < 900) & (grid['PF_2025'] > base_25['PF'])].copy()
    if len(cand) == 0:
        improved = "2025 개선조합 없음"; cand = grid.copy()
    # 점수: 2025 PF 개선폭 + CPCV p25 + 전체수익 유지
    cand['score'] = (cand['PF_2025'].clip(upper=5) + cand['cpcv_pf_p25'].fillna(0) +
                     (cand['ret_all'] / max(1.0, base_all['ret'])))
    fbest = cand.sort_values('score', ascending=False).iloc[0]
    bk, _, _ = CD.apply_cooldown(trades, BAR_MIN, int(fbest['K']), int(fbest['M']))
    _, best_paths = CP.cpcv_pf_eval(allpos[bk], allR[bk], n_bars, N=N_GROUP, k=K_TEST, min_n=3)
    pd.DataFrame(best_paths).to_csv(os.path.join(HERE, "cooldown_cpcv_paths.csv"), index=False, encoding='utf-8-sig')

    # ── 원장(BEST 적용 후) ──
    reg, _, _, _ = RC.classify(o, h, l, c, dict(w=0.0, chop_hi=60.0, adx_hi=30.0, vote_n=3))
    keepset = set(bk.tolist())
    led = []
    for i, t in enumerate(trades):
        led.append(dict(side=('long' if t['side'] > 0 else 'short'), year=t['year'],
                        regime=REGIME_MAP[int(reg[t['bar']])], R=t['R'], reason=t['reason'], bars=t['bars'],
                        kept_by_cooldown=int(i in keepset)))
    pd.DataFrame(led).to_csv(os.path.join(HERE, "ledger_trades.csv"), index=False, encoding='utf-8-sig')

    # 판정
    verdict = (f"VERDICT Stg9 휩쏘쿨다운 | 추세봇 {len(trades)}건 펀딩{'REAL' if fund_real else 'NONE'} | "
               f"[기준]전체PF{base_all['PF']}(수익{base_all['ret']}) 2025PF{base_25['PF']}(수익{base_25['ret']}) CPCV_p25{cs_base['pf_p25']} | "
               f"[BEST]K{int(fbest['K'])}/M{int(fbest['M'])} -> 전체PF{fbest['PF_all']}(수익{fbest['ret_all']}) 2025PF{fbest['PF_2025']}(수익{fbest['ret_2025']}) "
               f"CPCV_p25{fbest['cpcv_pf_p25']} PF<1경로{fbest['cpcv_below1']} | 제외 2025 {int(fbest['exc_2025'])}건/타년 {int(fbest['exc_other'])}건 -> {improved}")
    print("[verdict] " + verdict)
    pd.DataFrame([dict(sec=verdict),
                  dict(sec=f"[기준 년도별] {by}"),
                  dict(sec=f"[쿨다운 격자] {grid_rows}"),
                  dict(sec=f"[BEST 제외 년도분포] {[r for r in excl_rows if r['K']==int(fbest['K']) and r['M']==int(fbest['M'])]}")]
                 ).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')
    with open(os.path.join(HERE, ".stg9_metric"), "w", encoding="utf-8") as f:
        f.write(f"bars7h={n_bars}\nn_trend={len(trades)}\nbase_pf_all={base_all['PF']}\nbase_ret_all={base_all['ret']}\n"
                f"base_pf_2025={base_25['PF']}\nbase_ret_2025={base_25['ret']}\nbase_cpcv_p25={cs_base['pf_p25']}\n"
                f"base_cpcv_below1={cs_base['pf_below1']}\n"
                f"best_K={int(fbest['K'])}\nbest_M={int(fbest['M'])}\nbest_pf_all={fbest['PF_all']}\nbest_ret_all={fbest['ret_all']}\n"
                f"best_pf_2025={fbest['PF_2025']}\nbest_ret_2025={fbest['ret_2025']}\nbest_cpcv_p25={fbest['cpcv_pf_p25']}\n"
                f"best_cpcv_below1={fbest['cpcv_below1']}\nbest_exc_2025={int(fbest['exc_2025'])}\nbest_exc_other={int(fbest['exc_other'])}\n"
                f"best_n_trigger={int(fbest['n_trigger'])}\nimproved={improved}\ngrid_n={len(grid)}\n"
                f"label_in_feature=False\nlookahead_block=cooldown_pastonly+cpcv_group\nfunding={'REAL' if fund_real else 'NONE'}\n")
    print("[save] cooldown_grid/cooldown_cpcv_paths/cooldown_excl_byyear/baseline_year/ledger/summary.csv")


if __name__ == "__main__":
    main()
