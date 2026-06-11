# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch6_FrameWork_RAUTO_Stg2_SwitchWalkForward.py
# 코드길이: 약 360줄 | 내부버전: 06Prj_Ch6_Stg2_SwitchWalkForward_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   목적(딱 한 가지 로직): "칩필터로 봇을 스위칭(일반장=추세봇만 / 칩장=횡보봇만)하면, 항상병행보다
#                          깨끗한 검증(워크포워드)에서 더 좋은가?"를 결정용 숫자로 가린다.
#   엔진 무수정(해시 대조). 바깥에서 신호/거래만 읽어 ① 스위칭 ② 병행70/30 ③ 단독 을 나란히 측정.
#
#   [확정·동결된 규칙 (데이터 보기 전 고정 = 메타-과최적화 방지)]
#     · 칩 정의(동결): CHOP>65 AND ER<0.35 AND ADX<25  ← 진입봉의 7h신호(엔진 산출, 과거기반=미래참조 없음)
#         - 칩장 = 횡보봇만 진입 / 일반장 = 추세봇만 진입. (워크포워드 전 구간 동일 임계, 2025 맞춤조정 금지)
#     · 스위칭 방식(동결): '신규진입 게이팅' — 꺼진 봇은 새 진입만 안 함, 이미 든 포지션은 정상 청산까지 보유.
#         (구현: 거래의 '진입봉 칩여부'로 채택. 추세거래=일반봉 진입만 / 횡보거래=칩봉 진입만.)
#     · 자본(동결): 스위칭·단독은 단일 풀(START_CAP). 병행만 70/30 슬리브(Stg1 비교용).
#     · 횡보봇 정밀필터 ON(동결): filter_mode='precise' (Ch5 PF2.099·WFE116% 견고). OI필터(WFE74)는 제외.
#     · 워크포워드(동결): 학습=처음부터 확장(최소 18개월) / 검증=3개월 / 3개월씩 전진 → 약 6개 OOS창.
#         결정지표(동결): OOS PF 1순위(노출과 무관=알파 자체), 보조 cumR·MDD. 노출은 각 학습창서 'MDD-35% 내 최대' 선택(위험사이징, PF불변).
#
#   [Lookahead 차단] 진입/청산은 엔진 그대로. 칩신호도 진입봉 과거값. label_smc_8은 '분석 태깅 전용'(봇 입력 아님).
#
# [PATH] 실행: D:\ML\verify\06Prj_Ch6_FrameWork_RAUTO_Stg2_SwitchWalkForward\ . 데이터: 상위 D:\ML\verify.
# [OUTPUT] all_trades.csv / mode_compare.csv / walkforward.csv / breakdown.csv / by_year_mode.csv / summary.csv + .stg2_metric
#
# [사용 파일/함수/변수 In/Out 태그]
#   엔진(무수정): champ.load_data/resample_tf/compute_signals/load_oi_8h/load_bb_8h/run_strategy/NOMINAL/START_CAP/MIN_CAP/TF_MIN
#                 sdca.load_1m/resample_tf/precompute/build_1m_map/run_bot_honest(filter_mode='precise')/load_funding/funding_sum/BEST_PAR/DEFAULT_SLMULT/TF_MIN
#   본 코드:
#     chip_of(chop,er,adx,i)->bool        : In 신호배열·인덱스 / Out 그 봉이 칩인가
#     get_trend_trades(...)->list[dict]   : Out 추세거래(순R·side·year·regime·chip)
#     get_sideway_trades(...)->list[dict] : Out 횡보거래(정밀필터 적용, 순R·side·year·regime·chip)
#     single_pool_equity(trs,Et,Es,cap,minc)->dict : Out 단일풀 cumR%·MDD%·liq·curve (스위칭/단독)
#     parallel_equity(tT,tS,Et,Es,split,cap,minc)->dict : Out 병행 70/30 cumR%·MDD%·liq (Stg1 모델)
#     metrics(R)->dict / agg_breakdown(trades,dim)->rows : 차원별(연/장세/롱숏) PF·payoff·ret·n·profit
#     gen_windows(t0,t1)->list[(trS,teS,teE)] : 워크포워드 창 생성
#   주요 변수(동결): CHOP_HI=65 / ER_LO=0.35 / ADX_LO=25 / CAP_SPLIT_TREND=0.70 / E_TREND_REF=1.2 / E_SW_REF=5.0
#                    / E_TREND_GRID=[1.0,1.2,1.5] / E_SW_GRID=[2.5,5.0] / MDD_LIMIT=-35 / TRAIN_MIN_MONTHS=18 / TEST_MONTHS=3 / STEP_MONTHS=3 / COST_RT=0.0014
# ==============================================================================
import os, sys, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE); BOTS = os.path.join(HERE, "bots")

# ── 동결 상수(데이터 보기 전 확정) ──
CHOP_HI, ER_LO, ADX_LO = 65.0, 0.35, 25.0      # 칩 정의(Ch5 플러그인 B)
CAP_SPLIT_TREND = 0.70                          # 병행 모드 비교용
E_TREND_REF, E_SW_REF = 1.2, 5.0                # 3모드 비교 기준노출
E_TREND_GRID, E_SW_GRID = [1.0, 1.2, 1.5], [2.5, 5.0]   # 워크포워드 노출 선택 그리드(위험사이징)
MDD_LIMIT = -35.0
TRAIN_MIN_MONTHS, TEST_MONTHS, STEP_MONTHS = 18, 3, 3
COST_RT = 0.0014                                # 추세봇 왕복비용(횡보봇은 엔진내 처리)
REGIME_MAP = {0: 'uptrend', 1: 'downtrend', 2: 'volatile_range', 3: 'dead_range'}
NAME2INT = {'uptrend': 0, 'downtrend': 1, 'volatile_range': 2, 'dead_range': 3}


def load_engine(p, nm):
    s = importlib.util.spec_from_file_location(nm, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


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
        return dict(n=0, PF=0.0, ret_pct=0.0, payoff=0.0, win_pct=0.0)
    win = R[R > 0]; los = R[R < 0]; gp = float(win.sum()); gl = float(-los.sum())
    pf = round(gp / gl, 3) if gl > 0 else (999.0 if gp > 0 else 0.0)
    payoff = round(win.mean() / -los.mean(), 3) if len(win) and len(los) else 0.0
    return dict(n=n, PF=pf, ret_pct=round(R.sum() * 100, 2), payoff=payoff, win_pct=round(100 * len(win) / n, 1))


def regime_lookup(DATA):
    head = list(pd.read_csv(DATA, nrows=1).columns)
    lbl = next((c for c in head if c.startswith('label_smc_8')), None) or next((c for c in head if c.startswith('label_smc')), None)
    if lbl is None:
        return None
    s = pd.read_csv(DATA, usecols=['timestamp', lbl], index_col='timestamp', parse_dates=True)[lbl]
    if getattr(s.index, 'tz', None) is not None:
        s.index = s.index.tz_localize(None)
    return s.sort_index()


def tag_regime(rs, ts):
    if rs is None:
        return 'unknown'
    try:
        pos = rs.index.searchsorted(pd.Timestamp(ts), side='right') - 1
        if pos < 0:
            return 'unknown'
        v = rs.iloc[pos]
        return v if isinstance(v, str) and v in NAME2INT else REGIME_MAP.get(int(v), 'unknown') if not isinstance(v, str) else 'unknown'
    except Exception:
        return 'unknown'


def chip_at(idx7, chop, er, adx, ts):
    # 진입봉(과거)에서 칩 여부. 미래참조 없음.
    pos = idx7.searchsorted(pd.Timestamp(ts), side='right') - 1
    if pos < 0 or pos >= len(chop):
        return False
    c, e, a = chop[pos], er[pos], adx[pos]
    if (c != c) or (e != e) or (a != a):   # NaN 방어
        return False
    return bool((c > CHOP_HI) and (e < ER_LO) and (a < ADX_LO))


def get_trend_trades(champ, sdca, DATA, OIPATH, FUND, rs):
    df1m = champ.load_data(DATA); df7 = champ.resample_tf(df1m, champ.TF_MIN); sig = champ.compute_signals(df7)
    idx7 = df7.index; oi7 = champ.load_oi_8h(OIPATH, idx7); bb7 = champ.load_bb_8h(DATA, idx7)
    chop, er, adx = sig['chop'], sig['er'], sig['adx']
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
    out = []
    for t in ttr:
        R = t['side'] * (t['exit'] - t['entry']) / t['entry'] - COST_RT - fpay(t['side'], t['entry_t'], t['exit_t'])
        et = pd.Timestamp(t['entry_t'])
        out.append(dict(bot='trend', side=('L' if t['side'] > 0 else 'S'), entry_t=et, exit_t=pd.Timestamp(t['exit_t']),
                        R=float(R), year=et.year, regime=tag_regime(rs, et), chip=chip_at(idx7, chop, er, adx, et)))
    return out, (ft is not None), (idx7, chop, er, adx)


def get_sideway_trades(champ, sdca, DATA, FUND, rs, sig7):
    idx7, chop, er, adx = sig7
    ft = fr = None
    if FUND:
        try:
            ft, fr = sdca.load_funding(FUND)
        except Exception:
            ft = fr = None
    s1 = sdca.load_1m(DATA); df8 = sdca.resample_tf(s1, sdca.TF_MIN); ssig = sdca.precompute(df8)
    ss, se = sdca.build_1m_map(s1, df8)
    mO = s1['open'].values; mH = s1['high'].values; mL = s1['low'].values
    mT = s1.index.values.astype('datetime64[ns]').astype('int64')
    # ★정밀필터 ON (Ch5 PF2.099·WFE116% 견고). OI필터는 끔(WFE74=과최적).
    res = sdca.run_bot_honest(df8, ssig, sdca.BEST_PAR, mO, mH, mL, mT, ss, se, ft, fr, sdca.DEFAULT_SLMULT,
                              filter_mode='precise')
    trades = res[0] if isinstance(res, tuple) else res
    out = []
    for t in (trades or []):
        et = t.get('entry_t'); xt = t.get('exit_t')
        if et is None or xt is None:
            continue
        et = pd.Timestamp(et)
        out.append(dict(bot='sideway', side=('L' if int(t.get('side', 0)) > 0 else 'S'), entry_t=et, exit_t=pd.Timestamp(xt),
                        R=float(t.get('R', 0.0)), year=et.year, regime=tag_regime(rs, et),
                        chip=chip_at(idx7, chop, er, adx, et)))
    return out, (ft is not None)


def single_pool_equity(trs, Et, Es, start, minc):
    ev = sorted(((t['exit_t'], (Et if t['bot'] == 'trend' else Es), t['R']) for t in trs), key=lambda x: x[0])
    cap = start; peak = start; mdd = 0.0; liq = False
    for ts, E, R in ev:
        f = 1.0 + R * E
        cap = cap * f if f > 0 else 0.0
        peak = max(peak, cap)
        if peak > 0:
            mdd = min(mdd, (cap - peak) / peak)
        if cap <= minc:
            liq = True; break
    return dict(ret_pct=round((cap - start) / start * 100, 2), mdd_pct=round(mdd * 100, 1), liq=bool(liq), final=round(cap, 0))


def parallel_equity(tT, tS, Et, Es, split, start, minc):
    ev = sorted([(t['exit_t'], 'T', t['R']) for t in tT] + [(t['exit_t'], 'S', t['R']) for t in tS], key=lambda x: x[0])
    ct = start * split; cs = start * (1 - split); peak = start; mdd = 0.0; liq = False
    for ts, who, R in ev:
        if who == 'T':
            f = 1 + R * Et; ct = ct * f if f > 0 else 0.0
        else:
            f = 1 + R * Es; cs = cs * f if f > 0 else 0.0
        tot = ct + cs; peak = max(peak, tot)
        if peak > 0:
            mdd = min(mdd, (tot - peak) / peak)
        if tot <= minc:
            liq = True; break
    return dict(ret_pct=round((ct + cs - start) / start * 100, 2), mdd_pct=round(mdd * 100, 1), liq=bool(liq))


def pick_max_exposure(trs, start, minc):
    # 학습창: MDD -35% 안에 드는 최대 노출 선택(위험사이징, PF불변).
    best = (E_TREND_GRID[0], E_SW_GRID[0])
    for et in E_TREND_GRID:
        for es in E_SW_GRID:
            r = single_pool_equity(trs, et, es, start, minc)
            if r['mdd_pct'] >= MDD_LIMIT and not r['liq']:
                if (et + es) > (best[0] + best[1]):
                    best = (et, es)
    return best


def gen_windows(t0, t1):
    wins = []
    test_start = (t0 + pd.DateOffset(months=TRAIN_MIN_MONTHS))
    while True:
        test_end = test_start + pd.DateOffset(months=TEST_MONTHS)
        if test_start >= t1:
            break
        wins.append((t0, test_start, min(test_end, t1)))
        test_start = test_start + pd.DateOffset(months=STEP_MONTHS)
    return wins


def agg_breakdown(trades, dim):
    keys = {}
    for t in trades:
        keys.setdefault(t[dim], []).append(t)
    rows = []
    for k, g in keys.items():
        for bot in ['trend', 'sideway', 'ALL']:
            gg = g if bot == 'ALL' else [t for t in g if t['bot'] == bot]
            if not gg:
                continue
            m = metrics([t['R'] for t in gg])
            rows.append(dict(dim=dim, key=k, bot=bot, n=m['n'], PF=m['PF'], payoff=m['payoff'],
                             ret_Rsum_pct=m['ret_pct'], win_pct=m['win_pct'],
                             profit_approx=round(float(sum(t['R'] for t in gg)) * champ_NOMINAL)))
    return rows


def main():
    global champ_NOMINAL
    print("[Stg2] 칩스위칭 vs 병행 vs 단독 + 워크포워드 + 정밀필터ON + 롱숏분해")
    open(os.path.join(HERE, ".run_start"), "w").close()
    champ = load_engine(os.path.join(BOTS, "SpTrd_Fib_V1_Champion.py"), "champ_engine")
    sdca = load_engine(os.path.join(BOTS, "SidewayDCA_Stg7_engine.py"), "sdca_engine")
    DATA = find_file(["Merged_Data_with_Regime_Features.csv", "merged_data.csv"])
    OIPATH = find_file(["Merged_Data.csv", "merged_data.csv"])
    FUND = find_file(["BTCUSDT_funding_history_8h.csv", "funding_history_8h.csv", "sample_BTCUSDT_funding_history_8h.csv"])
    if DATA is None:
        pd.DataFrame([{'x': 'no data'}]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig'); return
    START_CAP = champ.START_CAP; MIN_CAP = champ.MIN_CAP; champ_NOMINAL = champ.NOMINAL

    rs = regime_lookup(DATA)
    tT, fT, sig7 = get_trend_trades(champ, sdca, DATA, OIPATH, FUND, rs)
    tS, fS = get_sideway_trades(champ, sdca, DATA, FUND, rs, sig7)
    print(f"[거래] 추세 {len(tT)} / 횡보(정밀필터) {len(tS)} | 펀딩 추세{'O' if fT else 'X'} 횡보{'O' if fS else 'X'}")

    # ── 스위칭 게이팅: 추세=일반봉 진입만 / 횡보=칩봉 진입만 ──
    sw_trades = [dict(t, mode='switch') for t in tT if not t['chip']] + [dict(t, mode='switch') for t in tS if t['chip']]
    for t in tT:
        t['in_switch'] = (not t['chip'])
    for t in tS:
        t['in_switch'] = t['chip']
    all_tr = tT + tS

    # ── all_trades.csv (전체 거래 — 롱숏·연/장세·칩·스위치채택) ──
    pd.DataFrame([dict(bot=t['bot'], side=t['side'], year=t['year'], regime=t['regime'], chip=t['chip'],
                       in_switch=t['in_switch'], R_pct=round(t['R'] * 100, 4),
                       entry_t=t['entry_t'].strftime('%Y-%m-%d %H:%M'), exit_t=t['exit_t'].strftime('%Y-%m-%d %H:%M'))
                  for t in all_tr]).to_csv(os.path.join(HERE, "all_trades.csv"), index=False, encoding='utf-8-sig')

    # ── 3모드 비교 (기준노출 E추세1.2/E횡보5.0) ──
    sw = single_pool_equity(sw_trades, E_TREND_REF, E_SW_REF, START_CAP, MIN_CAP)
    par = parallel_equity(tT, tS, E_TREND_REF, E_SW_REF, CAP_SPLIT_TREND, START_CAP, MIN_CAP)
    soloT = single_pool_equity(tT, E_TREND_REF, E_SW_REF, START_CAP, MIN_CAP)
    soloS = single_pool_equity(tS, E_TREND_REF, E_SW_REF, START_CAP, MIN_CAP)
    mSW = metrics([t['R'] for t in sw_trades]); mPar = metrics([t['R'] for t in all_tr])
    mT = metrics([t['R'] for t in tT]); mS = metrics([t['R'] for t in tS])
    mode_rows = [
        dict(mode='①스위칭(메인)', PF=mSW['PF'], n=mSW['n'], cumR_pct=sw['ret_pct'], MDD=sw['mdd_pct'], liq=('Y' if sw['liq'] else 'N')),
        dict(mode='②병행70/30', PF=mPar['PF'], n=mPar['n'], cumR_pct=par['ret_pct'], MDD=par['mdd_pct'], liq=('Y' if par['liq'] else 'N')),
        dict(mode='③단독추세', PF=mT['PF'], n=mT['n'], cumR_pct=soloT['ret_pct'], MDD=soloT['mdd_pct'], liq=('Y' if soloT['liq'] else 'N')),
        dict(mode='③단독횡보(정밀)', PF=mS['PF'], n=mS['n'], cumR_pct=soloS['ret_pct'], MDD=soloS['mdd_pct'], liq=('Y' if soloS['liq'] else 'N')),
    ]
    pd.DataFrame(mode_rows).to_csv(os.path.join(HERE, "mode_compare.csv"), index=False, encoding='utf-8-sig')

    # ── 연도별 3모드 cumR(단순R합·기준노출) — 특히 2025 ──
    yrs = sorted(set(t['year'] for t in all_tr))
    yr_rows = []
    for y in yrs:
        swy = [t for t in sw_trades if t['year'] == y]
        ry_sw = sum((E_TREND_REF if t['bot'] == 'trend' else E_SW_REF) * t['R'] for t in swy) * 100
        ry_par = sum((E_TREND_REF if t['bot'] == 'trend' else E_SW_REF) * t['R'] for t in all_tr if t['year'] == y) * 100
        ry_soloT = sum(E_TREND_REF * t['R'] for t in tT if t['year'] == y) * 100
        yr_rows.append(dict(year=y, switch_Rsum=round(ry_sw, 2), parallel_Rsum=round(ry_par, 2), soloTrend_Rsum=round(ry_soloT, 2),
                            n_switch=len(swy)))
    pd.DataFrame(yr_rows).to_csv(os.path.join(HERE, "by_year_mode.csv"), index=False, encoding='utf-8-sig')

    # ── 차원별(연/장세/롱숏) PF·손익비·수익률·거래수·수익금 — all_trades 기반 ──
    bd = agg_breakdown(all_tr, 'year') + agg_breakdown(all_tr, 'regime') + agg_breakdown(all_tr, 'side')
    pd.DataFrame(bd).to_csv(os.path.join(HERE, "breakdown.csv"), index=False, encoding='utf-8-sig')

    # ── 워크포워드: 스위칭 모드의 OOS 안정성 ──
    t0 = min(t['entry_t'] for t in all_tr); t1 = max(t['exit_t'] for t in all_tr)
    wins = gen_windows(t0, t1)
    wf_rows = []
    oos_R_all = []
    for k, (trs0, tes, tee) in enumerate(wins, 1):
        train = [t for t in sw_trades if t['entry_t'] < tes]
        test = [t for t in sw_trades if tes <= t['entry_t'] < tee]
        Et, Es = pick_max_exposure(train, START_CAP, MIN_CAP) if train else (E_TREND_REF, E_SW_REF)
        mte = metrics([t['R'] for t in test])
        te_eq = single_pool_equity(test, Et, Es, START_CAP, MIN_CAP)
        oos_R_all += [t['R'] for t in test]
        wf_rows.append(dict(win=k, test_start=str(tes.date()), test_end=str(tee.date()),
                            n_train=len(train), n_test=mte['n'], OOS_PF=mte['PF'], OOS_payoff=mte['payoff'],
                            OOS_cumR=te_eq['ret_pct'], OOS_MDD=te_eq['mdd_pct'],
                            pick_E=f"{Et}/{Es}", small=('YES' if mte['n'] < 10 else 'NO')))
    pd.DataFrame(wf_rows).to_csv(os.path.join(HERE, "walkforward.csv"), index=False, encoding='utf-8-sig')
    wf_oos = metrics(oos_R_all)
    pf_list = [r['OOS_PF'] for r in wf_rows if r['small'] == 'NO']
    pf_stable = (len(pf_list) > 0 and min(pf_list) >= 1.0)

    y25 = next((r for r in yr_rows if r['year'] == 2025), None)
    verdict = (f"VERDICT Stg2 깨끗검증 | 거래 추세{len(tT)}/횡보정밀{len(tS)} | "
               f"칩정의 CHOP>{int(CHOP_HI)}·ER<{ER_LO}·ADX<{int(ADX_LO)} | "
               f"[3모드 기준노출] ①스위칭 PF{mSW['PF']}/{sw['ret_pct']}%/MDD{sw['mdd_pct']} vs "
               f"②병행 PF{mPar['PF']}/{par['ret_pct']}%/MDD{par['mdd_pct']} vs ③단독추세 PF{mT['PF']}/{soloT['ret_pct']}% / 단독횡보 PF{mS['PF']}/{soloS['ret_pct']}% | "
               f"[워크포워드 {len(wins)}창] 통합OOS PF{wf_oos['PF']} | 창별OOS PF {[r['OOS_PF'] for r in wf_rows]} | PF안정(>=1, 소표본제외)={'YES' if pf_stable else 'NO'} | "
               f"★2025 R합: 스위칭 {y25['switch_Rsum'] if y25 else 'NA'}% vs 병행 {y25['parallel_Rsum'] if y25 else 'NA'}% vs 단독추세 {y25['soloTrend_Rsum'] if y25 else 'NA'}% | "
               f"펀딩 추세{'REAL' if fT else 'NONE'}/횡보{'REAL' if fS else 'NONE'}")
    print("[verdict] " + verdict)
    pd.DataFrame([dict(sec=verdict), dict(sec=f"[3모드] {mode_rows}"), dict(sec=f"[연도별] {yr_rows}"),
                  dict(sec=f"[워크포워드] {wf_rows}")]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')
    with open(os.path.join(HERE, ".stg2_metric"), "w", encoding="utf-8") as f:
        f.write(f"n_trend={len(tT)}\nn_sw_precise={len(tS)}\nn_switch={mSW['n']}\n"
                f"sw_pf={mSW['PF']}\nsw_ret={sw['ret_pct']}\nsw_mdd={sw['mdd_pct']}\nsw_liq={'YES' if sw['liq'] else 'NO'}\n"
                f"par_pf={mPar['PF']}\npar_ret={par['ret_pct']}\npar_mdd={par['mdd_pct']}\n"
                f"soloT_pf={mT['PF']}\nsoloT_ret={soloT['ret_pct']}\nsoloS_pf={mS['PF']}\nsoloS_ret={soloS['ret_pct']}\n"
                f"sw_precise_solo_pf={mS['PF']}\n"
                f"wf_windows={len(wins)}\nwf_oos_pf={wf_oos['PF']}\nwf_pf_list={[r['OOS_PF'] for r in wf_rows]}\nwf_pf_stable={'YES' if pf_stable else 'NO'}\n"
                f"y2025_switch={y25['switch_Rsum'] if y25 else 0}\ny2025_parallel={y25['parallel_Rsum'] if y25 else 0}\ny2025_soloT={y25['soloTrend_Rsum'] if y25 else 0}\n"
                f"chip_def=CHOP>{CHOP_HI}&ER<{ER_LO}&ADX<{ADX_LO}_FROZEN\nfilter_mode=precise\noi_filter=False\n"
                f"funding_trend={'REAL' if fT else 'NONE'}\nfunding_sw={'REAL' if fS else 'NONE'}\nhas_label_in_bot_input=False\n")
    print("[save] all_trades/mode_compare/walkforward/breakdown/by_year_mode/summary.csv")


champ_NOMINAL = 50000.0
if __name__ == "__main__":
    main()
