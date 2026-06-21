# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch6_FrameWork_RAUTO_Stg12_BalanceCurveCompare.py
# 코드길이: 약 300줄 | 내부버전: 06Prj_Ch6_Stg12_BalanceCurveCompare_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]  사장님 확정(나, 계좌잔고 복리기준): Ch5 Stg15·Ch6 Stg10·Stg11을
#   전부 '같은 $10,000 복리 자본곡선'으로 재생성해 한 그래프에 겹쳐 비교. 단위차이(단순합 vs 복리) 제거.
#   엔진 무수정(해시 7f9192e3/dfdfac43). label_smc 입력금지. 비용0.14%+실펀딩.
#
#   [비교 곡선 — 전부 $10,000 복리]
#     A 추세봇 base       : er게이트(gate_er=0.45)만
#     B 추세봇 +칩필터     : A + 칩필터(CHOP>65·ER<0.35·ADX<25 진입스킵) = Ch5 Stg15
#     C 추세봇 +칩+쿨다운   : B + 쿨다운(연속sl K4->M8) = Ch6 Stg10 최종스택
#     S 횡보봇 +칩필터2of3  : 독립 $10,000
#     INT 통합            : C(추세 $10k) + S(횡보 $10k) = $20,000 복리 합산 (Stg11)
#
#   [★최적화]  무거운 엔진 호출(run_strategy, run_bot_honest)은 각 1회만. 칩필터·쿨다운은 사후필터라
#     같은 거래목록을 재사용해 A/B/C 세 곡선 생성. 지표(compute_indicators)도 1회. -> 연산 최소.
#
#   [★미래참조 차단]  칩·쿨다운 과거기반. label 입력금지. 자본곡선 거래 시간순.
#
# [PATH] 실행 D:\ML\verify\06Prj_Ch6_FrameWork_RAUTO_Stg12_BalanceCurveCompare\ . 데이터 상위 D:\ML\verify.
# [OUTPUT] D:\ML\verify\00WorkHstr\ 로 분석txt·INDEX. 결과 csv는 하위폴더.
#   balance_curves.csv / stage_summary.csv / by_year_balance.csv / ledger_trades.csv / summary.csv + .stg12_metric
# [In/Out 태그]
#   regime_classifier: compute_indicators(In OHLC/Out chop·er·adx) / chip_gate_at(횡보봇) / classify
#   cooldown: apply_cooldown(In 거래,봉분,K,M/Out keep,제외,발동)
#   엔진(무수정): champ.run_strategy(gate_er=0.45)/compute_signals/load_oi_8h/load_bb_8h/load_data/resample_tf/TF_MIN
#                 sdca.run_bot_honest/load_1m/resample_tf/precompute/build_1m_map/load_funding/funding_sum/BEST_PAR/DEFAULT_SLMULT
#   본코드: ns_i64/compound_curve/mdd_of/build_trend_raw/build_sway/main
#   변수(동결): START=10000 CHOP_HI=65 ER_LO=0.35 ADX_LO=25 COOL_K=4 COOL_M=8 COST_RT=0.0014 BAR_MIN=420
# ==============================================================================
import os, sys, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE); BOTS = os.path.join(HERE, "bots")
sys.path.insert(0, HERE)
import regime_classifier as RC
import cooldown as CD

START = 10000.0
CHOP_HI = 65.0; ER_LO = 0.35; ADX_LO = 25.0; COOL_K = 4; COOL_M = 8
COST_RT = 0.0014; BAR_MIN = 420
CHIP2OF3 = dict(chip_pre_n=4, chip_hold_k=3, chip_chop_hi=55.0, chip_combo='2of3', chip_squeeze=4.0)


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


def compound_curve(trades, start=START):
    # 거래 시간순 복리 자본곡선. trades: [{'exit_t','R'}]. 반환: [(time,cap)...], 최종cap, 총수익%
    if not trades:
        return [], start, 0.0
    s = sorted(trades, key=lambda t: pd.Timestamp(t['exit_t']).value)
    cap = start; curve = []
    for t in s:
        cap *= (1.0 + t['R']); curve.append((pd.Timestamp(t['exit_t']), cap))
    return curve, cap, round((cap / start - 1) * 100, 2)


def mdd_of(curve, start=START):
    peak = start; mdd = 0.0
    for _, cap in curve:
        peak = max(peak, cap); mdd = min(mdd, (cap - peak) / peak)
    return round(mdd * 100, 2)


def build_trend_raw(champ, sdca, df7, sig, oi7, bb7, ft, fr, ind, idx7):
    # 추세봇 거래 1회 생성 + 진입봉 chop/er/adx + chip 플래그. (엔진 1회 호출)
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
                        R=float(R), reason=t.get('reason', '?'), is_chip=is_chip))
    return raw


def build_sway(champ, sdca, DATA, ind, idx7, ft, fr):
    # 횡보봇 + 칩필터 2of3 (엔진 1회 호출)
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
        if not RC.chip_gate_at(ind, np.array([pos]), CHIP2OF3)[0]:
            continue
        out.append(dict(exit_t=pd.Timestamp(t.get('exit_t', et)), year=int(t.get('year', et.year)), R=float(t.get('R', 0.0))))
    return out


def main():
    print("[Stg12] 세 단계 복리 자본곡선 비교(계좌잔고 $10,000 기준) — 단위통일. 엔진 1회호출 최적화.")
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
    ind = RC.compute_indicators(o, h, l, c, RC.DEFAULT_PARAMS)   # 1회

    raw = build_trend_raw(champ, sdca, df7, sig, oi7, bb7, ft, fr, ind, idx7)   # 추세봇 1회
    sway = build_sway(champ, sdca, DATA, ind, idx7, ft, fr)                     # 횡보봇 1회
    print(f"[준비] 추세봇 raw {len(raw)}건(칩 {sum(t['is_chip'] for t in raw)}) / 횡보봇 {len(sway)}건 / 펀딩 {'REAL' if fund_real else 'NONE'}")

    # 곡선 A: base (전체) / B: 칩필터(칩 제외) / C: 칩+쿨다운
    A = list(raw)
    B = [t for t in raw if not t['is_chip']]
    ki, _, _ = CD.apply_cooldown(B, BAR_MIN, COOL_K, COOL_M)
    C = [B[i] for i in ki]

    curves = {}
    for name, tr in [('A_base', A), ('B_chip', B), ('C_chip_cool', C), ('S_sway', sway)]:
        cv, cap, ret = compound_curve(tr, START)
        curves[name] = dict(curve=cv, cap=cap, ret=ret, mdd=mdd_of(cv, START), n=len(tr))

    # 통합(INT): C + S 두 계좌 시간순 합산 복리
    allt = [(t['exit_t'], t['R'], 'C') for t in C] + [(t['exit_t'], t['R'], 'S') for t in sway]
    allt.sort(key=lambda x: pd.Timestamp(x[0]).value)
    capC = START; capS = START; int_curve = []; peak = 2 * START; int_mdd = 0.0
    for ts, R, who in allt:
        if who == 'C':
            capC *= (1 + R)
        else:
            capS *= (1 + R)
        comb = capC + capS; peak = max(peak, comb); int_mdd = min(int_mdd, (comb - peak) / peak)
        int_curve.append((pd.Timestamp(ts), comb))
    int_mdd = round(int_mdd * 100, 2); int_cap = capC + capS

    # balance_curves.csv: 월말 스냅샷(곡선 겹쳐그리기용, 시간축 통일)
    def monthly_snap(curve, start=START):
        if not curve:
            return {}
        d = pd.DataFrame([(t.strftime('%Y-%m'), cap) for t, cap in curve], columns=['ym', 'cap'])
        return d.groupby('ym')['cap'].last().to_dict()
    snaps = {k: monthly_snap(v['curve']) for k, v in curves.items()}
    snaps['INT'] = pd.DataFrame([(t.strftime('%Y-%m'), cap) for t, cap in int_curve], columns=['ym', 'cap']).groupby('ym')['cap'].last().to_dict() if int_curve else {}
    all_ym = sorted(set().union(*[set(s.keys()) for s in snaps.values()]))
    rows = []
    last = {k: (2 * START if k == 'INT' else START) for k in snaps}
    for ym in all_ym:
        row = {'month': ym}
        for k in ['A_base', 'B_chip', 'C_chip_cool', 'S_sway', 'INT']:
            last[k] = snaps[k].get(ym, last[k]); row[k] = round(last[k], 0)
        rows.append(row)
    pd.DataFrame(rows).to_csv(os.path.join(HERE, "balance_curves.csv"), index=False, encoding='utf-8-sig')

    # stage_summary.csv
    ss_rows = [
        dict(stage='A_base(Ch5 추세봇기본)', start=START, end=round(curves['A_base']['cap'], 0), ret_pct=curves['A_base']['ret'], mdd=curves['A_base']['mdd'], n=curves['A_base']['n']),
        dict(stage='B_chip(Ch5 Stg15)', start=START, end=round(curves['B_chip']['cap'], 0), ret_pct=curves['B_chip']['ret'], mdd=curves['B_chip']['mdd'], n=curves['B_chip']['n']),
        dict(stage='C_chip_cool(Ch6 Stg10)', start=START, end=round(curves['C_chip_cool']['cap'], 0), ret_pct=curves['C_chip_cool']['ret'], mdd=curves['C_chip_cool']['mdd'], n=curves['C_chip_cool']['n']),
        dict(stage='S_sway(횡보봇 칩필터)', start=START, end=round(curves['S_sway']['cap'], 0), ret_pct=curves['S_sway']['ret'], mdd=curves['S_sway']['mdd'], n=curves['S_sway']['n']),
        dict(stage='INT(Stg11 통합)', start=2 * START, end=round(int_cap, 0), ret_pct=round((int_cap / (2 * START) - 1) * 100, 2), mdd=int_mdd, n=len(C) + len(sway)),
    ]
    pd.DataFrame(ss_rows).to_csv(os.path.join(HERE, "stage_summary.csv"), index=False, encoding='utf-8-sig')

    # by_year_balance.csv: 각 단계 연도별 복리 수익률(독립 $10k)
    years = sorted(set(t['year'] for t in raw))
    by_rows = []
    for y in years:
        def yret(tr):
            rs = [t['R'] for t in tr if t['year'] == y]
            return round((np.prod([1 + r for r in rs]) - 1) * 100, 2) if rs else 0.0
        by_rows.append(dict(year=int(y), A_base=yret(A), B_chip=yret(B), C_chip_cool=yret(C), S_sway=yret(sway)))
    pd.DataFrame(by_rows).to_csv(os.path.join(HERE, "by_year_balance.csv"), index=False, encoding='utf-8-sig')

    # 원장
    pd.DataFrame([dict(bot='trend_C', year=t['year'], R=t['R'], reason=t['reason']) for t in C] +
                 [dict(bot='sway', year=t['year'], R=t['R'], reason='-') for t in sway]
                 ).to_csv(os.path.join(HERE, "ledger_trades.csv"), index=False, encoding='utf-8-sig')

    verdict = (f"VERDICT Stg12 복리자본곡선 | 펀딩{'REAL' if fund_real else 'NONE'} | 전부 $10,000 복리 | "
               f"[A base] ${round(curves['A_base']['cap'],0):.0f}({curves['A_base']['ret']}% MDD{curves['A_base']['mdd']}) | "
               f"[B 칩필터] ${round(curves['B_chip']['cap'],0):.0f}({curves['B_chip']['ret']}% MDD{curves['B_chip']['mdd']}) | "
               f"[C 칩+쿨다운] ${round(curves['C_chip_cool']['cap'],0):.0f}({curves['C_chip_cool']['ret']}% MDD{curves['C_chip_cool']['mdd']}) | "
               f"[횡보봇] ${round(curves['S_sway']['cap'],0):.0f}({curves['S_sway']['ret']}%) | "
               f"[통합 $20k] ${round(int_cap,0):.0f}({round((int_cap/(2*START)-1)*100,1)}% MDD{int_mdd})")
    print("[verdict] " + verdict)
    pd.DataFrame([dict(sec=verdict), dict(sec=f"[단계요약] {ss_rows}"), dict(sec=f"[연도별 복리] {by_rows}")]
                 ).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')
    with open(os.path.join(HERE, ".stg12_metric"), "w", encoding="utf-8") as f:
        f.write(f"start={START}\nfunding={'REAL' if fund_real else 'NONE'}\nlabel_in_feature=False\n")
        f.write(f"A_end={round(curves['A_base']['cap'],0):.0f}\nA_ret={curves['A_base']['ret']}\nA_mdd={curves['A_base']['mdd']}\nA_n={curves['A_base']['n']}\n")
        f.write(f"B_end={round(curves['B_chip']['cap'],0):.0f}\nB_ret={curves['B_chip']['ret']}\nB_mdd={curves['B_chip']['mdd']}\nB_n={curves['B_chip']['n']}\n")
        f.write(f"C_end={round(curves['C_chip_cool']['cap'],0):.0f}\nC_ret={curves['C_chip_cool']['ret']}\nC_mdd={curves['C_chip_cool']['mdd']}\nC_n={curves['C_chip_cool']['n']}\n")
        f.write(f"S_end={round(curves['S_sway']['cap'],0):.0f}\nS_ret={curves['S_sway']['ret']}\nS_mdd={curves['S_sway']['mdd']}\nS_n={curves['S_sway']['n']}\n")
        f.write(f"INT_end={round(int_cap,0):.0f}\nINT_ret={round((int_cap/(2*START)-1)*100,2)}\nINT_mdd={int_mdd}\n")
        f.write(f"months={len(all_ym)}\nlookahead_block=chip_past+cooldown_past\n")
    print("[save] balance_curves/stage_summary/by_year_balance/ledger/summary.csv")


if __name__ == "__main__":
    main()
