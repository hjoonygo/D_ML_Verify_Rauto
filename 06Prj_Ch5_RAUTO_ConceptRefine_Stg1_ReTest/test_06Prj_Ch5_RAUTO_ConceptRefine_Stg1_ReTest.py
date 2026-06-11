# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch5_RAUTO_ConceptRefine_Stg1_ReTest.py
# 코드길이: 약 360줄 | 내부버전: RAUTO_ConceptRefine_06_Ch5_Stg1_ReTest | 로직 축약/생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   추세봇(SpTrd_Fib_V1_Champion)과 횡보봇(SidewayDCA_Stg7)을 '원본 그대로' 불러다 돌린다.
#   ★전략 로직은 한 줄도 새로 안 짠다 — bots/ 폴더의 원본 엔진을 import 해서 그 함수를 호출한다.
#   원본 실행으로 거래원장(각 거래의 진입/청산 시각·가격·손익R)을 얻은 뒤, 바깥에서만 다음을 처리한다:
#     ① 비용 현실화: 추세봇의 왕복 0.04%를 Basic 표준 0.14%로 보정(원본 R에서 되돌려 다시 적용).
#                    횡보봇은 원본이 이미 0.14%라 그대로.
#     ② 펀딩 현실화: 추세봇의 '고정 0.0001·부호무시'를 실펀딩·부호반영으로 보정.
#                    횡보봇은 원본이 이미 실펀딩이라 그대로.
#     ③ 노출 스윕: 두 봇 모두 '실효노출 E(= 자본대비 레버리지포함 진입수량)'를 단계별로 흔들어
#                  자본곡선 cap*=(1+R*E)로 누적·MDD를 계산. MDD가 -35%를 넘지 않는 최대 E를 찾는다.
#     ④ 강제청산 점검: 보유 중 1분봉 경로의 '최악 역행폭'을 재서, 교차마진에서 그 노출이면 청산되는지
#                      (역행 >= (1-유지증거금)/E) 검사. 한 건이라도 청산이면 그 노출은 폭주(불가).
#     ⑤ 횡보봇 OI 임계 z=1.0(권고본)으로 + z=0(현행) 참고 비교.
#     ⑥ 두 봇 거래시점 겹침(합쳐도 분산되는지) 측정.
#     ⑦ (선택) 추세봇 분할A 인과 점검: 체결창(20봉) 안에 청산된 거래 비율·손익 + 분할없음 대조.
#   ★새 버그가 끼어들 자리 없음: 전략은 원본 함수 호출, 여기선 비용·펀딩·노출·청산만 산수로 후처리.
#
# [★사용명칭 정의]  ※추정 방지
#   실효노출 E = (자본대비 진입수량 %) × (레버리지). 예: 자본30%×2배=0.6(=60%). cap*=(1+R*E).
#   강제청산 역행임계 = (1 - 유지증거금)/E. 교차마진 단일포지션 가정의 근사. E 클수록 임계 작음(위험).
#   최악역행폭 = 보유기간 1분봉에서 진입가 대비 가장 불리하게 간 비율(롱=저점, 숏=고점).
#   MDD = 자본곡선의 고점대비 최대낙폭(%). 한도 = -35%(사장님 심리 감내선).
#
# [미래참조 차단] 원본 엔진의 미래참조 차단을 그대로 계승. 후처리(비용/펀딩/노출/청산)는 거래 확정 후
#   '이미 일어난' 결과에만 적용 → 봇 진입/청산 결정에 영향 없음. 1분봉 최악역행은 보유구간만 본다.
# [PATH] 실행: D:\ML\verify\06Prj_Ch5_RAUTO_ConceptRefine_Stg1_ReTest\ . 데이터: 상위 D:\ML\verify\ .
#        엔진: 이 폴더\bots\SpTrd_Fib_V1_Champion.py , bots\SidewayDCA_Stg7_engine.py (원본 무수정).
# [DATA] (상위) Merged_Data_with_Regime_Features.csv(OHLC+adx+bb+atr_ratio) / Merged_Data.csv(oi_zscore)
#        (상위) BTCUSDT_funding_history_8h.csv 또는 funding_history_8h.csv (실펀딩; 없으면 폴백+경고)
# [OUTPUT] (실행폴더) retest_summary.csv + retest_exposure.csv + retest_trend_trades.csv
#          + retest_sdca_trades.csv + retest_scenarios.csv + .retest_metric(check용)
#
# [사용 파일]
#   IN : (상위) 위 DATA 3종 / (이 폴더) bots\ 원본 엔진 2개
#   OUT: (실행폴더) 위 OUTPUT 5종 + .retest_metric
# [함수 In->Out]
#   load_engine(path,name)              파일경로,이름 -> 모듈객체(원본 엔진)
#   find_file(cands)                    후보파일명 -> 첫 발견 경로 or None
#   to_ns(t)                            Timestamp -> int64 ns
#   nfund_periods(a_t,b_t)              진입,청산시각 -> 8h 펀딩정산 횟수(추세봇 고정펀딩 되돌리기용)
#   worst_adverse(side,ep,a_ns,b_ns,..) 방향,진입가,구간 -> 최악 역행폭(0~)
#   pf(Rs)                              R리스트 -> Profit Factor
#   equity_mdd(Rs,E)                    R리스트,노출 -> (최종자본, MDD%)
#   n_liq(worst,E)                      최악역행리스트,노출 -> 강제청산 발생 건수
#   run_trend()                         (없음) -> (trades_A, trades_none) 추세봇 원본 실행
#   run_sdca(oi_z_hi)                   OI임계 -> trades 횡보봇 원본 실행
#   correct_trend_R(t,ft,fr)            거래,실펀딩 -> 비용/펀딩 현실화된 R
#   sweep_exposure(name,trades,Egrid,Rs,worst) -> 노출별 행 리스트 + 최대안전노출
#   overlap_hours(trA,trB)              두 거래리스트 -> 겹친 시간(시간단위)
#   main()                              전체 실행 + CSV 5종 저장
# [상태/상수] MDD_LIMIT=-35 / MAINT=0.005 / COST_RT=0.0014 / 노출그리드 2종
# ==============================================================================

import os, sys, math, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
BOTS = os.path.join(HERE, "bots")

# ── 후처리 상수(전부 Basic 표준·사장님 지시) ──
COST_RT        = 0.0014     # 왕복 비용(테이커0.05%+슬리피지0.02%)×2 = 0.14% (Basic 표준)
COST_TREND_ORG = 0.0004     # 추세봇 원본 왕복비용(되돌리기용)
FUND_TREND_ORG = 0.0001     # 추세봇 원본 고정 펀딩(되돌리기용)
MAINT          = 0.005      # 유지증거금 근사(0.5%) — 강제청산 임계 계산용
MDD_LIMIT      = -35.0      # MDD 한도(%) — 사장님 심리 감내선
START_CAP      = 10000.0

# 실효노출 E 그리드(= 자본대비 진입수량 × 레버리지). 사장님 기준점 포함: 추세 0.6, 횡보 2.5
TREND_E_GRID = [0.3, 0.6, 0.9, 1.2, 1.5, 2.0, 2.5, 3.0]
SDCA_E_GRID  = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
SDCA_Z_MAIN  = 1.0          # 권고본
SDCA_Z_REF   = 0.0          # 현행 참고


def load_engine(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def find_file(cands):
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for c in cands:
            p = os.path.join(d, c)
            if os.path.exists(p):
                return p
    return None


def to_ns(t):
    return int(pd.Timestamp(t).value)


def nfund_periods(a_t, b_t):
    eh_a = to_ns(a_t) / 3.6e12
    eh_b = to_ns(b_t) / 3.6e12
    return int(math.floor(eh_b / 8.0) - math.floor(eh_a / 8.0))


def worst_adverse(side, ep, a_ns, b_ns, m_ns, m_high, m_low):
    if ep is None or ep <= 0 or b_ns <= a_ns:
        return 0.0
    lo = int(np.searchsorted(m_ns, a_ns, side='left'))
    hi = int(np.searchsorted(m_ns, b_ns, side='right'))
    if hi <= lo:
        return 0.0
    if side == 1:
        mn = float(m_low[lo:hi].min())
        return max(0.0, (ep - mn) / ep)
    else:
        mx = float(m_high[lo:hi].max())
        return max(0.0, (mx - ep) / ep)


def pf(Rs):
    Rs = np.asarray(Rs, float)
    if len(Rs) == 0:
        return 0.0
    gp = Rs[Rs > 0].sum(); gl = -Rs[Rs < 0].sum()
    return round(float(gp / gl), 3) if gl > 0 else 999.0


def equity_mdd(Rs, E):
    cap = START_CAP; peak = cap; mdd = 0.0
    for r in Rs:
        cap *= (1.0 + r * E)
        if cap > peak:
            peak = cap
        if peak > 0:
            dd = (cap - peak) / peak
            if dd < mdd:
                mdd = dd
    return round(float(cap), 0), round(mdd * 100.0, 1)


def n_liq(worst, E):
    thr = (1.0 - MAINT) / E
    return int(sum(1 for w in worst if (w is not None and w >= thr)))


# ── 엔진 로드(원본 무수정) ──
TREND_PY = os.path.join(BOTS, "SpTrd_Fib_V1_Champion.py")
SDCA_PY  = os.path.join(BOTS, "SidewayDCA_Stg7_engine.py")
champ = load_engine(TREND_PY, "champ_engine")
sdca  = load_engine(SDCA_PY,  "sdca_engine")

DATA = find_file(["Merged_Data_with_Regime_Features.csv", "merged_data.csv"])
OIPATH = find_file(["Merged_Data.csv", "merged_data.csv"])
FUNDING = find_file(["BTCUSDT_funding_history_8h.csv", "funding_history_8h.csv",
                     "sample_BTCUSDT_funding_history_8h.csv"])


def run_trend(oi_arr, bb_arr, df_tf, sig):
    FINAL = dict(dz_oi=oi_arr, gate_mode='er', gate_er=0.45, gate_bb=bb_arr,
                 fib=(0.3, 0.5, 0.6), split_mode='A', split_n=3)
    tr_A = champ.run_strategy(df_tf, sig, 0, 'none', 0.8, **FINAL)
    NONE = dict(dz_oi=oi_arr, gate_mode='er', gate_er=0.45, gate_bb=bb_arr,
                fib=(0.3, 0.5, 0.6), split_mode='none', split_n=1)
    tr_none = champ.run_strategy(df_tf, sig, 0, 'none', 0.8, **NONE)
    return tr_A, tr_none


def run_sdca(df8, sig, mO, mH, mL, mT, ss, se, ft, fr, oi_z_hi):
    trades, _, _, blk = sdca.run_bot_honest(
        df8, sig, sdca.BEST_PAR, mO, mH, mL, mT, ss, se, ft, fr, sdca.DEFAULT_SLMULT,
        filter_mode='precise', atr_lo=sdca.ATR_LO, atr_hi=sdca.ATR_HI,
        filter_scens=sdca.FILTER_SCENS, oi_filter=True, oi_z_hi=oi_z_hi,
        oi_filter_scens=sdca.OI_FILTER_SCENS)
    return trades, blk


def correct_trend_R(t, ft, fr):
    # 원본 R = gross - 0.0004 - 0.0001*nfund  →  gross 복원 후 0.0014 + 실펀딩(부호반영) 재적용
    nf = nfund_periods(t['entry_t'], t['exit_t'])
    gross = t['R'] + COST_TREND_ORG + FUND_TREND_ORG * nf
    if ft is not None:
        fs = sdca.funding_sum(ft, fr, to_ns(t['entry_t']), to_ns(t['exit_t']))
    else:
        fs = None
    if fs is None:
        fcost = FUND_TREND_ORG * nf            # 폴백: 원본과 동일 고정
    else:
        fcost = t['side'] * fs                 # 부호반영: 롱 양수펀딩=지불, 숏 양수=수취
    return gross - COST_RT - fcost


def sweep_exposure(name, Rs, worst, Egrid):
    rows = []; safe_E = None
    base_pf = pf(Rs)
    for E in Egrid:
        fin, mdd = equity_mdd(Rs, E)
        nl = n_liq(worst, E)
        cumR = round((fin / START_CAP - 1.0) * 100.0, 1)
        ok = (mdd >= MDD_LIMIT) and (nl == 0)
        if ok:
            safe_E = E
        rows.append({'bot': name, 'E_노출': E, 'PF': base_pf, 'cumR_pct': cumR,
                     'MDD_pct': mdd, 'fin_cap': fin, 'n_liq': nl,
                     'verdict': '안전' if ok else ('청산위험' if nl > 0 else 'MDD초과')})
    return rows, safe_E


def overlap_hours(trA, trB):
    A = sorted((to_ns(t['entry_t']), to_ns(t['exit_t'])) for t in trA)
    B = sorted((to_ns(t['entry_t']), to_ns(t['exit_t'])) for t in trB)
    tot = 0; j0 = 0
    for a0, a1 in A:
        for k in range(j0, len(B)):
            b0, b1 = B[k]
            if b1 <= a0:
                j0 = k + 1; continue
            if b0 >= a1:
                break
            tot += max(0, min(a1, b1) - max(a0, b0))
    return round(tot / 3.6e12, 1)


def span_hours(tr):
    return round(sum(to_ns(t['exit_t']) - to_ns(t['entry_t']) for t in tr) / 3.6e12, 1)


def main():
    print("[ReTest 06_Ch5_Stg1] 추세·횡보 원본엔진 실행 + 비용0.14%·실펀딩·노출스윕(MDD<=-35%)·강제청산 점검")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    if DATA is None:
        pd.DataFrame([{'cell': '★검증불가: Merged_Data_with_Regime_Features.csv 없음(상위 D:\\ML\\verify)'}]) \
            .to_csv(os.path.join(HERE, "retest_summary.csv"), index=False, encoding='utf-8-sig')
        print("[abort] 데이터 없음"); return
    print(f"[data] {DATA}\n[oi] {OIPATH}\n[funding] {FUNDING}")

    # 실펀딩 로드(두 봇 공통)
    ft = fr = None; fnote = "FALLBACK(고정0.0001)"
    if FUNDING is not None:
        try:
            ft, fr = sdca.load_funding(FUNDING)
            fnote = f"REAL({os.path.basename(FUNDING)}, {sdca.load_funding.n_loaded}건, 누락{sdca.load_funding.n_dropped})"
        except Exception as e:
            fnote = f"FALLBACK(로드실패:{e})"
    print(f"[funding] {fnote}")

    # 1분봉 최악역행 점검용 (high/low/timestamp만)
    m = pd.read_csv(DATA, usecols=['timestamp', 'high', 'low'], index_col='timestamp', parse_dates=True)
    if getattr(m.index, 'tz', None) is not None:
        m.index = m.index.tz_localize(None)
    m = m.sort_index()
    m_ns = m.index.values.astype('datetime64[ns]').astype('int64')
    m_high = m['high'].values.astype('float64'); m_low = m['low'].values.astype('float64')

    rows = []
    def meta(cell):
        rows.append({'bot': cell, 'E_노출': '', 'PF': '', 'cumR_pct': '', 'MDD_pct': '',
                     'fin_cap': '', 'n_liq': '', 'verdict': ''})

    # ── 추세봇: 원본 실행 → 비용/펀딩 현실화 → 노출 스윕 ──
    trend_rows = []; trend_safe = None; trend_note = ""
    try:
        df_t = champ.load_data(DATA)
        df_tf = champ.resample_tf(df_t, champ.TF_MIN)
        sig_t = champ.compute_signals(df_tf)
        oi_arr = champ.load_oi_8h(OIPATH, df_tf.index) if OIPATH else None
        bb_arr = champ.load_bb_8h(DATA, df_tf.index)
        if oi_arr is None:
            trend_note = "★OI없음 → 무덤필터 OFF로 실행(degraded)"
        tr_A, tr_none = run_trend(oi_arr, bb_arr, df_tf, sig_t)
        # 비용/펀딩 현실화
        Rs_t = [correct_trend_R(t, ft, fr) for t in tr_A]
        worst_t = [worst_adverse(t['side'], t['entry'], to_ns(t['entry_t']), to_ns(t['exit_t']),
                                 m_ns, m_high, m_low) for t in tr_A]
        trend_rows, trend_safe = sweep_exposure('추세봇', Rs_t, worst_t, TREND_E_GRID)
        # 분할A 인과 점검: 체결창(20봉) 안에 청산된 거래 비율·손익 + 분할없음 대조
        within = [i for i, t in enumerate(tr_A) if t.get('bars', 99) < 20]
        Rs_none = [correct_trend_R(t, ft, fr) for t in tr_none]
        split_diag = (f"분할A PF{pf(Rs_t)} cumR1x{round(sum(Rs_t)*100,1)}% vs 분할없음 PF{pf(Rs_none)} "
                      f"cumR1x{round(sum(Rs_none)*100,1)}% | 체결창(20봉)내청산 {len(within)}/{len(tr_A)}건"
                      f"({round(100*len(within)/max(1,len(tr_A)))}%) 그 R합 {round(sum(Rs_t[i] for i in within)*100,2)}%")
        # 거래 저장용 (현실화 R 포함)
        td_t = [{'entry_t': t['entry_t'].strftime('%Y-%m-%d %H:%M'), 'exit_t': t['exit_t'].strftime('%Y-%m-%d %H:%M'),
                 'side': t['side'], 'year': t['year'], 'entry': round(t['entry'], 2), 'exit': round(t['exit'], 2),
                 'R_org_pct': round(t['R']*100, 4), 'R_real_pct': round(Rs_t[i]*100, 4),
                 'worst_adv_pct': round(worst_t[i]*100, 2), 'reason': t['reason'], 'bars': t['bars']}
                for i, t in enumerate(tr_A)]
        pd.DataFrame(td_t).to_csv(os.path.join(HERE, "retest_trend_trades.csv"), index=False, encoding='utf-8-sig')
    except Exception as e:
        trend_note = f"★추세봇 실행오류:{e}"
        split_diag = "n/a"
        print("[trend][error]", e)

    # ── 횡보봇: 원본 실행(z=1.0 권고본 + z=0 참고) → 노출 스윕 ──
    sdca_rows = []; sdca_safe = None; sdca_note = ""; sdca_z0_line = "n/a"; tr_s = []
    try:
        df1m = sdca.load_1m(DATA)
        df8 = sdca.resample_tf(df1m, sdca.TF_MIN)
        sig_s = sdca.precompute(df8)
        ss, se = sdca.build_1m_map(df1m, df8)
        mO = df1m['open'].values; mH = df1m['high'].values; mL = df1m['low'].values
        mT = df1m.index.values.astype('datetime64[ns]').astype('int64')
        has_oi = df1m.attrs.get('has_oi', False)
        has_atrr = df1m.attrs.get('has_atrr', False)
        sdca_note = (f"atr_ratio={'O' if has_atrr else 'X'} oi={'O' if has_oi else 'X'}"
                     f"(src={df1m.attrs.get('oi_source','?')})")
        # z=1.0 권고본 (주력)
        tr_s, _ = run_sdca(df8, sig_s, mO, mH, mL, mT, ss, se, ft, fr, SDCA_Z_MAIN)
        Rs_s = [t['R'] for t in tr_s]   # 횡보봇은 원본이 이미 0.14%+실펀딩
        worst_s = [worst_adverse(t['side'], t['entry'], to_ns(t['entry_t']), to_ns(t['exit_t']),
                                 m_ns, m_high, m_low) for t in tr_s]
        sdca_rows, sdca_safe = sweep_exposure(f'횡보봇z{SDCA_Z_MAIN}', Rs_s, worst_s, SDCA_E_GRID)
        # z=0 참고: E=2.5(현행) 한 점만 비교
        tr_s0, _ = run_sdca(df8, sig_s, mO, mH, mL, mT, ss, se, ft, fr, SDCA_Z_REF)
        Rs_s0 = [t['R'] for t in tr_s0]
        fin0, mdd0 = equity_mdd(Rs_s0, 2.5)
        sdca_z0_line = f"z=0 참고(E2.5): PF{pf(Rs_s0)} cumR{round((fin0/START_CAP-1)*100,1)}% MDD{mdd0}% n{len(tr_s0)}"
        td_s = [{'entry_t': t['entry_t'].strftime('%Y-%m-%d %H:%M'), 'exit_t': t['exit_t'].strftime('%Y-%m-%d %H:%M'),
                 'side': t['side'], 'year': t['year'], 'entry': round(t['entry'], 2), 'exit': round(t['exit'], 2),
                 'R_real_pct': round(t['R']*100, 4), 'worst_adv_pct': round(worst_s[i]*100, 2),
                 'reason': t['reason'], 'scen': t['scen'], 'bars': t['bars']}
                for i, t in enumerate(tr_s)]
        pd.DataFrame(td_s).to_csv(os.path.join(HERE, "retest_sdca_trades.csv"), index=False, encoding='utf-8-sig')
        # 8시나리오 분해(주력 z=1.0)
        sb = {s: [0, 0.0] for s in sdca.SCEN}
        for t in tr_s:
            if t['scen'] in sb:
                sb[t['scen']][0] += 1; sb[t['scen']][1] += t['R'] * 100.0
        pd.DataFrame([{'scen': s, 'n': sb[s][0], 'cumR_pct': round(sb[s][1], 2)} for s in sdca.SCEN]) \
            .to_csv(os.path.join(HERE, "retest_scenarios.csv"), index=False, encoding='utf-8-sig')
    except Exception as e:
        sdca_note = f"★횡보봇 실행오류:{e}"
        print("[sdca][error]", e)

    # ── 겹침 측정 ──
    ov = "n/a"
    try:
        if 'tr_A' in dir() and tr_s:
            oh = overlap_hours(tr_A, tr_s); ah = span_hours(tr_A); bh = span_hours(tr_s)
            ov = (f"겹친시간 {oh}h | 추세 보유합 {ah}h, 횡보 보유합 {bh}h | "
                  f"겹침비율 추세{round(100*oh/max(1,ah))}% 횡보{round(100*oh/max(1,bh))}%")
    except Exception as e:
        ov = f"겹침측정오류:{e}"

    # ── VERDICT ──
    verdict = (f"VERDICT Stg1_ReTest | 비용=왕복0.14%통일 펀딩={fnote} | "
               f"추세봇 최대안전노출(MDD>=-35%·청산0)={trend_safe} {trend_note} | "
               f"횡보봇z1.0 최대안전노출={sdca_safe} {sdca_note} | {sdca_z0_line} | "
               f"겹침: {ov} | 분할A점검: {split_diag if 'split_diag' in dir() else 'n/a'}")
    print("[verdict] " + verdict)

    # ── 저장 ──
    out = [{'bot': verdict, 'E_노출': '', 'PF': '', 'cumR_pct': '', 'MDD_pct': '',
            'fin_cap': '', 'n_liq': '', 'verdict': ''}]
    meta_local = out
    out += [{'bot': '─ 추세봇 노출스윕 ─', 'E_노출': '', 'PF': '', 'cumR_pct': '', 'MDD_pct': '',
             'fin_cap': '', 'n_liq': '', 'verdict': ''}]
    out += trend_rows
    out += [{'bot': '─ 횡보봇 노출스윕(z=1.0) ─', 'E_노출': '', 'PF': '', 'cumR_pct': '', 'MDD_pct': '',
             'fin_cap': '', 'n_liq': '', 'verdict': ''}]
    out += sdca_rows
    pd.DataFrame(out).to_csv(os.path.join(HERE, "retest_summary.csv"), index=False, encoding='utf-8-sig')
    pd.DataFrame(trend_rows + sdca_rows).to_csv(os.path.join(HERE, "retest_exposure.csv"),
                                                index=False, encoding='utf-8-sig')

    with open(os.path.join(HERE, ".retest_metric"), "w", encoding="utf-8") as f:
        f.write(f"trend_safe_E={trend_safe}\nsdca_safe_E={sdca_safe}\n"
                f"funding={fnote}\ncost_rt={COST_RT}\nmdd_limit={MDD_LIMIT}\n")
    print("[save] retest_summary.csv + retest_exposure.csv + trend/sdca_trades.csv + scenarios.csv")


if __name__ == "__main__":
    main()
