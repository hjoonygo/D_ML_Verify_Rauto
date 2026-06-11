# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch7_stg4_GreedShortGuard.py
# 코드길이: 약 325줄 | 내부버전: 06Prj_Ch7_stg4_GreedShortGuard_v2_best55fixed | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [v2 변경점] BEST 선정을 자동(잔고1등)→ 'greed55_smult0' 고정으로 변경.
#   이유: v1 자동선정이 greed65_smult0(잔고1등)을 뽑아, 원장·분해표가 사장님 수동 챔피언
#         greed55_smult0(CPCV1등·MDD최저)와 불일치(07Prj 작업자 발견). v2는 사장님 결정 케이스로 고정.
#   그 외 로직·엔진·비용(14bp)·격자 전부 v1과 동일(무변경).
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]  사장님 승인(시나리오 A): 공포지수(FNG)가 '탐욕'일 때 숏을 막거나 줄인다.
#   ★왜 탐욕? 원장+FNG 결합분석에서 발견: 숏의 진짜 약점은 극공포가 아니라 '탐욕(55~75)' 구간이다.
#     전 기간 탐욕숏 PF 0.62·R합 -10.3%(상승장에 숏쳐서 추세에 짓밟힘). 극공포숏은 오히려 PF 1.13.
#     검색 정설도 "FNG는 정밀저격용이 아니라 거시필터; 강한 상승장에선 탐욕에 머물며 숏을 짓밟는다"로 일치.
#   ★stg3(극공포 차단)는 2025 특화(과최적화 위험)였음 → stg4는 전 기간 견고한 '탐욕숏 축소'를 검증.
#   ★전날(D-1) FNG 사용 = 미래참조 차단(FNG 일단위 종가 산출).  롱은 무수정(봇 강점 보존).
#
#   [격자]  탐욕 임계 3종(55/60/65) × 숏 처리 3종(완전차단 / 50% / 30%) = 9 + 기준선(FNG미적용) 1 = 10.
#     전부 ④스택(칩+쿨다운)·비용 왕복14bp·실펀딩·복리+CPCV.
#   [★원장 표준출력 — 사장님 반복지적 반영]  최고케이스 거래원장에 거래별
#     entry_t/exit_t/side/R/reason/진입월(ym)/장세(label_smc_8 우선, 없으면 regime_classifier)/FNG 부착.
#     => 결과 CSV로 36개월 월별 × 4장세 × 롱숏별 PF·수익률·손익비·거래수·수익금이 바로 산출됨.
#     ★label_smc_8은 '사후 정답지'라 진입결정엔 안 씀(미래참조 금지). 거래 결과 라벨링에만 사용(안전).
#   [★연산 최적화]  지표·신호·엔진 raw 1회 계산 후 10케이스 공유. 케이스별은 사후필터(탐욕숏 R조정+④스택)만.
#   [★과최적화 방어(stg3 교훈)]  판정에 전 연도(2023~2026) 일관성 포함 — 한 해에만 좋은 케이스 식별.
#
# [PATH] 실행 D:\ML\verify\06Prj_Ch7_stg4_GreedShortGuard\ . 데이터·FNG 상위 D:\ML\verify.
# [OUTPUT] 결과 csv 하위폴더. 분석txt·INDEX는 check.py가 D:\ML\verify\00WorkHstr\로.
#   stg4_greed_grid.csv(10) / stg4_best_ledger.csv(원장) / stg4_by_month.csv(36월) / stg4_by_regime.csv(4장세)
#   stg4_by_year_side.csv(연도×롱숏) / stg4_coverage.csv / summary.csv + .stg4_metric
# [In/Out 태그]
#   fear_greed_loader.map_to_bars(In FNG·7h봉idx / Out 봉별 전날FNG·커버율)
#   load_label_smc(In 데이터·7h봉idx / Out 봉별 장세문자열 or None) — label_smc_8 우선, 폴백 regime_classifier
#   champ.run_strategy(무수정) / regime_classifier / cooldown.apply_cooldown / cpcv.cpcv_pf_eval / sdca.load_funding
#   본코드: ns_i64/find_file/build_raw/apply_greed_guard/apply_4stack/compound_end/mdd_of/metrics/
#           eval_case/make_ledger_breakdowns/main
#   변수(동결): START=10000 GATE_ER=0.45 칩(65·0.35·25) 쿨(K4·M8) COST_RT=0.0014 BAR_MIN=420 N_GROUP6 K_TEST2
#   변수(격자): GREED_TH=[55,60,65] SHORT_MULT=[0.0,0.5,0.3]
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
import fear_greed_loader as FG

START = 10000.0
GATE_ER = 0.45
CHOP_HI = 65.0; ER_LO = 0.35; ADX_LO = 25.0
COOL_K = 4; COOL_M = 8
N_GROUP = 6; K_TEST = 2; COST_RT = 0.0014; BAR_MIN = 420
GREED_TH = [55, 60, 65]          # 탐욕 임계(이 값 이상이면 숏 위험)
SHORT_MULT = [0.0, 0.5, 0.3]     # 탐욕시 숏 수량배수: 0=완전차단 / 0.5 / 0.3
YEARS = [2023, 2024, 2025, 2026]


def load_engine(p, nm):
    s = importlib.util.spec_from_file_location(nm, p); m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m); return m


def ns_i64(dtindex):
    return np.asarray(dtindex.values).astype('datetime64[ns]').astype('int64')


def find_file(c):
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for x in c:
            p = os.path.join(d, x)
            if os.path.exists(p):
                return p
    return None


def load_label_smc(data_path, tf_index):
    # label_smc_8(사후 정답지 4장세)을 7h봉에 매핑. 진입봉 시각의 1분봉 라벨을 asof backward로.
    #  ★사후 분석 전용(진입결정 미사용) → 미래참조 무관. 컬럼 없으면 None 반환(폴백 regime_classifier).
    try:
        head = pd.read_csv(data_path, nrows=1)
        smc_col = None
        for cand in ['label_smc_8', 'label_smc_5', 'label_smc_12']:
            if cand in head.columns:
                smc_col = cand; break
        if smc_col is None:
            return None, None
        df = pd.read_csv(data_path, usecols=['timestamp', smc_col], index_col='timestamp', parse_dates=True)
        if getattr(df.index, 'tz', None) is not None:
            df.index = df.index.tz_localize(None)
        df = df.sort_index()
        # 7h봉 시각에 asof backward (그 시점까지의 최신 라벨)
        s = df[smc_col].reindex(df.index.union(tf_index)).ffill().reindex(tf_index)
        return s.values, smc_col
    except Exception:
        return None, None


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


def metrics(trades):
    # PF, R합%, 승률%, 손익비(평균이익/평균손실)
    R = np.array([t['R'] for t in trades], float) if trades else np.array([])
    if len(R) == 0:
        return dict(n=0, pf=0.0, ret=0.0, win=0.0, ratio=0.0)
    gp = float(R[R > 0].sum()); gl = float(-R[R < 0].sum())
    pf = round(gp / gl, 3) if gl > 0 else (999.0 if gp > 0 else 0.0)
    win = round((R > 0).mean() * 100, 1)
    avgw = R[R > 0].mean() if (R > 0).any() else 0.0
    avgl = -R[R < 0].mean() if (R < 0).any() else 0.0
    ratio = round(avgw / avgl, 2) if avgl > 0 else 0.0
    return dict(n=len(trades), pf=pf, ret=round(R.sum() * 100, 2), win=win, ratio=ratio)


def build_raw(champ, sdca, df7, sig, oi7, bb7, ft, fr, ind, idx7, fng_arr, smc_arr):
    def fpay(side, et, xt):
        if ft is None:
            return 0.0
        fs = sdca.funding_sum(ft, fr, int(pd.Timestamp(et).value), int(pd.Timestamp(xt).value))
        return side * fs if fs is not None else 0.0
    ttr = champ.run_strategy(df7, sig, 0, 'none', 0.8, gate_mode='er', gate_er=GATE_ER,
                             dz_oi=oi7, gate_bb=bb7, fib=(0.3, 0.5, 0.6), split_mode='A', split_n=3)
    edges = ns_i64(idx7); raw = []
    for t in ttr:
        R = t['side'] * (t['exit'] - t['entry']) / t['entry'] - COST_RT - fpay(t['side'], t['entry_t'], t['exit_t'])
        et = pd.Timestamp(t['entry_t'])
        pos = max(0, min(np.searchsorted(edges, np.int64(et.value), side='right') - 1, len(edges) - 1))
        chop = ind['chop'][pos]; er = ind['er'][pos]; adx = ind['adx'][pos]
        is_chip = bool(np.isfinite(chop) and chop > CHOP_HI and np.isfinite(er) and er < ER_LO
                       and np.isfinite(adx) and adx < ADX_LO)
        fng = fng_arr[pos] if pos < len(fng_arr) else np.nan
        # 장세: label_smc_8 우선, 없으면 regime_classifier 번호->이름
        if smc_arr is not None and pos < len(smc_arr):
            rg = smc_arr[pos]
            regime = str(rg) if rg is not None and (isinstance(rg, str) or not (isinstance(rg, float) and np.isnan(rg))) else 'unknown'
        else:
            rnum = ind['regime'][pos] if 'regime' in ind else -1
            regime = RC.REGIME_NAMES.get(int(rnum), 'unknown') if rnum >= 0 else 'unknown'
        raw.append(dict(side=int(t['side']), entry_t=et, exit_t=pd.Timestamp(t['exit_t']), year=et.year,
                        ym=et.strftime('%Y-%m'), R=float(R), reason=t.get('reason', '?'),
                        bar=pos, is_chip=is_chip, fng=float(fng), regime=regime))
    return raw


def apply_greed_guard(raw, greed_th, short_mult):
    # 탐욕(fng>=greed_th)에서 숏 거래의 R에 short_mult를 곱함(0=차단=제거). 롱·NaN은 그대로.
    out = []; n_guarded = 0
    for t in raw:
        if t['side'] == -1 and np.isfinite(t['fng']) and t['fng'] >= greed_th:
            if short_mult == 0.0:
                n_guarded += 1; continue
            t2 = dict(t); t2['R'] = t['R'] * short_mult; n_guarded += 1; out.append(t2)
        else:
            out.append(t)
    return out, n_guarded


def apply_4stack(raw):
    after_chip = [t for t in raw if not t['is_chip']]
    n_chip = len(raw) - len(after_chip)
    keep_idx, n_exc, n_trig = CD.apply_cooldown(after_chip, BAR_MIN, COOL_K, COOL_M)
    kept = [after_chip[i] for i in keep_idx]
    return kept, n_chip, n_exc, n_trig


def eval_case(raw_guarded, n_bars):
    kept, n_chip, n_exc, n_trig = apply_4stack(raw_guarded)
    cap, ret, curve = compound_end(kept, START); mdd = mdd_of(curve, START)
    m = metrics(kept)
    by_year = {}
    for y in YEARS:
        ys = [t for t in kept if t['year'] == y]
        by_year[y] = metrics(ys)['ret']
    m2025 = metrics([t for t in kept if t['year'] == 2025])
    s25 = metrics([t for t in kept if t['year'] == 2025 and t['side'] == -1])
    R = np.array([t['R'] for t in kept]); pos = np.array([t['bar'] for t in kept])
    if len(R) >= 30:
        cs, _ = CP.cpcv_pf_eval(pos, R, n_bars, N=N_GROUP, k=K_TEST, min_n=3); p25 = cs['pf_p25']
    else:
        p25 = float('nan')
    # 전 연도 양(+) 일관성: 4개 연도 모두 플러스인가
    yrs_pos = sum(1 for y in YEARS if by_year[y] > 0)
    return dict(n=len(kept), end=round(cap, 0), ret=ret, mdd=mdd, pf=m['pf'], ratio=m['ratio'], win=m['win'],
                cpcv_p25=p25, ret_2025=m2025['ret'], short2025_pf=s25['pf'], short2025_ret=s25['ret'],
                yr2023=by_year[2023], yr2024=by_year[2024], yr2025=by_year[2025], yr2026=by_year[2026],
                years_positive=yrs_pos), kept


def make_ledger_breakdowns(kept):
    # 원장 + 월별·장세별·연도×롱숏별 분해표 (사장님 표준 요청)
    led = pd.DataFrame([dict(entry_t=str(t['entry_t']), exit_t=str(t['exit_t']), ym=t['ym'],
                             year=t['year'], side=t['side'], R=round(t['R'], 6), reason=t['reason'],
                             regime=t['regime'], fng=round(t['fng'], 1) if np.isfinite(t['fng']) else None)
                        for t in kept])
    # 월별(복리: 그달 거래 R곱)
    by_month = []
    for ym in sorted(set(t['ym'] for t in kept)):
        ms = [t for t in kept if t['ym'] == ym]
        comp = (np.prod([1 + t['R'] for t in ms]) - 1) * 100 if ms else 0.0
        mm = metrics(ms)
        by_month.append(dict(ym=ym, n=mm['n'], pf=mm['pf'], ret_compound=round(comp, 2),
                             ret_sum=mm['ret'], win=mm['win'], ratio=mm['ratio']))
    # 장세별
    by_regime = []
    for rg in sorted(set(t['regime'] for t in kept)):
        rs = [t for t in kept if t['regime'] == rg]
        mm = metrics(rs)
        by_regime.append(dict(regime=rg, n=mm['n'], pf=mm['pf'], ret_sum=mm['ret'],
                              win=mm['win'], ratio=mm['ratio'],
                              ret_per_trade=round(mm['ret'] / mm['n'], 3) if mm['n'] else 0.0))
    # 연도×롱숏
    by_year_side = []
    for y in YEARS:
        for sd, nm in [(1, '롱'), (-1, '숏')]:
            ss = [t for t in kept if t['year'] == y and t['side'] == sd]
            mm = metrics(ss)
            by_year_side.append(dict(year=y, side=nm, n=mm['n'], pf=mm['pf'], ret_sum=mm['ret'],
                                     win=mm['win'], ratio=mm['ratio']))
    return led, pd.DataFrame(by_month), pd.DataFrame(by_regime), pd.DataFrame(by_year_side)


def main():
    print("[Ch7 Stg4] 시나리오A — 탐욕구간 숏가드 (FNG>=임계시 숏 차단/축소). 비용14bp+실펀딩.")
    champ = load_engine(os.path.join(BOTS, "SpTrd_Fib_V1_Champion.py"), "champ")
    sdca = load_engine(os.path.join(BOTS, "SidewayDCA_Stg7_engine.py"), "sdca")
    DATA = find_file(["Merged_Data_with_Regime_Features.csv", "merged_data.csv"])
    OIPATH = find_file(["Merged_Data.csv", "merged_data.csv"])
    FUND = find_file(["BTCUSDT_funding_history_8h.csv", "funding_history_8h.csv"])
    FNG = find_file(["Fear_Greed_Index_Clean.csv", "Fear_Greed_Index_2018to20260602.csv",
                     "Fear_Greed_Index_4Years.csv", "Fear_Greed_Index.csv"])
    if DATA is None or FNG is None:
        pd.DataFrame([{'x': f'missing DATA={DATA} FNG={FNG}'}]).to_csv(os.path.join(HERE, "summary.csv"),
                                                                       index=False, encoding='utf-8-sig')
        print(f"[ERR] 데이터없음 DATA={DATA} FNG={FNG}"); return

    df1m = champ.load_data(DATA); df7 = champ.resample_tf(df1m, champ.TF_MIN); sig = champ.compute_signals(df7)
    idx7 = df7.index; oi7 = champ.load_oi_8h(OIPATH, idx7); bb7 = champ.load_bb_8h(DATA, idx7)
    ft = fr = None
    if FUND:
        try:
            ft, fr = sdca.load_funding(FUND)
        except Exception:
            ft = fr = None
    fund_real = ft is not None
    fng_arr, fng_cov = FG.map_to_bars(FNG, idx7)
    smc_arr, smc_col = load_label_smc(DATA, idx7)
    o = df7['open'].values; h = df7['high'].values; l = df7['low'].values; c = df7['close'].values
    n_bars = len(c); ind = RC.compute_indicators(o, h, l, c, RC.DEFAULT_PARAMS)
    # regime 폴백용: compute_indicators에 regime 없으면 classify로 생성
    if 'regime' not in ind:
        try:
            reg, _ds, _tv, _ind = RC.classify(o, h, l, c, RC.DEFAULT_PARAMS, ind=ind)
            ind['regime'] = reg
        except Exception:
            ind['regime'] = np.full(n_bars, -1)
    raw0 = build_raw(champ, sdca, df7, sig, oi7, bb7, ft, fr, ind, idx7, fng_arr, smc_arr)
    print(f"[준비] raw {len(raw0)}건 / 펀딩{'REAL' if fund_real else 'NONE'} / FNG커버{fng_cov*100:.1f}% / 장세출처 {smc_col or 'regime_classifier'}")
    pd.DataFrame([dict(fng_coverage_pct=round(fng_cov*100, 2), n_bars=n_bars, n_raw=len(raw0),
                       regime_source=smc_col or 'regime_classifier',
                       fng_file=os.path.basename(FNG))]).to_csv(os.path.join(HERE, "stg4_coverage.csv"),
                                                                index=False, encoding='utf-8-sig')

    rows = []
    base_m, base_kept = eval_case(list(raw0), n_bars)
    rows.append(dict(case='0_base_noFNG', greed_th='-', short_mult='-', n_guarded=0, **base_m))
    case_kept = {'0_base_noFNG': base_kept}
    for th in GREED_TH:
        for sm in SHORT_MULT:
            guarded, ng = apply_greed_guard(raw0, th, sm)
            m, kept = eval_case(guarded, n_bars)
            cname = f'greed{th}_smult{int(sm*100)}'
            rows.append(dict(case=cname, greed_th=th, short_mult=sm, n_guarded=ng, **m))
            case_kept[cname] = kept

    grid = pd.DataFrame(rows)
    grid.to_csv(os.path.join(HERE, "stg4_greed_grid.csv"), index=False, encoding='utf-8-sig')

    # ★BEST = 수동 챔피언 'greed55_smult0' 고정 (사장님 결정 케이스).
    #   근거: 잔고 1등(greed65_smult0 $57,306)이 아니라, 강건성·방어 기준으로 사장님이 결정.
    #     greed55_smult0 = CPCV p25 1.758(9케이스 중 1등) + MDD -15.82%(한도 -15%에 가장 근접)
    #     + 2025 +10.99%(약한 해 방어 최고). TIL Ch4 원칙 "지표 최고값이 아니라 목표 적합성으로 결정".
    #   [폐기된 자동선정 로직 — 근거 보존, 다음 작업자 혼선 방지]
    #     이전: robust(years_positive==4 & cpcv>=base) 중 잔고 1등 자동선정 → greed65_smult0가 뽑혀
    #            ledger/분해표가 사장님 챔피언(greed55)과 불일치하는 문제 발생(07Prj 작업자 발견).
    #     수정: 아래처럼 greed55_smult0 명시 고정. 다른 케이스 원장이 필요하면 BEST_FIXED만 바꾸면 됨.
    BEST_FIXED = 'greed55_smult0'
    valid = grid[grid['case'] != '0_base_noFNG'].copy()
    sel = valid[valid['case'] == BEST_FIXED]
    if len(sel) == 0:
        pd.DataFrame([{'x': f'BEST_FIXED={BEST_FIXED} 케이스가 grid에 없음 (격자/임계 확인 필요)'}]
                     ).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')
        print(f"[ERR] BEST_FIXED={BEST_FIXED} not in grid — 격자(GREED_TH/SHORT_MULT) 확인"); return
    best_row = sel.iloc[0]
    best_case = best_row['case']

    # 최고케이스 원장·분해표 출력 (사장님 표준)
    led, bym, byr, bys = make_ledger_breakdowns(case_kept[best_case])
    led.to_csv(os.path.join(HERE, "stg4_best_ledger.csv"), index=False, encoding='utf-8-sig')
    bym.to_csv(os.path.join(HERE, "stg4_by_month.csv"), index=False, encoding='utf-8-sig')
    byr.to_csv(os.path.join(HERE, "stg4_by_regime.csv"), index=False, encoding='utf-8-sig')
    bys.to_csv(os.path.join(HERE, "stg4_by_year_side.csv"), index=False, encoding='utf-8-sig')

    months_pos = int((bym['ret_compound'] > 0).sum()); months_tot = len(bym)
    verdict = (f"VERDICT Ch7_Stg4 시나리오A 탐욕숏가드 | 펀딩{'REAL' if fund_real else 'NONE'} | $10k복리·14bp | "
               f"FNG커버{fng_cov*100:.0f}% 장세출처{smc_col or 'regime_classifier'} | "
               f"[기준선] ${base_m['end']:.0f}({base_m['ret']}% MDD{base_m['mdd']} p25{base_m['cpcv_p25']} "
               f"2025_{base_m['ret_2025']}% 2025숏R{base_m['short2025_ret']}% 전연도+{base_m['years_positive']}/4) | "
               f"[BEST] {best_case} ${best_row['end']:.0f}({best_row['ret']}% MDD{best_row['mdd']} "
               f"p25{best_row['cpcv_p25']} 2025_{best_row['ret_2025']}% 2025숏R{best_row['short2025_ret']}% "
               f"전연도+{best_row['years_positive']}/4) | 월별+{months_pos}/{months_tot}")
    print("[verdict] " + verdict)

    pd.DataFrame([dict(sec=verdict), dict(sec=f"[기준선] {base_m}"), dict(sec=f"[BEST] {dict(best_row)}")]
                 ).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')

    with open(os.path.join(HERE, ".stg4_metric"), "w", encoding="utf-8") as f:
        f.write(f"start={START}\nfunding={'REAL' if fund_real else 'NONE'}\nlabel_in_feature=False\n"
                f"cost_rt={COST_RT}\nfng_coverage={round(fng_cov,4)}\nregime_source={smc_col or 'regime_classifier'}\n"
                f"lookahead_block=fng_prevday+smc_postlabel_only+chip_past+cooldown_past+cpcv_group\n"
                f"n_cases={len(grid)}\n"
                f"base_end={base_m['end']:.0f}\nbase_ret={base_m['ret']}\nbase_mdd={base_m['mdd']}\n"
                f"base_cpcv_p25={base_m['cpcv_p25']}\nbase_ret2025={base_m['ret_2025']}\n"
                f"base_short2025_ret={base_m['short2025_ret']}\nbase_years_positive={base_m['years_positive']}\n"
                f"best_case={best_case}\nbest_end={best_row['end']:.0f}\nbest_mdd={best_row['mdd']}\n"
                f"best_cpcv_p25={best_row['cpcv_p25']}\nbest_ret2025={best_row['ret_2025']}\n"
                f"best_short2025_ret={best_row['short2025_ret']}\nbest_years_positive={best_row['years_positive']}\n"
                f"best_months_positive={months_pos}\nbest_months_total={months_tot}\n")
    print("[save] stg4_greed_grid/stg4_best_ledger/stg4_by_month/stg4_by_regime/stg4_by_year_side/stg4_coverage/summary.csv")


if __name__ == "__main__":
    main()
