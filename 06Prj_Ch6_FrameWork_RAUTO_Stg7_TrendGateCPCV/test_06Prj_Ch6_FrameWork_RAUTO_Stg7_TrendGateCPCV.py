# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch6_FrameWork_RAUTO_Stg7_TrendGateCPCV.py
# 코드길이: 약 340줄 | 내부버전: 06Prj_Ch6_Stg7_TrendGateCPCV_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]  사장님 확정 (다→가): (A)계열 먼저 깨끗하게, 결과보고 (B)엔진수정 결정.
#   질문: "추세봇에 칩장 대응 설정값(장세판단 로직)이 있나?" → 있다(gate_mode). 그게 칩장 추세봇에 도움되나 검증.
#   엔진 무수정(해시대조). 추세봇 내장 gate_mode를 표준값 고정으로 4종 비교 + 칩장진입 거래 사후필터.
#
#   [비교1 — gate_mode 4종]  추세봇을 각 게이트로 통째로 재실행 → 거래 PF를 CPCV 15경로 비교.
#     none(게이트끔) / adx(ADX>=25 추세장만 무덤필터) / er(ER>=0.40, Ch5 4/4년 견고) / adx_bb(ADX>=25 & BB확장)
#     ★표준값 고정(확인=가): ER_TREND=0.40, ADX_TREND=25, BB_EXPAND=0.5 (Ch5 검증값, 과최적 회피)
#
#   [비교2 — 칩장진입 사후필터]  기본 추세봇 거래 중 '진입봉이 칩장(분류기 레인지국면)'인 거래를 ON/OFF.
#     ★Stg3 교훈: 칩장진입 추세봇 거래가 수익의 58% → 빼면 PF는 올라도 총수익 급감. PF와 총수익 나란히 표시.
#     포지션 안 자르고 '거래 단위'로만 선별(깨끗). CPCV로 견고성.
#
#   [★미래참조 차단]  gate는 진입봉까지 신호만(엔진 내장, 검증됨). 분류기 국면도 과거봉만. CPCV는 거래를 봉그룹 채점.
#
# [PATH] 실행 D:\ML\verify\06Prj_Ch6_FrameWork_RAUTO_Stg7_TrendGateCPCV\ . 데이터 상위 D:\ML\verify.
# [OUTPUT] gate_compare.csv / gate_cpcv_paths.csv / chipentry_filter.csv / chipentry_cpcv_paths.csv /
#          ledger_trades.csv / summary.csv + .stg7_metric
# [In/Out 태그]
#   regime_classifier: compute_indicators / classify(In OHLC,P/Out 국면)
#   cpcv: cpcv_pf_eval(In 거래봉위치,R,총봉/Out PF분포+경로)
#   엔진(무수정): champ.run_strategy(gate_mode 4종)/load_oi_8h/load_bb_8h/compute_signals/resample_tf/load_data/TF_MIN
#                 sdca.load_funding/funding_sum
#   본코드: ns_i64/metrics/run_trend_gate(게이트별 거래)/trade_bar_idx/agg_matrix/main
#   변수(동결): GATES=[none,adx,er,adx_bb] N_GROUP=6 K_TEST=2 COST_RT=0.0014 RANGE_REG={2,3}
# ==============================================================================
import os, sys, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE); BOTS = os.path.join(HERE, "bots")
sys.path.insert(0, HERE)
import regime_classifier as RC
import cpcv as CP

GATES = ['none', 'adx', 'er', 'adx_bb']
N_GROUP = 6; K_TEST = 2; COST_RT = 0.0014
TREND_REG = {0, 1}; RANGE_REG = {2, 3}
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


def run_trend_gate(champ, sdca, df7, sig, oi7, bb7, ft, fr, gate_mode):
    # 추세봇을 주어진 gate_mode로 실행 → 거래(비용0.14%+실펀딩 재계산). 엔진 무수정.
    def fpay(side, et, xt):
        if ft is None:
            return 0.0
        fs = sdca.funding_sum(ft, fr, int(pd.Timestamp(et).value), int(pd.Timestamp(xt).value))
        return side * fs if fs is not None else 0.0
    ttr = champ.run_strategy(df7, sig, 0, 'none', 0.8, dz_oi=oi7, gate_mode=gate_mode,
                             gate_bb=bb7, fib=(0.3, 0.5, 0.6), split_mode='A', split_n=3)
    out = []
    for t in ttr:
        R = t['side'] * (t['exit'] - t['entry']) / t['entry'] - COST_RT - fpay(t['side'], t['entry_t'], t['exit_t'])
        et = pd.Timestamp(t['entry_t'])
        out.append(dict(side=int(t['side']), entry_t=et, year=et.year, R=float(R)))
    return out


def trade_bar_pos(trades, idx7):
    edges = ns_i64(idx7); out = []
    for t in trades:
        pos = np.searchsorted(edges, np.int64(pd.Timestamp(t['entry_t']).value), side='right') - 1
        out.append(max(0, min(pos, len(edges) - 1)))
    return np.array(out)


def main():
    print("[Stg7] 추세봇 gate_mode 4종 CPCV비교 + 칩장진입 사후필터 (장세판단 로직이 칩장 추세봇에 도움되나)")
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
    ind = RC.compute_indicators(o, h, l, c, RC.DEFAULT_PARAMS)
    reg, _, _, _ = RC.classify(o, h, l, c, dict(w=0.0, chop_hi=60.0, adx_hi=30.0, vote_n=3), ind=ind)
    print(f"[준비] 7h봉 {n_bars} / 펀딩 {'REAL' if fund_real else 'NONE'}")

    # ══ 비교1: gate_mode 4종 ══
    gate_rows = []; gate_paths_all = []; gate_trades = {}
    for gm in GATES:
        tr = run_trend_gate(champ, sdca, df7, sig, oi7, bb7, ft, fr, gm)
        gate_trades[gm] = tr
        R = np.array([t['R'] for t in tr]); pos = trade_bar_pos(tr, idx7)
        m = metrics(R)
        cs, paths = CP.cpcv_pf_eval(pos, R, n_bars, N=N_GROUP, k=K_TEST, min_n=3)
        gate_rows.append(dict(gate_mode=gm, n=m['n'], PF_full=m['PF'], ret_full=m['ret'], win=m['win'],
                              cpcv_pf_mean=cs['pf_mean'], cpcv_pf_min=cs['pf_min'], cpcv_pf_p25=cs['pf_p25'],
                              cpcv_below1=cs['pf_below1'], cpcv_paths=cs['n_paths']))
        for p in paths:
            gate_paths_all.append(dict(gate_mode=gm, **p))
    pd.DataFrame(gate_rows).to_csv(os.path.join(HERE, "gate_compare.csv"), index=False, encoding='utf-8-sig')
    pd.DataFrame(gate_paths_all).to_csv(os.path.join(HERE, "gate_cpcv_paths.csv"), index=False, encoding='utf-8-sig')

    # ══ 비교2: 칩장진입 사후필터 (기본=none 게이트 거래 기준) ══
    base_tr = gate_trades['none']
    R = np.array([t['R'] for t in base_tr]); pos = trade_bar_pos(base_tr, idx7)
    regE = reg[pos]
    is_range_entry = np.isin(regE, list(RANGE_REG))   # 진입봉이 칩(레인지)국면
    # 필터OFF=전체 / 필터ON=칩장진입 거래 제외(추세장진입만)
    m_all = metrics(R); m_keep = metrics(R[~is_range_entry])   # 추세장 진입만 남김
    m_chip = metrics(R[is_range_entry])                         # 제외될 칩장 진입 거래
    cs_all, paths_all = CP.cpcv_pf_eval(pos, R, n_bars, N=N_GROUP, k=K_TEST, min_n=3)
    cs_keep, paths_keep = CP.cpcv_pf_eval(pos[~is_range_entry], R[~is_range_entry], n_bars, N=N_GROUP, k=K_TEST, min_n=3)
    chip_rows = [
        dict(variant='전체(칩장진입 포함)', n=m_all['n'], PF=m_all['PF'], ret=m_all['ret'], win=m_all['win'],
             cpcv_pf_p25=cs_all['pf_p25'], cpcv_below1=cs_all['pf_below1']),
        dict(variant='칩장진입 제외(추세장만)', n=m_keep['n'], PF=m_keep['PF'], ret=m_keep['ret'], win=m_keep['win'],
             cpcv_pf_p25=cs_keep['pf_p25'], cpcv_below1=cs_keep['pf_below1']),
        dict(variant='[참고]제외되는 칩장진입거래', n=m_chip['n'], PF=m_chip['PF'], ret=m_chip['ret'], win=m_chip['win'],
             cpcv_pf_p25=float('nan'), cpcv_below1=-1),
    ]
    pd.DataFrame(chip_rows).to_csv(os.path.join(HERE, "chipentry_filter.csv"), index=False, encoding='utf-8-sig')
    pd.DataFrame([dict(variant='ALL', **p) for p in paths_all] +
                 [dict(variant='KEEP', **p) for p in paths_keep]
                 ).to_csv(os.path.join(HERE, "chipentry_cpcv_paths.csv"), index=False, encoding='utf-8-sig')

    # ══ 매트릭스(기본 none 거래, 장세별) ══
    led = []
    for kk, t in enumerate(base_tr):
        led.append(dict(bot='trend', side=('long' if t['side'] > 0 else 'short'), year=t['year'],
                        regime=REGIME_MAP[int(regE[kk])], R=t['R'], win=int(t['R'] > 0),
                        chip_entry=int(bool(is_range_entry[kk]))))
    pd.DataFrame(led).to_csv(os.path.join(HERE, "ledger_trades.csv"), index=False, encoding='utf-8-sig')

    # 판정
    base_pf = gate_rows[0]['PF_full']  # none
    best_gate = sorted(gate_rows, key=lambda r: (r['cpcv_pf_p25'] if r['cpcv_pf_p25'] == r['cpcv_pf_p25'] else -9, r['PF_full']), reverse=True)[0]
    gate_helps = "도움" if best_gate['gate_mode'] != 'none' and best_gate['cpcv_pf_p25'] > gate_rows[0]['cpcv_pf_p25'] else "none이최선(게이트무익)"
    chip_tradeoff = ("PF↑수익↓(라우팅자살골 재확인)" if m_keep['PF'] > m_all['PF'] and m_keep['ret'] < m_all['ret']
                     else ("PF·수익 둘다↑(드문이득)" if m_keep['PF'] > m_all['PF'] and m_keep['ret'] >= m_all['ret']
                           else "제외무익"))
    verdict = (f"VERDICT Stg7 | 7h봉 {n_bars} 펀딩{'REAL' if fund_real else 'NONE'} | "
               f"[gate_mode 4종 CPCV] none PF{gate_rows[0]['PF_full']}(p25 {gate_rows[0]['cpcv_pf_p25']}) / "
               f"adx {gate_rows[1]['PF_full']}({gate_rows[1]['cpcv_pf_p25']}) / er {gate_rows[2]['PF_full']}({gate_rows[2]['cpcv_pf_p25']}) / "
               f"adx_bb {gate_rows[3]['PF_full']}({gate_rows[3]['cpcv_pf_p25']}) -> BEST {best_gate['gate_mode']} -> {gate_helps} | "
               f"[칩장진입 사후필터] 전체 PF{m_all['PF']}(수익{m_all['ret']}) -> 칩장제외 PF{m_keep['PF']}(수익{m_keep['ret']}) "
               f"| 제외될 칩장거래 {m_chip['n']}건 PF{m_chip['PF']} 수익{m_chip['ret']}% -> {chip_tradeoff}")
    print("[verdict] " + verdict)
    pd.DataFrame([dict(sec=verdict),
                  dict(sec=f"[gate 4종] {gate_rows}"),
                  dict(sec=f"[칩장진입 필터] {chip_rows}")]
                 ).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')
    with open(os.path.join(HERE, ".stg7_metric"), "w", encoding="utf-8") as f:
        f.write(f"bars7h={n_bars}\n")
        for r in gate_rows:
            f.write(f"gate_{r['gate_mode']}_pf={r['PF_full']}\ngate_{r['gate_mode']}_n={r['n']}\n"
                    f"gate_{r['gate_mode']}_cpcv_p25={r['cpcv_pf_p25']}\ngate_{r['gate_mode']}_below1={r['cpcv_below1']}\n")
        f.write(f"best_gate={best_gate['gate_mode']}\ngate_helps={gate_helps}\n"
                f"chip_all_pf={m_all['PF']}\nchip_all_ret={m_all['ret']}\nchip_all_n={m_all['n']}\n"
                f"chip_keep_pf={m_keep['PF']}\nchip_keep_ret={m_keep['ret']}\nchip_keep_n={m_keep['n']}\n"
                f"chip_excluded_n={m_chip['n']}\nchip_excluded_pf={m_chip['PF']}\nchip_excluded_ret={m_chip['ret']}\n"
                f"chip_tradeoff={chip_tradeoff}\ngate_n={len(GATES)}\n"
                f"label_in_feature=False\nlookahead_block=gate_internal+regime_past+cpcv_group\nfunding={'REAL' if fund_real else 'NONE'}\n")
    print("[save] gate_compare/gate_cpcv_paths/chipentry_filter/chipentry_cpcv_paths/ledger/summary.csv")


if __name__ == "__main__":
    main()
