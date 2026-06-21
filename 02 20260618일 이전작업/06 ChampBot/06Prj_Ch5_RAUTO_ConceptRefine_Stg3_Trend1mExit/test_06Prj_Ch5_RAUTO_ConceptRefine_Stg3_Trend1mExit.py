# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch5_RAUTO_ConceptRefine_Stg3_Trend1mExit.py
# 코드길이: 약 340줄 | 내부버전: RAUTO_ConceptRefine_06_Ch5_Stg3_Trend1mExit | 로직 축약/생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   추세봇 청산을 7h봉 → 1분봉으로 바꾸면 결과가 얼마나 달라지나(실시간 갭)를 잰다.
#   ★엔진은 무수정(bots/ 원본, 해시검증). 다만 '청산 해상도'를 바꾸면 청산 시점·가격이 달라지고,
#     단일포지션 봇이라 이후 진입까지 줄줄이 달라진다 → 단순 후처리 불가, 전략 루프를 다시 돌려야 한다.
#   그래서 엔진 run_strategy의 루프를 '그대로 복제'하되 청산 블록만 교체한다. 분할평단·숏차단은
#     엔진 함수(compute_split_entry/short_blocked_combo)를 '직접 호출'해 재구현 위험을 없앤다.
#   ★자기검증: 7h청산 복제판(V0)이 엔진 거래와 진입/청산/사유/가격 100% 일치하는지 먼저 대조.
#     일치해야 루프 복제가 정확하다는 증명 → 그 다음에야 1분봉판을 믿는다.
#
#   세 버전:
#     V0 7h복제   : 엔진과 동일(검증용). 청산=7h봉 OHLC 가정틱순서.
#     VE 1m청산만 : 손절을 보유구간 1분봉 경로에 대고 '먼저 닿으면' 즉시 청산(손절 우선).
#                   추세전환(trend_flip)은 7h봉 닫혀야 알 수 있어 시점 유지. 분할·슬리피지 변경 없음.
#                   → '청산 해상도'만의 순수 갭.
#     V1 현실판   : VE + 진입 슬리피지(승인 결정1, 롱 비싸게/숏 싸게). 배포 기준 현실치.
#   ※결정2(분할A 1분봉)는 no-op이라 미적용 — 대신 '7h분할 평단 == 1m분할 평단' 동등성을 검증항목으로 증명.
#
# [★사용명칭 정의]  ※추정 방지
#   1분봉 손절청산: 보유 7h봉 j의 1분봉 구간 [ss[j],se[j])에서 롱은 저가<=손절, 숏은 고가>=손절이
#                   '한 번이라도' 닿으면 그 봉에서 손절가로 청산(틱가정 대신 실제 1분 경로).
#   손절 우선(결정3): 같은 7h구간서 손절과 추세전환이 겹치면, 1분 손절이 봉마감(전환확정)보다
#                     먼저 일어나므로 손절 우선(보수적·시간순 정합).
#   진입 슬리피지(결정1): 체결가 = 신호평단 ×(1 + 방향×0.02%). 롱은 비싸게, 숏은 싸게(보수적).
#   갭: V0 대비 VE/V1의 누적수익·PF·MDD 차이. 음수면 7h백테가 낙관적이었다는 뜻.
#
# [미래참조] 엔진 무수정. 1분봉 손절은 보유구간(진입후~청산)만 스캔(미래봉 안 봄). trend_flip은 7h유지.
# [PATH] 실행: D:\ML\verify\06Prj_Ch5_RAUTO_ConceptRefine_Stg3_Trend1mExit\ . 데이터: 상위 D:\ML\verify\ .
# [DATA] (상위) Merged_Data_with_Regime_Features.csv / Merged_Data.csv(oi_zscore_24h) / 펀딩 8h csv
# [OUTPUT] (실행폴더) trend1m_summary.csv + trend1m_versions.csv + trend1m_trades_v1.csv + trend1m_splitchk.csv
#          + .trend1m_metric(check용)
# [지정노출(향후)] 추세 E=1.5, 횡보 E=10 — 이번 진단엔 미사용, 기록만.
#
# [함수 In->Out]
#   load_engine/find_file/to_ns/nfund               (Stg1·2와 동일 유틸)
#   build_1m_slices(m_ns, tf_index, tf_min)         1분봉ns,7h인덱스 -> (ss[], se[]) 각 7h봉의 1분봉구간
#   realize_R(side,entry,exit,a_t,b_t,ft,fr)        -> 현실화 R(비용0.14%+실펀딩 부호반영)
#   split_1m(d,i,...,m_ns,m_low,m_high,ss,se)       1분봉 경로로 분할평단(동등성 증명용)
#   replica(...,exit_mode,slip)                     엔진 루프 복제(청산 7h/1m, 슬리피지) -> 거래목록
#   trades_match(a,b)                               두 거래목록 진입/청산/사유/가격 일치여부
#   pf/equity_mdd                                   PF / (cumR%, MDD%)
#   main()                                          전체 실행 + CSV 저장
# ==============================================================================

import os, sys, math, importlib.util
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
BOTS = os.path.join(HERE, "bots")

COST_RT = 0.0014       # 왕복 0.14% (Basic 표준)
SLIP = 0.0002          # 진입 슬리피지 0.02% (승인 결정1)
SL_PCT = 1.0           # 엔진과 동일(초기 손절 1%)
FIB = (0.3, 0.5, 0.6)  # 엔진 FINAL과 동일
GATE_ER = 0.45
TREND_E, SDCA_E = 1.5, 10.0   # 향후 페이퍼 설정값(기록만)


def load_engine(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


def find_file(cands):
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for c in cands:
            p = os.path.join(d, c)
            if os.path.exists(p):
                return p
    return None


def to_ns(t):
    return int(pd.Timestamp(t).value)


champ = load_engine(os.path.join(BOTS, "SpTrd_Fib_V1_Champion.py"), "champ_engine")
sdca = load_engine(os.path.join(BOTS, "SidewayDCA_Stg7_engine.py"), "sdca_engine")

DATA = find_file(["Merged_Data_with_Regime_Features.csv", "merged_data.csv"])
OIPATH = find_file(["Merged_Data.csv", "merged_data.csv"])
FUNDING = find_file(["BTCUSDT_funding_history_8h.csv", "funding_history_8h.csv",
                     "sample_BTCUSDT_funding_history_8h.csv"])


def build_1m_slices(m_ns, tf_index, tf_min):
    start = tf_index.values.astype('datetime64[ns]').astype('int64')
    step = int(tf_min) * 60 * 1_000_000_000
    ss = np.searchsorted(m_ns, start, side='left')
    se = np.searchsorted(m_ns, start + step, side='left')
    return ss.astype(np.int64), se.astype(np.int64)


def realize_R(side, entry, exit_px, a_t, b_t, ft, fr):
    gross = side * (exit_px - entry) / entry
    if ft is not None:
        fs = sdca.funding_sum(ft, fr, to_ns(a_t), to_ns(b_t))
        fcost = side * fs if fs is not None else 0.0
    else:
        fcost = 0.0
    return gross - COST_RT - fcost


def split_1m(d, i, close, high, low, lastPH, lastPL, m_ns, m_low, m_high, tf_start, tf_step, n):
    # 분할A를 '1분봉 경로'로 계산(동등성 증명용). 원본 compute_split_entry와 같은 레벨/축소율.
    base = close[i]
    if np.isnan(lastPH) or np.isnan(lastPL):
        return base
    swing = lastPH - lastPL
    fills = [base]
    for lv in [0.382, 0.5]:
        if d == 1:
            target = base - lv * swing * 0.1
        else:
            target = base + lv * swing * 0.1
        # 1분봉 윈도우: 진입 다음 7h봉(i+1)부터 i+20봉 끝까지
        lo_b = i + 1; hi_b = min(i + 20, n - 1)
        got = None
        if lo_b <= hi_b:
            s0 = int(np.searchsorted(m_ns, tf_start[lo_b], 'left'))
            s1 = int(np.searchsorted(m_ns, tf_start[hi_b] + tf_step, 'left'))
            if s1 > s0:
                if d == 1 and m_low[s0:s1].min() <= target:
                    got = target
                elif d == -1 and m_high[s0:s1].max() >= target:
                    got = target
        fills.append(got if got is not None else base)
    return float(np.mean(fills))


def replica(df_tf, sig, oi_arr, m_low, m_high, ss, se, exit_mode, slip):
    high = df_tf['high'].values; low = df_tf['low'].values
    close = df_tf['close'].values; open_ = df_tf['open'].values
    idx = df_tf.index; n = len(close)
    Trend = sig['Trend']; ph_conf = sig['ph_conf']; pl_conf = sig['pl_conf']; er = sig['er']
    lastPH = np.nan; lastPL = np.nan
    pos = 0; entry_price = np.nan; entry_i = -1; sl = np.nan; pb = 0
    trades = []

    def close_trade(reason, exit_px, i):
        trades.append({'entry_t': idx[entry_i], 'exit_t': idx[i], 'side': pos,
                       'entry': entry_price, 'exit': exit_px, 'reason': reason,
                       'bars': i - entry_i, 'entry_i': entry_i, 'exit_i': i, 'year': idx[i].year})

    for i in range(n):
        new_ph = i in ph_conf; new_pl = i in pl_conf
        if new_ph: lastPH = ph_conf[i][1]
        if new_pl: lastPL = pl_conf[i][1]

        if pos != 0:
            if exit_mode == '7h':
                # 엔진 순서: 추세전환 먼저 → 7h봉 틱가정 손절
                if (pos == 1 and Trend[i] == -1) or (pos == -1 and Trend[i] == 1):
                    close_trade('trend_flip', close[i], i); pos = 0; sl = np.nan; pb = 0; continue
                if i > entry_i and not np.isnan(sl):
                    o_, h_, l_, c_ = open_[i], high[i], low[i], close[i]
                    ticks = (o_, h_, l_, c_) if c_ < o_ else (o_, l_, h_, c_)
                    hit = False
                    for px in ticks:
                        if pos == 1 and px <= sl: hit = True; break
                        if pos == -1 and px >= sl: hit = True; break
                    if hit:
                        close_trade('sl', sl, i); pos = 0; sl = np.nan; pb = 0; continue
            else:
                # 1분봉: 손절 먼저(인트라바·보수적) → 없으면 추세전환(봉마감)
                if i > entry_i and not np.isnan(sl):
                    s0, s1 = int(ss[i]), int(se[i])
                    hit = False
                    if s1 > s0:
                        if pos == 1:
                            hit = bool((m_low[s0:s1] <= sl).any())
                        else:
                            hit = bool((m_high[s0:s1] >= sl).any())
                    if hit:
                        close_trade('sl', sl, i); pos = 0; sl = np.nan; pb = 0; continue
                if (pos == 1 and Trend[i] == -1) or (pos == -1 and Trend[i] == 1):
                    close_trade('trend_flip', close[i], i); pos = 0; sl = np.nan; pb = 0; continue

        # 트레일 손절 갱신 (엔진 464-473 그대로)
        if pos == 1 and new_pl:
            pb += 1; ratio = FIB[0] if pb == 1 else FIB[1] if pb == 2 else FIB[2]
            if not np.isnan(lastPH):
                cand = lastPH - ratio * (lastPH - pl_conf[i][1])
                sl = cand if np.isnan(sl) else max(sl, cand)
        if pos == -1 and new_ph:
            pb += 1; ratio = FIB[0] if pb == 1 else FIB[1] if pb == 2 else FIB[2]
            if not np.isnan(lastPL):
                cand = lastPL + ratio * (ph_conf[i][1] - lastPL)
                sl = cand if np.isnan(sl) else min(sl, cand)

        # 진입 (엔진 475-507 그대로, 분할·숏차단은 엔진함수 직접호출)
        if pos == 0:
            le = Trend[i] == 1 and new_pl and not np.isnan(lastPH)
            se_ = Trend[i] == -1 and new_ph and not np.isnan(lastPL)
            if se_ and champ.short_blocked_combo(sig, i, 0, 'none', 0.8):
                se_ = False
            if oi_arr is not None:
                z = oi_arr[i]
                if not np.isnan(z) and (0.0 <= z < 1.0):
                    if er[i] >= GATE_ER:       # gate_mode='er'
                        le = False; se_ = False
            if le or se_:
                d = 1 if le else -1
                ep = champ.compute_split_entry(d, i, close, high, low, open_, n,
                                               pl_conf, ph_conf, lastPH, lastPL, 'A', 3)
                if slip > 0:
                    ep = ep * (1 + d * slip)   # 진입 슬리피지(보수적)
                pos = d; entry_price = ep; entry_i = i; pb = 0
                sl = ep * (1 - d * SL_PCT / 100)
    return trades


def trades_match(a, b):
    if len(a) != len(b):
        return False, f"건수 {len(a)} vs {len(b)}"
    for x, y in zip(a, b):
        if (x['entry_i'] != y['entry_i'] or x['exit_i'] != y['exit_i'] or x['side'] != y['side']
                or x['reason'] != y['reason']
                or abs(x['entry'] - y['entry']) > max(1e-6, abs(y['entry']) * 1e-6)
                or abs(x['exit'] - y['exit']) > max(1e-6, abs(y['exit']) * 1e-6)):
            return False, f"불일치 @entry_i{x['entry_i']}"
    return True, "100% 일치"


def pf(R):
    R = np.asarray(R, float); gp = R[R > 0].sum(); gl = -R[R < 0].sum()
    return round(float(gp / gl), 3) if gl > 0 else 999.0


def equity_mdd(R):
    cap = 1.0; peak = 1.0; mdd = 0.0
    for r in R:
        cap *= (1 + r); peak = max(peak, cap)
        if peak > 0:
            mdd = min(mdd, (cap - peak) / peak)
    return round((cap - 1) * 100, 1), round(mdd * 100, 1)


def metrics(trades, ft, fr):
    R = [realize_R(t['side'], t['entry'], t['exit'], t['entry_t'], t['exit_t'], ft, fr) for t in trades]
    cum, mdd = equity_mdd(R)
    nsl = sum(1 for t in trades if t['reason'] == 'sl')
    nfl = sum(1 for t in trades if t['reason'] == 'trend_flip')
    return R, dict(n=len(trades), n_sl=nsl, n_flip=nfl, PF=pf(R), cumR_pct=cum, MDD_pct=mdd)


def main():
    print("[Stg3] 추세봇 1분봉 청산 갭 측정 (엔진 무수정·복제검증)")
    open(os.path.join(HERE, ".run_start"), "w").close()
    if DATA is None or OIPATH is None:
        pd.DataFrame([{'x': '★검증불가: 데이터/OI 없음(상위 D:\\ML\\verify)'}]).to_csv(
            os.path.join(HERE, "trend1m_summary.csv"), index=False, encoding='utf-8-sig')
        print("[abort] 데이터 없음"); return
    print(f"[data]{DATA}\n[oi]{OIPATH}\n[funding]{FUNDING}")

    ft = fr = None; fnote = "FALLBACK(펀딩없음)"
    if FUNDING is not None:
        try:
            ft, fr = sdca.load_funding(FUNDING); fnote = f"REAL({sdca.load_funding.n_loaded}건)"
        except Exception as e:
            fnote = f"FALLBACK({e})"

    df1m = champ.load_data(DATA)
    df_tf = champ.resample_tf(df1m, champ.TF_MIN)
    sig = champ.compute_signals(df_tf)
    oi_arr = champ.load_oi_8h(OIPATH, df_tf.index)
    bb_arr = champ.load_bb_8h(DATA, df_tf.index)

    # 1분봉 배열 + 7h 슬라이스맵
    m = pd.read_csv(DATA, usecols=['timestamp', 'high', 'low'], index_col='timestamp', parse_dates=True)
    if getattr(m.index, 'tz', None) is not None:
        m.index = m.index.tz_localize(None)
    m = m.sort_index()
    m_ns = m.index.values.astype('datetime64[ns]').astype('int64')
    m_low = m['low'].values.astype('float64'); m_high = m['high'].values.astype('float64')
    ss, se = build_1m_slices(m_ns, df_tf.index, champ.TF_MIN)
    tf_start = df_tf.index.values.astype('datetime64[ns]').astype('int64')
    tf_step = int(champ.TF_MIN) * 60 * 1_000_000_000

    # 엔진 원본(검증 기준)
    eng = champ.run_strategy(df_tf, sig, 0, 'none', 0.8, gate_mode='er', gate_er=0.45,
                             dz_oi=oi_arr, gate_bb=bb_arr, fib=FIB, split_mode='A', split_n=3)
    eng_n = len(eng)

    # V0 7h복제 / VE 1m청산만 / V1 현실판(+슬리피지)
    V0 = replica(df_tf, sig, oi_arr, m_low, m_high, ss, se, '7h', 0.0)
    VE = replica(df_tf, sig, oi_arr, m_low, m_high, ss, se, '1m', 0.0)
    V1 = replica(df_tf, sig, oi_arr, m_low, m_high, ss, se, '1m', SLIP)

    # ── 검증1: V0 == 엔진 (진입/청산/사유/가격) ──
    eng_norm = [{'entry_i': None, 'exit_i': None, 'side': t['side'], 'reason': t['reason'],
                 'entry': t['entry'], 'exit': t['exit'],
                 'entry_t': t['entry_t'], 'exit_t': t['exit_t']} for t in eng]
    # 엔진엔 entry_i가 없으니 시각으로 매칭
    i_of = {t: k for k, t in enumerate(df_tf.index)}
    for e in eng_norm:
        e['entry_i'] = i_of[e['entry_t']]; e['exit_i'] = i_of[e['exit_t']]
    repl_ok, repl_msg = trades_match(V0, eng_norm)
    print(f"[검증1] V0 7h복제 vs 엔진: {repl_msg}")

    # ── 검증2: 분할 7h평단 == 1m평단 (결정2 no-op 증명) ──
    maxdiff = 0.0
    for t in eng:
        i = i_of[t['entry_t']]; d = t['side']
        # 진입봉 i의 러닝 피봇값 재현
        lph = lpl = np.nan
        for k in range(i + 1):
            if k in sig['ph_conf']: lph = sig['ph_conf'][k][1]
            if k in sig['pl_conf']: lpl = sig['pl_conf'][k][1]
        a1m = split_1m(d, i, df_tf['close'].values, df_tf['high'].values, df_tf['low'].values,
                       lph, lpl, m_ns, m_low, m_high, tf_start, tf_step, len(df_tf))
        maxdiff = max(maxdiff, abs(a1m - t['entry']))
    split_noop = maxdiff <= max(1e-4, abs(eng[0]['entry']) * 1e-6) if eng else True
    print(f"[검증2] 분할 7h평단 vs 1m평단 최대차 {maxdiff:.6f} -> {'동일(결정2 no-op 확정)' if split_noop else '차이있음'}")

    # ── 메트릭 & 갭 ──
    R0, m0 = metrics(V0, ft, fr)
    RE, mE = metrics(VE, ft, fr)
    R1, m1 = metrics(V1, ft, fr)
    gap_E = round(m0['cumR_pct'] - mE['cumR_pct'], 1)   # 7h대비 1m청산 갭(양수=1m이 더 나쁨=백테낙관)
    gap_1 = round(m0['cumR_pct'] - m1['cumR_pct'], 1)
    print(f"[갭] V0 {m0['cumR_pct']}% / VE {mE['cumR_pct']}% / V1 {m1['cumR_pct']}% "
          f"| 청산갭 {gap_E}%p, 현실판갭 {gap_1}%p")

    # ── 연도별(현실판 V1) ──
    yr = {}
    for t, r in zip(V1, R1):
        yr.setdefault(t['year'], 0.0); yr[t['year']] += r * 100
    ver = pd.DataFrame([dict(version='V0_7h복제(=엔진)', **m0), dict(version='VE_1m청산만', **mE),
                        dict(version='V1_현실판(+슬리피지)', **m1)])
    ver.to_csv(os.path.join(HERE, "trend1m_versions.csv"), index=False, encoding='utf-8-sig')

    pd.DataFrame([dict(entry_t=t['entry_t'].strftime('%Y-%m-%d %H:%M'),
                       exit_t=t['exit_t'].strftime('%Y-%m-%d %H:%M'), side=t['side'], year=t['year'],
                       entry=round(t['entry'], 2), exit=round(t['exit'], 2),
                       reason=t['reason'], bars=t['bars'], R_pct=round(r * 100, 4))
                  for t, r in zip(V1, R1)]).to_csv(
        os.path.join(HERE, "trend1m_trades_v1.csv"), index=False, encoding='utf-8-sig')

    pd.DataFrame([dict(check='분할 7h vs 1m 최대평단차', value=round(maxdiff, 6),
                       verdict='no-op(동일)' if split_noop else '차이')]).to_csv(
        os.path.join(HERE, "trend1m_splitchk.csv"), index=False, encoding='utf-8-sig')

    verdict = (f"VERDICT Stg3 | 펀딩={fnote} | V0복제=엔진:{repl_msg} | 분할1m=7h:{'no-op' if split_noop else '차이'}(최대차{maxdiff:.6f}) | "
               f"V0 {m0['cumR_pct']}%(PF{m0['PF']},MDD{m0['MDD_pct']}) / "
               f"VE_1m청산 {mE['cumR_pct']}%(PF{mE['PF']},MDD{mE['MDD_pct']}) / "
               f"V1_현실 {m1['cumR_pct']}%(PF{m1['PF']},MDD{m1['MDD_pct']}) | "
               f"청산갭 {gap_E}%p, 현실판갭 {gap_1}%p | 거래수 엔진{eng_n}/V0{m0['n']}/VE{mE['n']}/V1{m1['n']} | "
               f"지정노출(향후) 추세E={TREND_E} 횡보E={SDCA_E}")
    print("[verdict] " + verdict)

    out = [dict(sec=verdict), dict(sec='─ 버전 비교 ─')]
    for _, r in ver.iterrows():
        out.append(dict(sec=f"  {r['version']}: cumR{r['cumR_pct']}% PF{r['PF']} MDD{r['MDD_pct']}% "
                            f"n{r['n']}(sl{r['n_sl']}/flip{r['n_flip']})"))
    out.append(dict(sec='─ 현실판 V1 연도별 R% ─'))
    for Y in sorted(yr):
        out.append(dict(sec=f"  {Y}: {round(yr[Y], 2)}%"))
    pd.DataFrame(out).to_csv(os.path.join(HERE, "trend1m_summary.csv"), index=False, encoding='utf-8-sig')

    with open(os.path.join(HERE, ".trend1m_metric"), "w", encoding="utf-8") as f:
        f.write(f"repl_ok={repl_ok}\nsplit_noop={split_noop}\nmaxdiff={maxdiff:.6f}\n"
                f"eng_n={eng_n}\nv0_n={m0['n']}\nve_n={mE['n']}\nv1_n={m1['n']}\n"
                f"v0_cum={m0['cumR_pct']}\nve_cum={mE['cumR_pct']}\nv1_cum={m1['cumR_pct']}\n"
                f"gap_exit={gap_E}\ngap_real={gap_1}\nfunding={fnote}\n"
                f"trend_E={TREND_E}\nsdca_E={SDCA_E}\n")
    print("[save] trend1m_summary/versions/trades_v1/splitchk.csv")


if __name__ == "__main__":
    main()
