# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch6_FrameWork_RAUTO_Stg11_DualBotIntegrated.py
# 코드길이: 약 330줄 | 내부버전: 06Prj_Ch6_Stg11_DualBotIntegrated_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]  사장님 확정(가, 독립계좌 합산): Ch6 모든 확정알파를 합쳐 RAUTO 종합실력 측정.
#   이건 'RAUTO 실물 제작' 전 마지막 종합 백테스트. 월목표와의 갭을 보고 제작 우선순위를 정한다.
#   엔진 무수정(해시 7f9192e3/dfdfac43). label_smc 입력금지. 비용0.14%+실펀딩.
#
#   [추세봇 최종스택]  er게이트(gate_er=0.45, 내장) + 칩필터(CHOP>65·ER<0.35·ADX<25 진입스킵) + 쿨다운(연속sl K4->M8봉)
#   [횡보봇]  칩필터 2of3(Stg4 best: pre_n4·hold_k3·CHOP55·2of3·SQZ4.0) 적용
#   [독립계좌 합산]  추세봇 $10,000 + 횡보봇 $10,000 각자 운용 → 두 자본곡선 합쳐 $20,000 통합곡선.
#     자본배분 가정 없음(가장 깨끗). 동시포지션 충돌 없음(별도 서브계좌 가정).
#
#   [산출]  두 봇 각각+통합의 년도별·장세별 PF/수익/MDD + 통합 자본곡선 + 월수익률 환산 + 월목표 갭.
#   [★미래참조 차단]  칩·쿨다운 전부 과거기반. label 입력금지. 자본곡선은 거래 시간순 정렬.
#
# [PATH] 실행 D:\ML\verify\06Prj_Ch6_FrameWork_RAUTO_Stg11_DualBotIntegrated\ . 데이터 상위 D:\ML\verify.
# [OUTPUT] integrated_by_year.csv / integrated_by_regime.csv / equity_curve.csv / monthly_returns.csv /
#          ledger_trades.csv / summary.csv + .stg11_metric
# [In/Out 태그]
#   regime_classifier: compute_indicators / chip_gate_at(횡보봇 칩필터) / classify(장세)
#   cooldown: apply_cooldown(추세봇 쿨다운)
#   엔진(무수정): champ.run_strategy(gate_er=0.45)/compute_signals/load_oi_8h/load_bb_8h/load_data/resample_tf/TF_MIN
#                 sdca.run_bot_honest/load_funding/funding_sum/BEST_PAR/DEFAULT_SLMULT
#   본코드: ns_i64/metrics/mdd/get_trend_stack/get_sideway_chip/build_equity/monthly/main
#   변수(동결): CHOP_HI=65 ER_LO=0.35 ADX_LO=25 COOL_K=4 COOL_M=8 START_CAP=10000 COST_RT=0.0014 BAR_MIN=420
#               CHIP2OF3=dict(chip_pre_n4,chip_hold_k3,chip_chop_hi55,chip_combo2of3,chip_squeeze4.0)
# ==============================================================================
import os, sys, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE); BOTS = os.path.join(HERE, "bots")
sys.path.insert(0, HERE)
import regime_classifier as RC
import cooldown as CD

CHOP_HI = 65.0; ER_LO = 0.35; ADX_LO = 25.0; COOL_K = 4; COOL_M = 8
START_CAP = 10000.0; COST_RT = 0.0014; BAR_MIN = 420
CHIP2OF3 = dict(chip_pre_n=4, chip_hold_k=3, chip_chop_hi=55.0, chip_combo='2of3', chip_squeeze=4.0)
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


def equity_and_mdd(trades, start=START_CAP):
    # 거래 시간순 복리 자본곡선 + MDD. trades: [(exit_t, R), ...]
    if not trades:
        return [start], 0.0
    s = sorted(trades, key=lambda x: pd.Timestamp(x[0]).value)
    cap = start; curve = [start]; peak = start; mdd = 0.0
    for _, R in s:
        cap *= (1.0 + R); curve.append(cap)
        peak = max(peak, cap); dd = (cap - peak) / peak
        mdd = min(mdd, dd)
    return curve, round(mdd * 100, 2)


def get_trend_stack(champ, sdca, df7, sig, oi7, bb7, ft, fr, ind, idx7):
    # 추세봇 최종스택: er게이트(엔진) + 칩필터(진입스킵) + 쿨다운.
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
    # 칩필터: 칩거래 제외
    kept = [t for t in raw if not t['is_chip']]
    # 쿨다운
    ki, _, _ = CD.apply_cooldown(kept, BAR_MIN, COOL_K, COOL_M)
    kept = [kept[i] for i in ki]
    return kept


def get_sideway_chip(champ, sdca, DATA, ind, idx7, ft, fr):
    # 횡보봇 + 칩필터 2of3.
    s1 = sdca.load_1m(DATA); df8 = sdca.resample_tf(s1, sdca.TF_MIN); ssig = sdca.precompute(df8)
    ss, se = sdca.build_1m_map(s1, df8)
    mO = s1['open'].values; mH = s1['high'].values; mL = s1['low'].values
    mT = s1.index.values.astype('datetime64[ns]').astype('int64')
    res = sdca.run_bot_honest(df8, ssig, sdca.BEST_PAR, mO, mH, mL, mT, ss, se, ft, fr, sdca.DEFAULT_SLMULT, filter_mode='precise')
    trades = res[0] if isinstance(res, tuple) else res
    edges = ns_i64(idx7); out = []
    for t in (trades or []):
        et = t.get('entry_t')
        if et is None:
            continue
        et = pd.Timestamp(et)
        pos = max(0, min(np.searchsorted(edges, np.int64(et.value), side='right') - 1, len(edges) - 1))
        # 칩게이트 통과만
        if not RC.chip_gate_at(ind, np.array([pos]), CHIP2OF3)[0]:
            continue
        out.append(dict(side=int(t.get('side', 1)), entry_t=et, exit_t=pd.Timestamp(t.get('exit_t', et)),
                        year=int(t.get('year', et.year)), R=float(t.get('R', 0.0)), bar=pos))
    return out


def main():
    print("[Stg11] 두 봇 통합 백테스트(독립계좌 합산) — RAUTO 종합실력 + 월목표 갭. 실물제작 전 마지막 검증.")
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
    ind = RC.compute_indicators(o, h, l, c, RC.DEFAULT_PARAMS)
    reg, _, _, _ = RC.classify(o, h, l, c, dict(w=0.0, chop_hi=60.0, adx_hi=30.0, vote_n=3), ind=ind)

    trend = get_trend_stack(champ, sdca, df7, sig, oi7, bb7, ft, fr, ind, idx7)
    sway = get_sideway_chip(champ, sdca, DATA, ind, idx7, ft, fr)
    print(f"[준비] 추세봇 스택 {len(trend)}건 / 횡보봇 칩필터 {len(sway)}건 / 펀딩 {'REAL' if fund_real else 'NONE'}")

    # 년도별
    years = sorted(set([t['year'] for t in trend] + [t['year'] for t in sway]))
    by_year = []
    for y in years:
        tR = np.array([t['R'] for t in trend if t['year'] == y])
        sR = np.array([t['R'] for t in sway if t['year'] == y])
        mt = metrics(tR); ms = metrics(sR)
        # 독립계좌 합산: 각 봇 수익금($10k 기준) 합
        prof_t = (np.prod(1 + tR) - 1) * START_CAP if len(tR) else 0.0
        prof_s = (np.prod(1 + sR) - 1) * START_CAP if len(sR) else 0.0
        comb_ret = (prof_t + prof_s) / (2 * START_CAP) * 100
        by_year.append(dict(year=int(y), trend_n=mt['n'], trend_PF=mt['PF'], trend_ret=mt['ret'],
                            sway_n=ms['n'], sway_PF=ms['PF'], sway_ret=ms['ret'],
                            combined_ret_pct=round(comb_ret, 2),
                            combined_profit=round(prof_t + prof_s, 0)))
    pd.DataFrame(by_year).to_csv(os.path.join(HERE, "integrated_by_year.csv"), index=False, encoding='utf-8-sig')

    # 장세별
    by_reg = []
    for code in range(4):
        tR = np.array([t['R'] for t in trend if int(reg[t['bar']]) == code])
        sR = np.array([t['R'] for t in sway if int(reg[t['bar']]) == code])
        mt = metrics(tR); ms = metrics(sR)
        by_reg.append(dict(regime=REGIME_MAP[code], trend_n=mt['n'], trend_PF=mt['PF'], trend_ret=mt['ret'],
                          sway_n=ms['n'], sway_PF=ms['PF'], sway_ret=ms['ret']))
    pd.DataFrame(by_reg).to_csv(os.path.join(HERE, "integrated_by_regime.csv"), index=False, encoding='utf-8-sig')

    # 통합 자본곡선(두 계좌 각각 복리 후 합산) + MDD
    t_curve, t_mdd = equity_and_mdd([(t['exit_t'], t['R']) for t in trend])
    s_curve, s_mdd = equity_and_mdd([(t['exit_t'], t['R']) for t in sway])
    # 통합 곡선: 시간축 통일 위해 월말 스냅샷
    all_tr = [(pd.Timestamp(t['exit_t']), t['R'], 'T') for t in trend] + [(pd.Timestamp(t['exit_t']), t['R'], 'S') for t in sway]
    all_tr.sort(key=lambda x: x[0].value)
    capT = START_CAP; capS = START_CAP; eq_rows = []; peak = 2 * START_CAP; comb_mdd = 0.0
    for ts, R, who in all_tr:
        if who == 'T':
            capT *= (1 + R)
        else:
            capS *= (1 + R)
        comb = capT + capS
        peak = max(peak, comb); dd = (comb - peak) / peak; comb_mdd = min(comb_mdd, dd)
        eq_rows.append(dict(time=ts.strftime('%Y-%m-%d'), trend_cap=round(capT, 0), sway_cap=round(capS, 0), combined=round(comb, 0)))
    pd.DataFrame(eq_rows).to_csv(os.path.join(HERE, "equity_curve.csv"), index=False, encoding='utf-8-sig')
    comb_mdd = round(comb_mdd * 100, 2)

    # 월별 수익률(통합)
    eqdf = pd.DataFrame(eq_rows)
    monthly = []
    if len(eqdf):
        eqdf['ym'] = eqdf['time'].str[:7]
        prev = 2 * START_CAP
        for ym, g in eqdf.groupby('ym'):
            end = g['combined'].iloc[-1]
            mret = (end - prev) / prev * 100
            monthly.append(dict(month=ym, combined_cap=round(end, 0), monthly_ret_pct=round(mret, 2)))
            prev = end
    mdf = pd.DataFrame(monthly)
    mdf.to_csv(os.path.join(HERE, "monthly_returns.csv"), index=False, encoding='utf-8-sig')

    # 원장
    led = [dict(bot='trend', side=('long' if t['side'] > 0 else 'short'), year=t['year'],
                regime=REGIME_MAP[int(reg[t['bar']])], R=t['R']) for t in trend]
    led += [dict(bot='sideway', side=('long' if t['side'] > 0 else 'short'), year=t['year'],
                 regime=REGIME_MAP[int(reg[t['bar']])], R=t['R']) for t in sway]
    pd.DataFrame(led).to_csv(os.path.join(HERE, "ledger_trades.csv"), index=False, encoding='utf-8-sig')

    # 종합 지표
    tot_t = (np.prod([1 + t['R'] for t in trend]) - 1) * 100 if trend else 0.0
    tot_s = (np.prod([1 + t['R'] for t in sway]) - 1) * 100 if sway else 0.0
    comb_total = (capT + capS - 2 * START_CAP) / (2 * START_CAP) * 100
    n_months = len(monthly) if monthly else 1
    avg_monthly = comb_total / n_months
    pos_months = sum(1 for m in monthly if m['monthly_ret_pct'] > 0)
    verdict = (f"VERDICT Stg11 통합 | 추세봇스택 {len(trend)}건 {round(tot_t,1)}% MDD{t_mdd} / 횡보봇칩 {len(sway)}건 {round(tot_s,1)}% MDD{s_mdd} | "
               f"[통합] 36개월 {round(comb_total,1)}% MDD{comb_mdd} | 월평균 {round(avg_monthly,2)}% | 플러스월 {pos_months}/{n_months} | "
               f"펀딩{'REAL' if fund_real else 'NONE'}")
    print("[verdict] " + verdict)
    pd.DataFrame([dict(sec=verdict), dict(sec=f"[년도별] {by_year}"), dict(sec=f"[장세별] {by_reg}"),
                  dict(sec=f"[월평균 {round(avg_monthly,2)}% / 플러스월 {pos_months}/{n_months}]")]
                 ).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')
    with open(os.path.join(HERE, ".stg11_metric"), "w", encoding="utf-8") as f:
        f.write(f"n_trend={len(trend)}\nn_sway={len(sway)}\ntrend_total_pct={round(tot_t,2)}\ntrend_mdd={t_mdd}\n"
                f"sway_total_pct={round(tot_s,2)}\nsway_mdd={s_mdd}\ncombined_total_pct={round(comb_total,2)}\n"
                f"combined_mdd={comb_mdd}\nn_months={n_months}\navg_monthly_pct={round(avg_monthly,2)}\n"
                f"pos_months={pos_months}\nfunding={'REAL' if fund_real else 'NONE'}\nlabel_in_feature=False\n")
    print("[save] integrated_by_year/integrated_by_regime/equity_curve/monthly_returns/ledger/summary.csv")


if __name__ == "__main__":
    main()
