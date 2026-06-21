# -*- coding: utf-8 -*-
# [FILE] test_05Alpha_UpCh1_stg2_Sideway4Champ_Vrfy.py
# 코드길이: 약 560줄 | 내부버전명: 05Alpha_Up_Ch1_S4C_Vrfy_stg2 | 전체 출력, 축약/생략 없음
# ==============================================================================
# [목적] Sideway4Champ_V1_stg2(눌림목 추세추종, 원본 롱전용 .pine)를:
#        ① 파이썬으로 정확히 포팅하고  ② 숏을 거울상으로 추가(롱숏)  ③ 피보 SL을 A안/B안
#        두 기준점으로 비교 검증한다. 롱/숏 따로 + 월별 롱/숏 따로 5지표(거래수·승률·수익률·손익비·수익금)를 낸다.
#
# [원본 로직 충실 포팅 — Sideway4Champ_V1_stg2.pine 187줄 기준]
#   롱 진입(2단계): ①셋업 = 상승구조(HH: lastPH>prevPH) + 새저점(눌림 newPL) + lastPH 존재
#                   ②반등트리거(RSI_UP: RSI가 rsiOS 상향돌파) 가 waitMax봉 내 발생 → 롱.
#   숏 진입(거울상): ①셋업 = 하락구조(LL: lastPL<prevPL) + 새고점(되돌림 newPH) + lastPL 존재
#                   ②하락트리거(RSI_DN: RSI가 rsiOSs 하향돌파) 가 waitMax봉 내 발생 → 숏.
#   SL: 진입직후 ±slPct% 고정. 보유 중 롱=새저점마다 / 숏=새고점마다 피보 단계 갱신.
#       롱 trailSL=max(안내림), 숏 trailSL=min(안올림). 재난선 balStop(롱 -10%/숏 +10%).
#   청산: 시간손절(timeStop봉) 또는 (트레일·재난·ATR 중 가장 먼저 닿는 손절).
#   익절목표 없음(추세추종) — 원본과 동일.
#
# [A안/B안 — fib_cand 함수에서만 분기 (Key_05Alpha_UpCh1_stg1 계약·어댑터 구조 준수)]
#   A안 HIGH_BASE(원본 .pine 158행): 롱 cand=lastPH-ratio*(lastPH-pl) / 숏 cand=lastPL+ratio*(ph-lastPL)
#   B안 LOW_BASE (설계 의도)       : 롱 cand=pl+ratio*(lastPH-pl)     / 숏 cand=ph-ratio*(ph-lastPL)
#   ratio 단계: pb==1→fib1(0.3), pb==2→fib2(0.5), pb>=3→fib3(0.6)  (원본과 동일 3단계)
#
# [비용] 원본 .pine과 동일: 커미션 0.08%(편도 환산 위해 왕복 0.08% 적용), 슬리피지 0, 단일포지션.
#        결정=닫힌 봉, 체결=다음 봉 시가(미래참조 차단).
# [미래참조 차단] 피벗은 pivR봉 뒤 확정(원본 동일). RSI/ATR/DMI 과거봉만. 진입 체결가=open[i+1].
# [PATH] 실행: D:\ML\verify\05Alpha_UpCh1_stg2_Sideway4Champ_Vrfy\ . 데이터: 상위 D:\ML\verify\ (자동탐색).
# [DATA] 상위 Merged_Data_with_Regime_Features.csv (없으면 merged_data.csv). OHLCV만 사용.
# [OUTPUT] (실행폴더) s4c_summary.csv + s4c_trades.csv + s4c_monthly.csv + s4c_scenarios.csv → check.py가 정리.
# [SPEED] TF별 신호(피벗/RSI/ATR/DMI) 1회 사전계산 후 캐시. 그리드는 가벼운 거래루프만 재실행.
#
# [FUNCTIONS]
#   find_data()              In:-                  Out: csv경로            데이터 자동탐색
#   load_1m(path)            In: csv경로           Out: 1분봉 DataFrame    로드/정렬/tz제거
#   resample_tf(df,tf)       In: 1분봉,분          Out: TF OHLCV           리샘플
#   rma(x,n)                 In: 배열,기간         Out: Wilder평활 배열    RSI/ATR/DMI 공용
#   compute_rsi(close,n)     In: 종가,기간         Out: RSI 배열           반등 트리거
#   compute_atr(h,l,c,n)     In: 고저종,기간       Out: ATR 배열           바닥스탑
#   compute_dmi(h,l,c,n,s)   In: 고저종,길이,평활  Out: ADX 배열           게이트
#   pivots(high,low,L,R)     In: 고저,좌우         Out: ph_at,pl_at dict   피벗 확정봉
#   precompute(df,par)       In: TFdf,파라미터     Out: 신호 dict          TF별 1회 사전계산
#   fib_cand(mode,side,...)  In: 모드,방향,피벗    Out: SL 후보 cand       ★A/B 어댑터(분기 핵심)
#   scen_label(...)          In: adx,구조,위치     Out: 시나리오명         8시나리오 사후라벨
#   run_bot(df,sig,par)      In: TFdf,sig,파라미터 Out: trades 리스트      ★롱숏 진입/청산 엔진
#   agg(trades,...)          In: 거래,필터         Out: 5지표 dict         거래수·승률·수익률·손익비·수익금
#   monthly(trades,side)     In: 거래,방향         Out: 월별 5지표 리스트  월별 롱/숏 분해
#   pick_best(runs,mode)     In: 런목록,모드       Out: best행             train PF 최고셀
#   main()                   In:-                  Out: CSV 4종            그리드+A/B+롱숏+월별
# [변수] pos(방향0/1/-1) avg(평단) entry_i pb trailSL entryBar waiting waitBars sl_mode
#        lastPH prevPH lastPL prevPL structUp structDn  ratio cand stopUse
# ==============================================================================

import os, sys, itertools
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)

# ── CFG (원본 .pine 동일) ──
COMMISSION = 0.0008          # 0.08% — 원본 commission_value (체결당 적용, 진입+청산 2회)
START_CAP  = 10000.0
SLPCT      = 1.0             # 진입직후 고정손절 %
FIB        = (0.3, 0.5, 0.6) # 1/2/3단계
BAL_SL     = 10.0            # 재난방지 % (롱 -10% / 숏 +10%)
TIME_STOP  = 30
WAIT_MAX   = 5
RSI_LEN    = 14
ATR_LEN    = 14
ADX_LEN    = 14
ADX_SMOOTH = 14
PIV_L      = 4
PIV_R      = 1
TRAIN_YEARS = [2023, 2024]
TEST_YEARS  = [2025, 2026]

# ── 탐색 그리드 ──
GRID_TF     = [60, 2*60, 4*60]      # 1h, 2h, 4h
GRID_rsiOS  = [35, 40, 45]          # 롱 반등기준선
GRID_rsiOSs = [55, 60, 65]          # 숏 하락기준선(롱 대칭, 60 중심)
GRID_gate   = ['OFF', 'ADX_TREND']
GRID_adxTh  = [20, 25]
GRID_dir    = ['LONG', 'SHORT', 'BOTH']
GRID_SLMODE = ['HIGH_BASE', 'LOW_BASE']   # A안 / B안

SCEN = ['clean_uptrend','clean_downtrend','choppy_range','strong_breakout',
        'failed_pullback','v_reversal','high_adx','low_adx']


def find_data():
    cands = ["Merged_Data_with_Regime_Features.csv", "merged_data.csv"]
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for c in cands:
            p = os.path.join(d, c)
            if os.path.exists(p):
                return p
    raise FileNotFoundError("상위 D:\\ML\\verify 에 데이터 csv 필요")


def load_1m(path):
    head = pd.read_csv(path, nrows=1)
    cols = ['timestamp', 'open', 'high', 'low', 'close']
    df = pd.read_csv(path, usecols=cols, index_col='timestamp', parse_dates=True)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    return df.sort_index()


def resample_tf(df1m, tf_min):
    rule = f"{tf_min}min"
    out = df1m.resample(rule, label='left', closed='left').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
    return out


def rma(x, n):
    # Wilder 평활 (RSI/ATR/DMI 공용)
    a = np.asarray(x, dtype=float)
    out = np.full(len(a), np.nan)
    if len(a) < n:
        return out
    out[n - 1] = a[:n].mean()
    for i in range(n, len(a)):
        out[i] = (out[i - 1] * (n - 1) + a[i]) / n
    return out


def compute_rsi(close, n):
    c = np.asarray(close, dtype=float)
    d = np.diff(c, prepend=c[0])
    gain = np.where(d > 0, d, 0.0)
    loss = np.where(d < 0, -d, 0.0)
    ag = rma(gain, n); al = rma(loss, n)
    rs = np.divide(ag, al, out=np.full_like(ag, np.nan), where=al > 0)
    rsi = 100 - 100 / (1 + rs)
    rsi[al == 0] = 100.0
    return rsi


def compute_atr(high, low, close, n):
    h = np.asarray(high, float); l = np.asarray(low, float); c = np.asarray(close, float)
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum.reduce([h - l, np.abs(h - pc), np.abs(l - pc)])
    return rma(tr, n)


def compute_dmi(high, low, close, n, smooth):
    h = np.asarray(high, float); l = np.asarray(low, float); c = np.asarray(close, float)
    N = len(c)
    up = h - np.roll(h, 1); dn = np.roll(l, 1) - l
    up[0] = 0; dn[0] = 0
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum.reduce([h - l, np.abs(h - pc), np.abs(l - pc)])
    atr = rma(tr, n)
    pdi = 100 * rma(pdm, n) / np.where(atr > 0, atr, np.nan)
    ndi = 100 * rma(ndm, n) / np.where(atr > 0, atr, np.nan)
    dx = 100 * np.abs(pdi - ndi) / np.where((pdi + ndi) > 0, pdi + ndi, np.nan)
    adx = rma(np.nan_to_num(dx), smooth)
    return adx


def pivots(high, low, L, R):
    # ta.pivothigh/low(L,R): 중심봉이 좌L·우R 봉보다 높(낮)으면 확정. 확정은 중심+R 봉에서.
    h = np.asarray(high, float); l = np.asarray(low, float); n = len(h)
    ph_at = {}; pl_at = {}
    for c in range(L, n - R):
        seg_h = h[c - L:c + R + 1]; seg_l = l[c - L:c + R + 1]
        if h[c] == seg_h.max() and (seg_h == h[c]).sum() == 1:
            ph_at[c + R] = float(h[c])   # 확정봉 = c+R, 값 = high[c]
        if l[c] == seg_l.min() and (seg_l == l[c]).sum() == 1:
            pl_at[c + R] = float(l[c])
    return ph_at, pl_at


def precompute(df, gate_mode, adx_th):
    high = df['high'].values; low = df['low'].values; close = df['close'].values
    open_ = df['open'].values; n = len(close)
    rsi = compute_rsi(close, RSI_LEN)
    atr = compute_atr(high, low, close, ATR_LEN)
    adx = compute_dmi(high, low, close, ADX_LEN, ADX_SMOOTH)
    ph_at, pl_at = pivots(high, low, PIV_L, PIV_R)
    years = df.index.year.values
    months = np.array([f"{df.index[i].year}-{df.index[i].month:02d}" for i in range(n)])
    return {'high': high, 'low': low, 'close': close, 'open': open_, 'n': n,
            'rsi': rsi, 'atr': atr, 'adx': adx, 'ph_at': ph_at, 'pl_at': pl_at,
            'years': years, 'months': months}


def fib_cand(sl_mode, side, ratio, lastPH, lastPL, piv):
    # ★A/B 어댑터. piv = 이번에 새로 찍힌 피벗값(롱=새저점 pl, 숏=새고점 ph)
    if side == 1:   # 롱: 고점 lastPH, 새저점 piv
        span = lastPH - piv
        return (lastPH - ratio * span) if sl_mode == 'HIGH_BASE' else (piv + ratio * span)
    else:           # 숏: 저점 lastPL, 새고점 piv
        span = piv - lastPL
        return (lastPL + ratio * span) if sl_mode == 'HIGH_BASE' else (piv - ratio * span)


def scen_label(adx_i, structUp, structDn, adx_th_ref=22):
    strong = (not np.isnan(adx_i)) and adx_i >= adx_th_ref
    if structUp and strong:  return 'strong_breakout'
    if structUp:             return 'clean_uptrend'
    if structDn and strong:  return 'high_adx'
    if structDn:             return 'clean_downtrend'
    if strong:               return 'v_reversal'
    return 'choppy_range' if (np.isnan(adx_i) or adx_i < 18) else 'low_adx'


def run_bot(df, sig, par):
    high = sig['high']; low = sig['low']; close = sig['close']; open_ = sig['open']; n = sig['n']
    rsi = sig['rsi']; atr = sig['atr']; adx = sig['adx']
    ph_at = sig['ph_at']; pl_at = sig['pl_at']; months = sig['months']; years = sig['years']
    rsiOS = par['rsiOS']; rsiOSs = par['rsiOSs']; gate_mode = par['gate']; adx_th = par['adx_th']
    direction = par['dir']; sl_mode = par['sl_mode']
    allow_long = direction in ('LONG', 'BOTH')
    allow_short = direction in ('SHORT', 'BOTH')

    lastPH = np.nan; prevPH = np.nan; lastPL = np.nan; prevPL = np.nan
    pos = 0; avg = np.nan; entry_i = -1; pb = 0; trailSL = np.nan
    waiting_L = False; waitBars_L = 0
    waiting_S = False; waitBars_S = 0
    scen0 = None
    trades = []

    for i in range(n):
        new_ph = i in ph_at; new_pl = i in pl_at
        ph_i = ph_at.get(i, np.nan); pl_i = pl_at.get(i, np.nan)
        if new_ph:
            prevPH = lastPH; lastPH = ph_i
        if new_pl:
            prevPL = lastPL; lastPL = pl_i

        structUp = (not np.isnan(lastPH)) and (not np.isnan(prevPH)) and lastPH > prevPH
        structDn = (not np.isnan(lastPL)) and (not np.isnan(prevPL)) and lastPL < prevPL
        gate = True if gate_mode == 'OFF' else ((not np.isnan(adx[i])) and adx[i] > adx_th)

        # ── 보유 중: SL 갱신 + 청산 ──
        if pos != 0:
            # 피보 스텝업: 롱=새저점마다 / 숏=새고점마다
            if pos == 1 and new_pl and not np.isnan(lastPH):
                pb += 1
                ratio = FIB[0] if pb == 1 else FIB[1] if pb == 2 else FIB[2]
                cand = fib_cand(sl_mode, 1, ratio, lastPH, lastPL, pl_i)
                trailSL = cand if np.isnan(trailSL) else max(trailSL, cand)
            elif pos == -1 and new_ph and not np.isnan(lastPL):
                pb += 1
                ratio = FIB[0] if pb == 1 else FIB[1] if pb == 2 else FIB[2]
                cand = fib_cand(sl_mode, -1, ratio, lastPH, lastPL, ph_i)
                trailSL = cand if np.isnan(trailSL) else min(trailSL, cand)

            bars_in = i - entry_i
            exit_px = np.nan; reason = None
            if pos == 1:
                balStop = avg * (1 - BAL_SL / 100.0)
                stopUse = balStop if np.isnan(trailSL) else max(trailSL, balStop)
                if bars_in >= TIME_STOP:
                    exit_px = close[i]; reason = 'time'
                elif low[i] <= stopUse:
                    exit_px = stopUse; reason = 'trail_sl'
            else:
                balStop = avg * (1 + BAL_SL / 100.0)
                stopUse = balStop if np.isnan(trailSL) else min(trailSL, balStop)
                if bars_in >= TIME_STOP:
                    exit_px = close[i]; reason = 'time'
                elif high[i] >= stopUse:
                    exit_px = stopUse; reason = 'trail_sl'

            if reason is not None:
                gross = (exit_px - avg) / avg if pos == 1 else (avg - exit_px) / avg
                R = gross - COMMISSION * 2     # 진입+청산 왕복 수수료
                trades.append({'side': pos, 'entry_t': df.index[entry_i], 'exit_t': df.index[i],
                               'entry': avg, 'exit': exit_px, 'R': R, 'reason': reason,
                               'bars': bars_in, 'scen': scen0, 'year': years[i], 'month': months[i]})
                pos = 0; avg = np.nan; pb = 0; trailSL = np.nan
            # 보유 중엔 신규 진입 안 함(단일 포지션)
            continue

        # ── 미보유: 셋업 → 대기 → 트리거 진입 ──
        # 롱 셋업/대기
        if allow_long:
            setup_L = structUp and gate and new_pl and (not np.isnan(lastPH))
            if setup_L and not waiting_L:
                waiting_L = True; waitBars_L = 0
            if waiting_L:
                waitBars_L += 1
            trigL = (rsi[i - 1] <= rsiOS < rsi[i]) if i > 0 else False  # crossover(rsi, rsiOS)
            if waiting_L and trigL:
                px = open_[i + 1] if i + 1 < n else close[i]
                pos = 1; avg = px; entry_i = i; pb = 0
                trailSL = px * (1 - SLPCT / 100.0)
                scen0 = scen_label(adx[i], structUp, structDn)
                waiting_L = False; waitBars_L = 0; waiting_S = False
                continue
            if waiting_L and waitBars_L > WAIT_MAX:
                waiting_L = False; waitBars_L = 0

        # 숏 셋업/대기 (거울상)
        if allow_short and pos == 0:
            setup_S = structDn and gate and new_ph and (not np.isnan(lastPL))
            if setup_S and not waiting_S:
                waiting_S = True; waitBars_S = 0
            if waiting_S:
                waitBars_S += 1
            trigS = (rsi[i - 1] >= rsiOSs > rsi[i]) if i > 0 else False  # crossunder(rsi, rsiOSs)
            if waiting_S and trigS:
                px = open_[i + 1] if i + 1 < n else close[i]
                pos = -1; avg = px; entry_i = i; pb = 0
                trailSL = px * (1 + SLPCT / 100.0)
                scen0 = scen_label(adx[i], structUp, structDn)
                waiting_S = False; waitBars_S = 0; waiting_L = False
                continue
            if waiting_S and waitBars_S > WAIT_MAX:
                waiting_S = False; waitBars_S = 0

    return trades


def agg(trades, years=None, side_filter=None):
    if years is not None:
        trades = [t for t in trades if t['year'] in years]
    if side_filter is not None:
        trades = [t for t in trades if t['side'] == side_filter]
    if not trades:
        return {'trades': 0, 'win_pct': 0.0, 'cumR_pct': 0.0, 'PF': 0.0, 'payoff': 0.0, 'final_cap': START_CAP}
    R = np.array([t['R'] for t in trades])
    wins = R[R > 0]; losses = R[R < 0]
    gp = wins.sum(); gl = -losses.sum()
    pf = (gp / gl) if gl > 0 else 999.0
    payoff = (wins.mean() / -losses.mean()) if (len(wins) > 0 and len(losses) > 0) else 0.0
    cap = START_CAP
    for r in R:
        cap *= (1 + r)
    return {'trades': len(trades), 'win_pct': round(len(wins) / len(trades) * 100, 1),
            'cumR_pct': round(R.sum() * 100, 2), 'PF': round(pf, 3),
            'payoff': round(payoff, 3), 'final_cap': round(float(cap), 2)}


def monthly(trades, side_filter):
    sub = [t for t in trades if t['side'] == side_filter]
    out = {}
    for t in sub:
        out.setdefault(t['month'], []).append(t['R'])
    rows = []
    for m in sorted(out.keys()):
        R = np.array(out[m]); wins = R[R > 0]; losses = R[R < 0]
        gl = -losses.sum()
        cap = START_CAP
        for r in R:
            cap *= (1 + r)
        rows.append({'month': m, 'side': 'LONG' if side_filter == 1 else 'SHORT',
                     'trades': len(R), 'win_pct': round(len(wins) / len(R) * 100, 1),
                     'cumR_pct': round(R.sum() * 100, 2),
                     'PF': round((wins.sum() / gl) if gl > 0 else 999.0, 3),
                     'payoff': round((wins.mean() / -losses.mean()) if (len(wins) and len(losses)) else 0.0, 3),
                     'pnl_usd': round(float(cap - START_CAP), 2)})
    return rows


def pick_best(runs, sl_mode):
    # 롱숏 분해가 의미있도록 BOTH 방향을 우선. BOTH 중 train PF 최고(거래>=15).
    # BOTH에 표본이 없으면 전체에서 차선택.
    best_both = None; best_any = None
    for r in runs:
        if r['sl_mode'] != sl_mode:
            continue
        if r['tr_trades'] >= 15:
            if best_any is None or r['tr_PF'] > best_any['tr_PF']:
                best_any = r
            if r['dir'] == 'BOTH' and (best_both is None or r['tr_PF'] > best_both['tr_PF']):
                best_both = r
    return best_both if best_both is not None else best_any


def main():
    print("[05Alpha_Up_Ch1_S4C_Vrfy_stg2] 눌림목봇 롱숏 + 피보 A/B 검증")
    data = find_data(); print(f"[data] {data}")
    df1m = load_1m(data)
    print(f"[load] {len(df1m):,}rows | {df1m.index.min().date()}~{df1m.index.max().date()}")

    # 사전계산 캐시: (tf, gate, adx_th) 별 1회
    sig_cache = {}
    for tf in GRID_TF:
        dd = resample_tf(df1m, tf)
        for gate in GRID_gate:
            for ath in (GRID_adxTh if gate == 'ADX_TREND' else [GRID_adxTh[0]]):
                sig_cache[(tf, gate, ath)] = (dd, precompute(dd, gate, ath))
        print(f"[tf {tf//60}h] {len(dd)} bars precomputed")

    combos = []
    for tf in GRID_TF:
        for rsiOS in GRID_rsiOS:
            for rsiOSs in GRID_rsiOSs:
                for gate in GRID_gate:
                    for ath in (GRID_adxTh if gate == 'ADX_TREND' else [GRID_adxTh[0]]):
                        for direction in GRID_dir:
                            for sl_mode in GRID_SLMODE:
                                combos.append((tf, rsiOS, rsiOSs, gate, ath, direction, sl_mode))
    print(f"[grid] {len(combos)} runs")

    summary_runs = []; trades_by_key = {}
    done = 0
    for (tf, rsiOS, rsiOSs, gate, ath, direction, sl_mode) in combos:
        dd, sig = sig_cache[(tf, gate, ath)]
        par = {'rsiOS': rsiOS, 'rsiOSs': rsiOSs, 'gate': gate, 'adx_th': ath,
               'dir': direction, 'sl_mode': sl_mode}
        trades = run_bot(dd, sig, par)
        lab = f"TF{tf//60}h_osL{rsiOS}_osS{rsiOSs}_{gate}_adx{ath}_{direction}"
        mTr = agg(trades, TRAIN_YEARS); mTe = agg(trades, TEST_YEARS)
        summary_runs.append({'sl_mode': sl_mode, 'cell': lab, 'TF_h': tf // 60,
                             'rsiOS': rsiOS, 'rsiOSs': rsiOSs, 'gate': gate, 'adx_th': ath, 'dir': direction,
                             'tr_trades': mTr['trades'], 'tr_PF': mTr['PF'], 'tr_cumR': mTr['cumR_pct'],
                             'te_trades': mTe['trades'], 'te_PF': mTe['PF'], 'te_cumR': mTe['cumR_pct']})
        trades_by_key[(sl_mode, lab)] = trades
        done += 1
        if done % 100 == 0:
            print(f"[progress] {done}/{len(combos)}")

    # A안/B안 best + 롱숏 분해 + 월별
    verdict_lines = []; best_meta = {}; scen_rows = []; monthly_rows = []
    for sl_mode in GRID_SLMODE:
        b = pick_best(summary_runs, sl_mode)
        tag = 'A_HIGH_BASE' if sl_mode == 'HIGH_BASE' else 'B_LOW_BASE'
        if b is None:
            verdict_lines.append(f"{tag}: 표본부족(train<15)")
            best_meta[sl_mode] = None
            for s in SCEN:
                scen_rows.append({'sl_mode': sl_mode, 'scen': s, 'n': 0, 'cumR': 0})
            continue
        bt = trades_by_key[(sl_mode, b['cell'])]
        m_tr = agg(bt, TRAIN_YEARS); m_te = agg(bt, TEST_YEARS)
        wfe = round((m_te['PF'] / m_tr['PF']) * 100, 1) if m_tr['PF'] > 0 else 0
        L = agg(bt, None, 1); S = agg(bt, None, -1)
        verdict_lines.append(
            f"{tag} BEST[{b['cell']}] train PF={m_tr['PF']} cumR={m_tr['cumR_pct']}% | test PF={m_te['PF']} cumR={m_te['cumR_pct']}% WFE={wfe}% "
            f"|| LONG n{L['trades']} 승{L['win_pct']}% R{L['cumR_pct']}% PF{L['PF']} 손익비{L['payoff']} ${L['final_cap']-START_CAP:.0f} "
            f"|| SHORT n{S['trades']} 승{S['win_pct']}% R{S['cumR_pct']}% PF{S['PF']} 손익비{S['payoff']} ${S['final_cap']-START_CAP:.0f}")
        best_meta[sl_mode] = {'b': b, 'bt': bt, 'L': L, 'S': S, 'tag': tag}
        # 시나리오 분해(전체기간)
        for s in SCEN:
            rs = [t['R'] for t in bt if t['scen'] == s]
            scen_rows.append({'sl_mode': sl_mode, 'scen': s, 'n': len(rs),
                              'cumR': round(float(np.sum(rs)) * 100, 2) if rs else 0.0})
        # 월별 롱/숏
        for row in monthly(bt, 1) + monthly(bt, -1):
            row['sl_mode'] = tag
            monthly_rows.append(row)

    # 최종 결론
    am = best_meta.get('HIGH_BASE'); bm = best_meta.get('LOW_BASE')
    if am and bm:
        a_te = am['b']['te_PF']; b_te = bm['b']['te_PF']
        if b_te > a_te:   concl = f"B(LOW_BASE 설계)가 우위 test PF {b_te} > {a_te} -> 알파상승"
        elif a_te > b_te: concl = f"A(HIGH_BASE 원본)가 우위 test PF {a_te} > {b_te}"
        else:             concl = f"A=B 동률 test PF {a_te}"
    else:
        concl = "한쪽 이상 표본부족 - 데이터/그리드 점검"
    verdict = "VERDICT: " + concl + " || " + " || ".join(verdict_lines)
    print("[verdict] " + verdict)

    # CSV 저장
    pd.DataFrame([{'cell': verdict}] + summary_runs).to_csv(
        os.path.join(HERE, "s4c_summary.csv"), index=False, encoding='utf-8-sig')

    all_td = []
    for sl_mode in GRID_SLMODE:
        meta = best_meta.get(sl_mode)
        if not meta: continue
        for t in meta['bt']:
            all_td.append({'sl_mode': meta['tag'], 'side': 'LONG' if t['side'] == 1 else 'SHORT',
                           'entry_t': t['entry_t'].strftime('%Y-%m-%d %H:%M'),
                           'exit_t': t['exit_t'].strftime('%Y-%m-%d %H:%M'),
                           'year': t['year'], 'month': t['month'],
                           'entry': round(t['entry'], 2), 'exit': round(t['exit'], 2),
                           'R_pct': round(t['R'] * 100, 4), 'reason': t['reason'], 'bars': t['bars'], 'scen': t['scen']})
    cols_td = ['sl_mode','side','entry_t','exit_t','year','month','entry','exit','R_pct','reason','bars','scen']
    (pd.DataFrame(all_td) if all_td else pd.DataFrame(columns=cols_td)).to_csv(
        os.path.join(HERE, "s4c_trades.csv"), index=False, encoding='utf-8-sig')

    cols_m = ['sl_mode','month','side','trades','win_pct','cumR_pct','PF','payoff','pnl_usd']
    (pd.DataFrame(monthly_rows)[cols_m] if monthly_rows else pd.DataFrame(columns=cols_m)).to_csv(
        os.path.join(HERE, "s4c_monthly.csv"), index=False, encoding='utf-8-sig')

    if not scen_rows:
        scen_rows = [{'sl_mode': m, 'scen': s, 'n': 0, 'cumR': 0} for m in GRID_SLMODE for s in SCEN]
    pd.DataFrame(scen_rows).to_csv(os.path.join(HERE, "s4c_scenarios.csv"), index=False, encoding='utf-8-sig')
    print("[save] s4c_summary / s4c_trades / s4c_monthly / s4c_scenarios .csv")


if __name__ == "__main__":
    main()
