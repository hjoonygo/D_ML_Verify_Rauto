# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch6_FrameWork_RAUTO_Stg13_TrendStackFinalize.py
# 코드길이: 약 290줄 | 내부버전: 06Prj_Ch6_Stg13_TrendStackFinalize_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]  사장님 확정(가): RAUTO에 넣을 최종 추세봇 스택 확정.
#   Stg12 발견 = 복리기준 칩필터 단독(B)이 base(A)보다 손해(2024 좋은거래까지 잘라서). 그럼 칩필터 빼야?
#   ★Stg12엔 '쿨다운만(③)'이 없었다. 이번에 4종을 복리+CPCV로 동시비교해 확정한다.
#   엔진 무수정(해시 7f9192e3/dfdfac43). label_smc 입력금지. 비용0.14%+실펀딩.
#
#   [4종 — 전부 $10,000 복리]
#     ① base       : er게이트(gate_er=0.45)만
#     ② +chip      : ① + 칩필터(CHOP>65·ER<0.35·ADX<25 진입스킵)
#     ③ +cool      : ① + 쿨다운(연속sl K4->M8)            ★Stg12에 없던 핵심
#     ④ +chip+cool : ① + 칩필터 + 쿨다운 (현재 스택)
#
#   [판정]  복리 최종잔고 + CPCV p25(견고성) + MDD. ③>④면 칩필터 제거 확정. ③<④면 시너지로 유지.
#   [★최적화]  엔진 1회 호출(run_strategy) + 지표 1회(compute_indicators). 4종은 거래목록 재사용(사후필터).
#   [★미래참조 차단]  칩·쿨다운 과거기반. CPCV purge+embargo. label 입력금지.
#
# [PATH] 실행 D:\ML\verify\06Prj_Ch6_FrameWork_RAUTO_Stg13_TrendStackFinalize\ . 데이터 상위 D:\ML\verify.
# [OUTPUT] D:\ML\verify\00WorkHstr\ 로 분석txt·INDEX. 결과 csv는 하위폴더.
#   stack4_compare.csv / stack4_cpcv_paths.csv / stack4_by_year.csv / ledger_trades.csv / summary.csv + .stg13_metric
# [In/Out 태그]
#   regime_classifier: compute_indicators(In OHLC/Out chop·er·adx)
#   cooldown: apply_cooldown(In 거래,봉분,K,M/Out keep,제외,발동)
#   cpcv: cpcv_pf_eval(In 거래봉,R,총봉/Out PF분포)
#   엔진(무수정): champ.run_strategy(gate_er=0.45)/compute_signals/load_oi_8h/load_bb_8h/load_data/resample_tf/TF_MIN
#                 sdca.load_funding/funding_sum
#   본코드: ns_i64/compound_end/mdd_of/metrics/build_raw/eval_variant/main
#   변수(동결): START=10000 CHOP_HI=65 ER_LO=0.35 ADX_LO=25 COOL_K=4 COOL_M=8 N_GROUP=6 K_TEST=2 COST_RT=0.0014 BAR_MIN=420
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

START = 10000.0
CHOP_HI = 65.0; ER_LO = 0.35; ADX_LO = 25.0; COOL_K = 4; COOL_M = 8
N_GROUP = 6; K_TEST = 2; COST_RT = 0.0014; BAR_MIN = 420; TARGET_YEAR = 2025


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


def compound_end(trades, start=START):
    if not trades:
        return start, 0.0, []
    s = sorted(trades, key=lambda t: pd.Timestamp(t['exit_t']).value)
    cap = start; curve = []
    for t in s:
        cap *= (1.0 + t['R']); curve.append(cap)
    return cap, round((cap / start - 1) * 100, 2), curve


def mdd_of(curve, start=START):
    peak = start; mdd = 0.0
    for cap in curve:
        peak = max(peak, cap); mdd = min(mdd, (cap - peak) / peak)
    return round(mdd * 100, 2)


def metrics_pf(trades):
    R = np.array([t['R'] for t in trades], float) if trades else np.array([])
    if len(R) == 0:
        return 0.0, 0.0
    gp = float(R[R > 0].sum()); gl = float(-R[R < 0].sum())
    pf = round(gp / gl, 3) if gl > 0 else (999.0 if gp > 0 else 0.0)
    return pf, round(R.sum() * 100, 2)


def build_raw(champ, sdca, df7, sig, oi7, bb7, ft, fr, ind, idx7):
    def fpay(side, et, xt):
        if ft is None:
            return 0.0
        fs = sdca.funding_sum(ft, fr, int(pd.Timestamp(et).value), int(pd.Timestamp(xt).value))
        return side * fs if fs is not None else 0.0
    ttr = champ.run_strategy(df7, sig, 0, 'none', 0.8, gate_mode='er', gate_er=0.45,
                             dz_oi=oi7, gate_bb=bb7, fib=(0.3, 0.5, 0.6), split_mode='A', split_n=3)
    edges = ns_i64(idx7); raw = []
    for t in ttr:
        R = t['side'] * (t['exit'] - t['entry']) / t['entry'] - COST_RT - fpay(t['side'], t['entry_t'], t['exit_t'])
        et = pd.Timestamp(t['entry_t'])
        pos = max(0, min(np.searchsorted(edges, np.int64(et.value), side='right') - 1, len(edges) - 1))
        chop = ind['chop'][pos]; er = ind['er'][pos]; adx = ind['adx'][pos]
        is_chip = bool(np.isfinite(chop) and chop > CHOP_HI and np.isfinite(er) and er < ER_LO and np.isfinite(adx) and adx < ADX_LO)
        raw.append(dict(side=int(t['side']), entry_t=et, exit_t=pd.Timestamp(t['exit_t']), year=et.year,
                        R=float(R), reason=t.get('reason', '?'), bar=pos, is_chip=is_chip))
    return raw


def eval_variant(raw, use_chip, use_cool, n_bars):
    tr = [t for t in raw if not t['is_chip']] if use_chip else list(raw)
    if use_cool:
        ki, n_exc, n_trig = CD.apply_cooldown(tr, BAR_MIN, COOL_K, COOL_M)
        tr = [tr[i] for i in ki]
    else:
        n_exc = 0; n_trig = 0
    cap, ret, curve = compound_end(tr, START)
    mdd = mdd_of(curve, START)
    pf, _ = metrics_pf(tr)
    pf25, ret25 = metrics_pf([t for t in tr if t['year'] == TARGET_YEAR])
    R = np.array([t['R'] for t in tr]); pos = np.array([t['bar'] for t in tr])
    if len(R) >= 30:
        cs, paths = CP.cpcv_pf_eval(pos, R, n_bars, N=N_GROUP, k=K_TEST, min_n=3)
    else:
        cs = {'pf_mean': float('nan'), 'pf_p25': float('nan'), 'pf_below1': -1}; paths = []
    return dict(n=len(tr), end=round(cap, 0), ret=ret, mdd=mdd, pf=pf, pf_2025=pf25, ret_2025=ret25,
                cpcv_p25=cs['pf_p25'], cpcv_mean=cs['pf_mean'], cpcv_below1=cs['pf_below1'],
                n_excluded=n_exc, n_trigger=n_trig), tr, paths


def main():
    print("[Stg13] 추세봇 스택 4종 복리+CPCV 비교 — RAUTO 최종 추세봇 확정(칩필터 빼야하나?)")
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
    raw = build_raw(champ, sdca, df7, sig, oi7, bb7, ft, fr, ind, idx7)
    print(f"[준비] 추세봇 raw {len(raw)}건(칩 {sum(t['is_chip'] for t in raw)}) / 펀딩 {'REAL' if fund_real else 'NONE'}")

    variants = [('1_base', False, False), ('2_chip', True, False), ('3_cool', False, True), ('4_chip_cool', True, True)]
    rows = []; paths_all = []; kept_map = {}
    for name, uc, ucl in variants:
        m, tr, paths = eval_variant(raw, uc, ucl, n_bars)
        rows.append(dict(variant=name, **m)); kept_map[name] = tr
        for p in paths:
            paths_all.append(dict(variant=name, **p))
    comp = pd.DataFrame(rows)
    comp.to_csv(os.path.join(HERE, "stack4_compare.csv"), index=False, encoding='utf-8-sig')
    pd.DataFrame(paths_all).to_csv(os.path.join(HERE, "stack4_cpcv_paths.csv"), index=False, encoding='utf-8-sig')

    # 연도별 복리
    years = sorted(set(t['year'] for t in raw)); by_rows = []
    for y in years:
        row = {'year': int(y)}
        for name, _, _ in variants:
            rs = [t['R'] for t in kept_map[name] if t['year'] == y]
            row[name] = round((np.prod([1 + r for r in rs]) - 1) * 100, 2) if rs else 0.0
        by_rows.append(row)
    pd.DataFrame(by_rows).to_csv(os.path.join(HERE, "stack4_by_year.csv"), index=False, encoding='utf-8-sig')

    pd.DataFrame([dict(variant=n, year=t['year'], R=t['R'], reason=t['reason']) for n in kept_map for t in kept_map[n]]
                 ).to_csv(os.path.join(HERE, "ledger_trades.csv"), index=False, encoding='utf-8-sig')

    # 판정
    d = {r['variant']: r for r in rows}
    base = d['1_base']; chip = d['2_chip']; cool = d['3_cool']; both = d['4_chip_cool']
    # 복리잔고 1등 + CPCV 견고
    best = max(rows, key=lambda r: (r['end'] if r['end'] < 9e8 else 0, r['cpcv_p25'] if r['cpcv_p25'] == r['cpcv_p25'] else 0))
    if cool['end'] > both['end']:
        chip_verdict = f"칩필터 제거 권장(쿨다운만 ${cool['end']:.0f} > 칩+쿨 ${both['end']:.0f})"
    elif cool['end'] < both['end'] - 100:
        chip_verdict = f"칩필터 유지(시너지: 칩+쿨 ${both['end']:.0f} > 쿨다운만 ${cool['end']:.0f})"
    else:
        chip_verdict = f"칩필터 무의미(쿨${cool['end']:.0f}≈칩+쿨${both['end']:.0f}, 차이 미미)"
    verdict = (f"VERDICT Stg13 추세봇스택확정 | 펀딩{'REAL' if fund_real else 'NONE'} | 전부$10k복리 | "
               f"[①base] ${base['end']:.0f}({base['ret']}% MDD{base['mdd']} p25{base['cpcv_p25']}) | "
               f"[②칩만] ${chip['end']:.0f}({chip['ret']}% p25{chip['cpcv_p25']}) | "
               f"[③쿨만] ${cool['end']:.0f}({cool['ret']}% MDD{cool['mdd']} p25{cool['cpcv_p25']}) | "
               f"[④칩+쿨] ${both['end']:.0f}({both['ret']}% MDD{both['mdd']} p25{both['cpcv_p25']}) | "
               f"BEST {best['variant']} | -> {chip_verdict}")
    print("[verdict] " + verdict)
    pd.DataFrame([dict(sec=verdict), dict(sec=f"[4종] {rows}"), dict(sec=f"[연도별복리] {by_rows}")]
                 ).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')
    with open(os.path.join(HERE, ".stg13_metric"), "w", encoding="utf-8") as f:
        f.write(f"start={START}\nfunding={'REAL' if fund_real else 'NONE'}\nlabel_in_feature=False\n"
                f"lookahead_block=chip_past+cooldown_past+cpcv_group\nn_raw={len(raw)}\n")
        for r in rows:
            t = r['variant']
            f.write(f"{t}_end={r['end']:.0f}\n{t}_ret={r['ret']}\n{t}_mdd={r['mdd']}\n{t}_pf={r['pf']}\n"
                    f"{t}_ret2025={r['ret_2025']}\n{t}_cpcv_p25={r['cpcv_p25']}\n{t}_cpcv_below1={r['cpcv_below1']}\n{t}_n={r['n']}\n")
        f.write(f"best_variant={best['variant']}\nchip_verdict={chip_verdict}\n")
    print("[save] stack4_compare/stack4_cpcv_paths/stack4_by_year/ledger/summary.csv")


if __name__ == "__main__":
    main()
