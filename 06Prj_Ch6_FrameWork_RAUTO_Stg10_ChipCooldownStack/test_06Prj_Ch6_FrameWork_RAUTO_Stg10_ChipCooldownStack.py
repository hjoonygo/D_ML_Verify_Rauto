# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch6_FrameWork_RAUTO_Stg10_ChipCooldownStack.py
# 코드길이: 약 300줄 | 내부버전: 06Prj_Ch6_Stg10_ChipCooldownStack_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]  사장님 확정(가): Stg15 칩필터 추세봇(+4.81%)에 Ch6 쿨다운을 얹어 합산 검증.
#   질문: 쿨다운이 칩필터에 '보태지나'(D>B) 아니면 '같은 거래 중복'이라 그대로(D≈B)? 추정금지, 코드로.
#   엔진 무수정(해시 Ch6동일=Stg15동일 7f9192e3/dfdfac43). er게이트는 Stg15에 이미 내장(gate_er=0.45).
#
#   [4종 비교]  A 기본(none칩·쿨다운off) / B 칩필터만(=Stg15 +4.81%) / C 쿨다운만 / D 칩필터+쿨다운(합산)
#     칩필터 = CHOP>65 AND ER<0.35 AND ADX<25 이면 진입스킵(R×0). 쿨다운 = 연속 sl K4번->M8봉 진입중단.
#     ★합치는 순서: ①칩필터로 칩거래 먼저 스킵 → ②남은거래에 쿨다운(연속sl) 적용. 운용흐름과 일치.
#   [평가축]  각 종 전체 PF/수익 + 2025 PF/수익 + CPCV 15경로 견고성(p25, PF<1경로).
#   [판정]  D의 2025수익 > B면 쿨다운이 추가이득. D≈B면 중복. D<B면 충돌(과제거).
#
#   [★미래참조 차단]  칩 정의는 진입봉 과거지표만. 쿨다운은 과거 거래결과만. CPCV purge+embargo. label_smc 입력금지.
#
# [PATH] 실행 D:\ML\verify\06Prj_Ch6_FrameWork_RAUTO_Stg10_ChipCooldownStack\ . 데이터 상위 D:\ML\verify.
# [OUTPUT] stack_compare.csv / stack_cpcv_paths.csv / stack_by_year.csv / ledger_trades.csv / summary.csv + .stg10_metric
# [In/Out 태그]
#   cooldown: apply_cooldown(In 거래,봉분,K,M/Out keep,제외,발동)
#   cpcv: cpcv_pf_eval(In 거래봉,R,총봉/Out PF분포)
#   regime_classifier: compute_indicators(In OHLC/Out chop·er·adx)
#   엔진(무수정): champ.run_strategy(gate_er=0.45=Stg15동일)/compute_signals/load_oi_8h/load_bb_8h/load_data/resample_tf/TF_MIN
#                 sdca.load_funding/funding_sum
#   본코드: ns_i64/metrics/get_trend_trades(chip플래그 부착)/apply_chip_skip/main
#   변수(동결): CHOP_HI=65 ER_LO=0.35 ADX_LO=25 COOL_K=4 COOL_M=8 N_GROUP=6 K_TEST=2 COST_RT=0.0014 BAR_MIN=420
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

CHOP_HI = 65.0; ER_LO = 0.35; ADX_LO = 25.0       # Stg15 best 칩필터
COOL_K = 4; COOL_M = 8                              # Ch6 Stg9 best 쿨다운
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
        return dict(n=0, PF=0.0, ret=0.0, win=0.0)
    gp = float(R[R > 0].sum()); gl = float(-R[R < 0].sum())
    pf = round(gp / gl, 3) if gl > 0 else (999.0 if gp > 0 else 0.0)
    return dict(n=n, PF=pf, ret=round(R.sum() * 100, 2), win=round(100 * (R > 0).mean(), 1))


def get_trend_trades(champ, sdca, df7, sig, oi7, bb7, ft, fr, ind, idx7):
    # 추세봇 거래(Stg15와 동일: gate_er=0.45) + 진입봉 chop/er/adx 부착 + chip 플래그.
    def fpay(side, et, xt):
        if ft is None:
            return 0.0
        fs = sdca.funding_sum(ft, fr, int(pd.Timestamp(et).value), int(pd.Timestamp(xt).value))
        return side * fs if fs is not None else 0.0
    ttr = champ.run_strategy(df7, sig, 0, 'none', 0.8, gate_mode='er', gate_er=0.45,
                             dz_oi=oi7, gate_bb=bb7, fib=(0.3, 0.5, 0.6), split_mode='A', split_n=3)
    edges = ns_i64(idx7); out = []
    for t in ttr:
        R = t['side'] * (t['exit'] - t['entry']) / t['entry'] - COST_RT - fpay(t['side'], t['entry_t'], t['exit_t'])
        et = pd.Timestamp(t['entry_t'])
        pos = max(0, min(np.searchsorted(edges, np.int64(et.value), side='right') - 1, len(edges) - 1))
        chop = ind['chop'][pos]; er = ind['er'][pos]; adx = ind['adx'][pos]
        is_chip = bool(np.isfinite(chop) and np.isfinite(er) and np.isfinite(adx) and
                       chop > CHOP_HI and er < ER_LO and adx < ADX_LO)
        out.append(dict(side=int(t['side']), entry_t=et, exit_t=pd.Timestamp(t['exit_t']), year=et.year,
                        R=float(R), reason=t.get('reason', '?'), bars=int(t.get('bars', 0)), bar=pos, is_chip=is_chip))
    return out


def variant_eval(trades, use_chip, use_cool, n_bars):
    # use_chip: 칩거래 제외. use_cool: 남은거래에 쿨다운. -> (지표dict, 2025지표, CPCV, keep된 거래)
    # ①칩필터: 칩이면 제외(R×0=실질 거래안함)
    if use_chip:
        kept = [t for t in trades if not t['is_chip']]
    else:
        kept = list(trades)
    # ②쿨다운: 남은 거래에 연속 sl 적용
    if use_cool:
        keep_idx, n_exc, n_trig = CD.apply_cooldown(kept, BAR_MIN, COOL_K, COOL_M)
        kept = [kept[i] for i in keep_idx]
    else:
        n_exc = 0; n_trig = 0
    R = np.array([t['R'] for t in kept]); pos = np.array([t['bar'] for t in kept])
    yrs = np.array([t['year'] for t in kept])
    m_all = metrics(R); m_25 = metrics(R[yrs == TARGET_YEAR])
    cs, paths = CP.cpcv_pf_eval(pos, R, n_bars, N=N_GROUP, k=K_TEST, min_n=3) if len(R) >= 30 else ({'pf_mean': float('nan'), 'pf_p25': float('nan'), 'pf_below1': -1, 'n_paths': 0}, [])
    return m_all, m_25, cs, kept, n_exc, n_trig, paths


def main():
    print("[Stg10] Stg15 칩필터(+4.81%) + Ch6 쿨다운 합산검증: 쿨다운이 보태지나(D>B) 중복인가(D≈B)")
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
    trades = get_trend_trades(champ, sdca, df7, sig, oi7, bb7, ft, fr, ind, idx7)
    n_chip = sum(1 for t in trades if t['is_chip'])
    n_chip25 = sum(1 for t in trades if t['is_chip'] and t['year'] == TARGET_YEAR)
    print(f"[준비] 추세봇 {len(trades)}건 / 칩거래 {n_chip}건(2025중 {n_chip25}) / 펀딩 {'REAL' if fund_real else 'NONE'}")

    # 4종: A 기본 / B 칩필터 / C 쿨다운 / D 합산
    variants = [('A_기본', False, False), ('B_칩필터(Stg15)', True, False),
                ('C_쿨다운만', False, True), ('D_칩필터+쿨다운', True, True)]
    rows = []; paths_all = []; best_keep = None
    for name, uc, ucl in variants:
        m_all, m_25, cs, kept, n_exc, n_trig, paths = variant_eval(trades, uc, ucl, n_bars)
        rows.append(dict(variant=name, n=m_all['n'], PF_all=m_all['PF'], ret_all=m_all['ret'], win=m_all['win'],
                         PF_2025=m_25['PF'], ret_2025=m_25['ret'], n_2025=m_25['n'],
                         cpcv_pf_mean=cs['pf_mean'], cpcv_pf_p25=cs['pf_p25'], cpcv_below1=cs['pf_below1'],
                         n_excluded=n_exc, n_trigger=n_trig))
        for p in paths:
            paths_all.append(dict(variant=name, **p))
        if name == 'D_칩필터+쿨다운':
            best_keep = kept
    comp = pd.DataFrame(rows)
    comp.to_csv(os.path.join(HERE, "stack_compare.csv"), index=False, encoding='utf-8-sig')
    pd.DataFrame(paths_all).to_csv(os.path.join(HERE, "stack_cpcv_paths.csv"), index=False, encoding='utf-8-sig')

    # 년도별(4종)
    by_rows = []
    for name, uc, ucl in variants:
        if uc:
            kept0 = [t for t in trades if not t['is_chip']]
        else:
            kept0 = list(trades)
        if ucl:
            ki, _, _ = CD.apply_cooldown(kept0, BAR_MIN, COOL_K, COOL_M); kept0 = [kept0[i] for i in ki]
        for y in sorted(set(t['year'] for t in trades)):
            R = np.array([t['R'] for t in kept0 if t['year'] == y])
            m = metrics(R)
            by_rows.append(dict(variant=name, year=int(y), n=m['n'], PF=m['PF'], ret=m['ret']))
    pd.DataFrame(by_rows).to_csv(os.path.join(HERE, "stack_by_year.csv"), index=False, encoding='utf-8-sig')

    # 원장(D 적용 후)
    reg, _, _, _ = RC.classify(o, h, l, c, dict(w=0.0, chop_hi=60.0, adx_hi=30.0, vote_n=3), ind=ind)
    led = []
    for t in (best_keep or []):
        led.append(dict(side=('long' if t['side'] > 0 else 'short'), year=t['year'],
                        regime=REGIME_MAP[int(reg[t['bar']])], R=t['R'], reason=t['reason'], is_chip=int(t['is_chip'])))
    pd.DataFrame(led).to_csv(os.path.join(HERE, "ledger_trades.csv"), index=False, encoding='utf-8-sig')

    # 판정
    B = next(r for r in rows if r['variant'] == 'B_칩필터(Stg15)')
    D = next(r for r in rows if r['variant'] == 'D_칩필터+쿨다운')
    A = next(r for r in rows if r['variant'] == 'A_기본')
    if D['ret_2025'] > B['ret_2025'] + 0.5:
        verdict_stack = "쿨다운 추가이득(D>B)"
    elif D['ret_2025'] < B['ret_2025'] - 0.5:
        verdict_stack = "충돌·과제거(D<B)"
    else:
        verdict_stack = "중복(D≈B, 쿨다운이 칩필터와 같은거래 제거)"
    verdict = (f"VERDICT Stg10 칩+쿨다운 합산 | 추세봇 {len(trades)}건(칩 {n_chip}/2025중 {n_chip25}) 펀딩{'REAL' if fund_real else 'NONE'} | "
               f"[A기본] 2025 {A['ret_2025']}%(PF{A['PF_2025']}) | [B칩필터] 2025 {B['ret_2025']}%(PF{B['PF_2025']}) | "
               f"[D합산] 2025 {D['ret_2025']}%(PF{D['PF_2025']}) 전체PF{D['PF_all']}(수익{D['ret_all']}) CPCV_p25{D['cpcv_pf_p25']} | -> {verdict_stack}")
    print("[verdict] " + verdict)
    pd.DataFrame([dict(sec=verdict), dict(sec=f"[4종 비교] {rows}")]
                 ).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')
    with open(os.path.join(HERE, ".stg10_metric"), "w", encoding="utf-8") as f:
        f.write(f"bars7h={n_bars}\nn_trend={len(trades)}\nn_chip={n_chip}\nn_chip_2025={n_chip25}\n")
        for r in rows:
            tag = r['variant'].split('_')[0]
            f.write(f"{tag}_pf_all={r['PF_all']}\n{tag}_ret_all={r['ret_all']}\n{tag}_pf_2025={r['PF_2025']}\n"
                    f"{tag}_ret_2025={r['ret_2025']}\n{tag}_cpcv_p25={r['cpcv_pf_p25']}\n{tag}_cpcv_below1={r['cpcv_below1']}\n")
        f.write(f"verdict_stack={verdict_stack}\nlabel_in_feature=False\n"
                f"lookahead_block=chip_past+cooldown_past+cpcv_group\nfunding={'REAL' if fund_real else 'NONE'}\n")
    print("[save] stack_compare/stack_cpcv_paths/stack_by_year/ledger/summary.csv")


if __name__ == "__main__":
    main()
