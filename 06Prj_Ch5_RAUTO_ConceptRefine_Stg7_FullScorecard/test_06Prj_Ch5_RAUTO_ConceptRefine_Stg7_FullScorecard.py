# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch5_RAUTO_ConceptRefine_Stg7_FullScorecard.py
# 코드길이: 약 300줄 | 내부버전: RAUTO_ConceptRefine_06_Ch5_Stg7_FullScorecard | 로직 전체 출력
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   추세봇 + 횡보봇을 '현재 진입수량 그대로' 3년 돌린 전체 성적표를 만든다. 엔진 무수정.
#   결과를 3가지 축으로 쪼개 집계: (가)장세별 (나)연도별 (다)롱숏별.
#   각 칸마다 5지표: PF, 수익률(누적R%), 손익비(payoff=평균이익/평균손실), 거래횟수, 수익금($).
#
#   [진입수량=노출, 엔진에 박힌 그대로]
#     추세봇: 고정 명목 NOMINAL=$50,000 (START_CAP $10k의 5배=교차5x). 수익금 += R*50000 (코드 521행 단리누적).
#     횡보봇: NOTIONAL_CAP=2.5배 복리. 수익금: cap *= (1 + R*2.5) (코드 651행).
#   [지표 정의]
#     PF = 총이익 / |총손실|   (이익합/손실합, 1보다 크면 흑자체질)
#     수익률 = ΣR * 100 (%)  (단리 R합. 추세봇 자본곡선과 별개의 '순수 신호합')
#     손익비 payoff = 평균(이긴거래 R) / |평균(진거래 R)|
#     거래횟수 = n
#     수익금 = 위 노출규칙대로 누적한 최종 $ - START_CAP
#   [장세] label_smc_8을 7h(추세봇)·8h(횡보봇) 진입봉에 매칭해 4장세 부여 (집계 전용, 매매엔 미사용).
#   [비용] round-trip 0.14% + 실제 펀딩(있으면).  [Lookahead] 없음(엔진 그대로, 라벨은 사후 집계만).
#
# [PATH] 실행: D:\ML\Verify\06Prj_..._Stg7_FullScorecard\ . 데이터: 상위 D:\ML\Verify\ (4종).
# [OUTPUT] scorecard_by_regime.csv / by_year.csv / by_side.csv / all_trades.csv / summary.csv + .stg7_metric
# ==============================================================================
import os, sys, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE); BOTS = os.path.join(HERE, "bots")
COST_RT = 0.0014
REGIME_MAP = {'uptrend': 0, 'downtrend': 1, 'volatile_range': 2, 'dead_range': 3}
REGIME_NAME = {0: 'uptrend', 1: 'downtrend', 2: 'volatile_range', 3: 'dead_range', -1: 'unknown'}


def load_engine(p, nm):
    s = importlib.util.spec_from_file_location(nm, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def find_file(c):
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for x in c:
            p = os.path.join(d, x)
            if os.path.exists(p):
                return p
    return None


champ = load_engine(os.path.join(BOTS, "SpTrd_Fib_V1_Champion.py"), "champ_engine")
sdca = load_engine(os.path.join(BOTS, "SidewayDCA_Stg7_engine.py"), "sdca_engine")
DATA = find_file(["Merged_Data_with_Regime_Features.csv", "merged_data.csv"])
OIPATH = find_file(["Merged_Data.csv", "merged_data.csv"])
FUND = find_file(["BTCUSDT_funding_history_8h.csv", "funding_history_8h.csv", "sample_BTCUSDT_funding_history_8h.csv"])
NOMINAL = champ.NOMINAL          # 추세봇 고정 명목 $50,000
NOTIONAL_CAP = sdca.NOTIONAL_CAP  # 횡보봇 명목 2.5배
START_CAP = champ.START_CAP


def metrics(R):
    R = np.asarray(R, float); n = len(R)
    if n == 0:
        return dict(n=0, PF=0.0, ret_pct=0.0, payoff=0.0, win_pct=0.0)
    win = R[R > 0]; los = R[R < 0]
    gp = float(win.sum()); gl = float(-los.sum())
    pf = round(gp / gl, 3) if gl > 0 else (999.0 if gp > 0 else 0.0)
    payoff = round((win.mean() / -los.mean()), 3) if len(win) and len(los) else 0.0
    return dict(n=n, PF=pf, ret_pct=round(R.sum() * 100, 2), payoff=payoff,
                win_pct=round(100 * len(win) / n, 1))


def profit_trend(R):     # 추세봇: 고정명목 단리누적 (엔진 521행 그대로)
    return round(float(np.sum(R) * NOMINAL), 0)


def profit_sdca(R):      # 횡보봇: 2.5배 복리 (엔진 651행 그대로)
    cap = START_CAP
    for r in R:
        cap *= (1 + r * NOTIONAL_CAP)
    return round(cap - START_CAP, 0)


def regime_at(ts_map, regime_arr, idx, t):
    pos = idx.searchsorted(pd.Timestamp(t)) - 1
    if 0 <= pos < len(regime_arr) and not np.isnan(regime_arr[pos]):
        return int(regime_arr[pos])
    return -1


def main():
    print("[Stg7] 두 봇 현재수량 3년 성적표")
    open(os.path.join(HERE, ".run_start"), "w").close()
    if DATA is None:
        pd.DataFrame([{'x': '데이터없음'}]).to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig'); return

    ft = fr = None
    if FUND:
        try:
            ft, fr = sdca.load_funding(FUND)
        except Exception:
            pass

    def fund_pay(side, et, xt):
        if ft is None:
            return 0.0
        fs = sdca.funding_sum(ft, fr, int(pd.Timestamp(et).value), int(pd.Timestamp(xt).value))
        return side * fs if fs is not None else 0.0

    # 장세 라벨 준비
    head = list(pd.read_csv(DATA, nrows=1).columns)
    lbl = next((c for c in head if c.startswith('label_smc_8')), None) or next((c for c in head if c.startswith('label_smc')), None)
    lab_raw = pd.read_csv(DATA, usecols=['timestamp', lbl], index_col='timestamp', parse_dates=True)
    if getattr(lab_raw.index, 'tz', None) is not None:
        lab_raw.index = lab_raw.index.tz_localize(None)
    lab_raw = lab_raw.sort_index()

    # ── 추세봇 ──
    df1m = champ.load_data(DATA); df7 = champ.resample_tf(df1m, champ.TF_MIN); sig = champ.compute_signals(df7)
    idx7 = df7.index; oi7 = champ.load_oi_8h(OIPATH, idx7); bb7 = champ.load_bb_8h(DATA, idx7)
    reg7 = lab_raw[lbl].resample(f"{champ.TF_MIN}min", label='left', closed='left').last().reindex(idx7).map(REGIME_MAP).values.astype('float64')
    ttr = champ.run_strategy(df7, sig, 0, 'none', 0.8, gate_mode='er', gate_er=0.45,
                             dz_oi=oi7, gate_bb=bb7, fib=(0.3, 0.5, 0.6), split_mode='A', split_n=3)
    trend_rows = []
    for t in ttr:
        R = t['side'] * (t['exit'] - t['entry']) / t['entry'] - COST_RT - fund_pay(t['side'], t['entry_t'], t['exit_t'])
        trend_rows.append(dict(bot='추세봇', side='롱' if t['side'] > 0 else '숏',
                               year=pd.Timestamp(t['entry_t']).year,
                               regime=REGIME_NAME[regime_at(None, reg7, idx7, t['entry_t'])],
                               R=float(R), entry_t=str(t['entry_t'])))
    print(f"[추세봇] {len(trend_rows)}건")

    # ── 횡보봇 ──
    sdca_rows = []
    try:
        s1 = sdca.load_1m(DATA); s8 = sdca.resample_tf(s1, sdca.TF_MIN); ss = sdca.precompute(s8)
        s_ss, s_se = sdca.build_1m_map(s1, s8)
        mO = s1['open'].values; mH = s1['high'].values; mL = s1['low'].values
        mT = s1.index.values.astype('datetime64[ns]').astype('int64')
        reg8 = lab_raw[lbl].resample(f"{sdca.TF_MIN}min", label='left', closed='left').last().reindex(s8.index).map(REGIME_MAP).values.astype('float64')
        strd, *_ = sdca.run_bot_honest(s8, ss, sdca.BEST_PAR, mO, mH, mL, mT, s_ss, s_se, ft, fr,
                                       sdca.DEFAULT_SLMULT, filter_mode='precise', atr_lo=sdca.ATR_LO, atr_hi=sdca.ATR_HI,
                                       filter_scens=sdca.FILTER_SCENS, oi_filter=True, oi_z_hi=1.0, oi_filter_scens=sdca.OI_FILTER_SCENS)
        for t in strd:
            sdca_rows.append(dict(bot='횡보봇', side='롱' if t['side'] > 0 else '숏',
                                  year=pd.Timestamp(t['entry_t']).year,
                                  regime=REGIME_NAME[regime_at(None, reg8, s8.index, t['entry_t'])],
                                  R=float(t['R']), entry_t=str(t['entry_t'])))
        print(f"[횡보봇] {len(sdca_rows)}건")
    except Exception as e:
        print(f"[횡보봇] 오류 {e}")

    allrows = trend_rows + sdca_rows
    df = pd.DataFrame(allrows)
    df.to_csv(os.path.join(HERE, "all_trades.csv"), index=False, encoding='utf-8-sig')

    def agg(group_keys, fname):
        out = []
        for bot, prof in [('추세봇', profit_trend), ('횡보봇', profit_sdca)]:
            sub = df[df.bot == bot]
            if sub.empty:
                continue
            for key, g in sub.groupby(group_keys):
                m = metrics(g.R.values)
                row = dict(bot=bot)
                if isinstance(key, tuple):
                    for k, kv in zip(group_keys, key):
                        row[k] = kv
                else:
                    row[group_keys if isinstance(group_keys, str) else group_keys[0]] = key
                row.update(m); row['profit_usd'] = prof(g.R.values)
                out.append(row)
        d = pd.DataFrame(out); d.to_csv(os.path.join(HERE, fname), index=False, encoding='utf-8-sig'); return d

    by_reg = agg('regime', "scorecard_by_regime.csv")
    by_year = agg('year', "by_year.csv")
    by_side = agg('side', "by_side.csv")

    # 봇 전체 요약
    summ = []
    for bot, prof in [('추세봇', profit_trend), ('횡보봇', profit_sdca)]:
        sub = df[df.bot == bot]
        if sub.empty:
            continue
        m = metrics(sub.R.values); m['bot'] = bot; m['profit_usd'] = prof(sub.R.values)
        m['noteposure'] = f"명목${NOMINAL:.0f}고정단리" if bot == '추세봇' else f"{NOTIONAL_CAP}배복리"
        summ.append(m)
    sdf = pd.DataFrame(summ); sdf.to_csv(os.path.join(HERE, "summary.csv"), index=False, encoding='utf-8-sig')

    print("[summary]\n" + sdf.to_string(index=False))
    print("[by_regime]\n" + by_reg.to_string(index=False))
    print("[by_year]\n" + by_year.to_string(index=False))
    print("[by_side]\n" + by_side.to_string(index=False))

    with open(os.path.join(HERE, ".stg7_metric"), "w", encoding="utf-8") as f:
        f.write(f"n_trend={len(trend_rows)}\nn_sdca={len(sdca_rows)}\nn_all={len(allrows)}\n")
        for r in summ:
            f.write(f"{r['bot']}_n={r['n']}\n{r['bot']}_PF={r['PF']}\n{r['bot']}_ret={r['ret_pct']}\n"
                    f"{r['bot']}_payoff={r['payoff']}\n{r['bot']}_profit={r['profit_usd']}\n")
        f.write(f"nominal_trend={NOMINAL}\nnotional_sdca={NOTIONAL_CAP}\nlabel={lbl}\nhas_label_in_feats=False\nfunding={'REAL' if ft is not None else 'NONE'}\n")
    print("[save] scorecard_by_regime / by_year / by_side / all_trades / summary.csv")


if __name__ == "__main__":
    main()
