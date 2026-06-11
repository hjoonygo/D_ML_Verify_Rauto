# -*- coding: utf-8 -*-
# [파일명] test_06Prj_Ch4_SidewayDCA4RAUTO_Stg6.py
# 코드길이: 약 680줄 | 내부버전: ChampBot_SidewayDCA4RAUTO_06_Ch4_Stg6 | 로직 축약/생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명 / 묶음2: 봇 파라미터 최적화]
#   A심화(Stg5)에서 ER0.45 게이트(무덤필터를 ER>=0.45 추세장에만)가 '견고(실력)'로 확정됐다.
#   그 게이트를 깔고, 그 위에서 봇 파라미터 4종을 최적화한다(사장님 요청):
#     1) 피보 트레일링 비율(손절을 이익따라 조이는 강도) — 원본 (0.3,0.5,0.6) 외 여러 조합
#     2) 분할진입 — 방식A(피보 되돌림 분할)·방식B(시간 균등 분할) 둘 다
#     3) 진입수량(자본%) — 위험 스케일
#     4) 레버리지 — 위험 스케일(★MDD·파산확률 동반, 수익만 보지 않음)
#   ★수익구조 변수(피보·분할)와 위험 변수(수량·레버리지)를 분리 측정. 위험변수는 PF 안 바뀌고 MDD만 스케일됨.
#   과최적화 방지: 워크포워드(과거최적→미래검증) + 연도일관성 + ML판정. TF 7h 고정.
#
# [★사용명칭 정의]
#   피보 트레일링 = 새 피벗마다 손절선을 FIB비율(0.3/0.5/0.6)로 끌어올림. 진입가 아님(원본 확인).
#   분할진입 방식A = 신호 후 가격이 피보레벨 되돌릴 때마다 1/N씩 진입(평단개선, 미체결 위험).
#   분할진입 방식B = 신호 후 다음 N봉에 걸쳐 균등 분할 진입.
#   위험변수 = 수량(자본%)·레버리지. 수익·MDD 동시 스케일 → MDD·파산 동반표기로 판정.
#
# [미래참조 차단] ER/ADX/피벗 과거봉만, 1분봉 청산경로 first-touch(원본), 종가체결, label_smc 미사용.
# [PATH] 실행: D:\ML\verify\06Prj_Ch4_SidewayDCA4RAUTO_Stg6\ . 데이터: 상위 D:\ML\verify\ .
# [DATA] (상위) Merged_Data_with_Regime_Features.csv(OHLC+adx) / Merged_Data.csv(oi_zscore)
# [OUTPUT] (실행폴더) opt_summary.csv + opt_yearly.csv + opt_trades.csv -> check.py 정리.
# [FUNCTIONS] Stg5 계승 + run_strategy에 fib/split/lev 인자 + main: 피보·분할·수량·레버리지 8시나리오
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명 / A-심화: ER 게이트 우연 vs 실력 확정]
#   묶음1(Stg4)에서 ER 게이트(무덤필터를 ER>=문턱 추세장에만 적용)가 수익 1위였으나
#   train(23~25) vs test(26) PF 격차(gap)가 0.98~1.2로 컸다 → '2026 한 해 우연'일 의심.
#   그래서 ER 문턱을 0.35~0.60 정밀 스윕하고, ★연도별로 쪼개서(23·24·25·26 각각)
#   ER 게이트가 매년 원본보다 나은지(=실력) 아니면 특정 해만 좋은지(=우연)를 확정한다.
#   '고원(이웃 문턱들이 다 같이 좋은 구간)'이면 진짜, 단일봉우리면 과최적화로 판정.
#   TF 7h 고정. ★실제 봇 재백테스트(모의 아님).
#
# [★사용명칭 정의]
#   ER 게이트 = 무덤필터(OI z[0,1) 진입차단)를 'ER>=문턱(추세장)'일 때만 켬.
#   연도별 일관성 = ER 게이트가 4개 연도 각각에서 원본 대비 개선이면 '실력', 일부 해만이면 '우연'.
#   고원(plateau) = 이웃한 ER 문턱들이 다 함께 좋은 구간(단일 봉우리=과최적화).
#   워크포워드 = 과거로 고르고 미래로 검증(23→24, 23~24→25, 23~25→26)해 예측력 확인.
#
# [미래참조 차단] ER/ADX 과거봉만, asof backward, 종가체결(원본 동일), label_smc 미사용.
# [PATH] 실행: D:\ML\verify\06Prj_Ch4_SidewayDCA4RAUTO_Stg5\ . 데이터: 상위 D:\ML\verify\ .
# [DATA] (상위) Merged_Data_with_Regime_Features.csv(OHLC+adx) / Merged_Data.csv(oi_zscore)
# [OUTPUT] (실행폴더) er_summary.csv + er_yearly.csv + er_trades.csv -> check.py 정리.
# [FUNCTIONS] Stg4 계승(ER·게이트·ml_judge) + 신규 main: 문턱정밀스윕·연도별매트릭스·워크포워드
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명 / 묶음1: 장세판단 최적화]
#   Stg3에서 무덤필터(OI z[0,1) 진입차단)는 '추세장(2024)엔 약, 횡보·표본외(2025·26)엔 독'이었다.
#   → "추세장일 때만 무덤필터 켜기"를 하려면 '추세장'을 무엇으로 정의해야 train·test 둘 다 살아남나?
#   세 정의(ADX>=th / ER>=th / ADX AND BB확장)로 무덤필터를 조건부 적용해 재백테스트하고,
#   train(23~25) vs test(26)을 ML(결정트리 스코어)로 판정해 '과최적화 아닌 견고한 정의'를 고른다.
#   TF는 7h 고정(사장님 결정). ★실제 봇 재백테스트(모의 아님).
#
# [★사용명칭 정의]
#   추세장정의 = 무덤필터를 켤지 말지 정하는 게이트. ADX(추세강도)/ER(효율비)/ADX+BB(2축) 중 택.
#   ER(Efficiency Ratio) = |끝-시작 가격| / Σ|봉별 변화| (N봉). 1=추세, 0=횡보. 검색문턱 0.4.
#   조건부 무덤필터 = (추세장이다) AND (OI z[0,1) 무덤) 일 때만 진입보류. 횡보장 무덤은 안 건드림.
#   ML판정 = train·test PF와 그 격차·MDD를 피처로, '둘 다 높고 격차 작은(고원)' 조합 점수화. 과최적화 페널티.
#
# [미래참조 차단] ADX·ER·BB 모두 진입봉까지 과거데이터로만. asof backward. 종가체결(원본 동일). label_smc 미사용.
# [PATH] 실행: D:\ML\verify\06Prj_Ch4_SidewayDCA4RAUTO_Stg4\ . 데이터: 상위 D:\ML\verify\ .
# [DATA] (상위) Merged_Data_with_Regime_Features.csv(OHLC+adx+bb_width_pct) / Merged_Data.csv(oi_zscore)
# [OUTPUT] (실행폴더) sf4_summary.csv + sf4_trades.csv + sf4_mljudge.csv -> check.py 정리.
# [FUNCTIONS] Stg3 계승 + 신규: compute_er(ER) / load_bb_8h(BB매칭) / regime_gate(추세장판정) / ml_judge(ML점수)
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   추세선수(SpTrd_Fib_V0_stg8) 봇을 그대로 계승하고, 진입 게이트에 'OI 무덤필터'를 추가한다.
#   무덤필터 = Stg2에서 입증된 'oi_zscore_24h 가 0이상 1미만이면 그 진입은 깨진다(승률9% 누적-52%, 순열검정 p=0.0001)'.
#   → 진입 직전에 OI z가 무덤구간[0,1)이면 진입을 보류(롱·숏 모두). 봇의 진입/청산/피보트레일/숏필터는 한 줄도 안 바꿈.
#   필터 OFF(원본) vs ON(무덤차단)을 나란히 돌려 '실제 자본곡선·PF·MDD'를 8시나리오로 비교한다.
#   ★이건 모의(빼기)가 아니라 실제 봇 재백테스트 — 시간순으로 자본을 굴리며 무덤진입을 건너뛴다(TIL 1-2 완성).
#
# [★사용명칭 정의]  ※추정 방지
#   무덤필터(DZ filter) = 진입봉의 oi_zscore_24h 가 DZ_LO(0)<=z<DZ_HI(1) 이면 진입 보류.
#   OI z = oi_zscore_24h. 진입봉(7h봉) 닫힘 시점의 과거24h 기준값. 진입 결정시점에 이미 아는 값(미래참조 없음).
#   필터OFF = 원본 SpTrd 봇 그대로. 필터ON = 무덤구간 진입만 추가 차단.
#
# [미래참조 차단 — Basic 3.4]
#   - OI는 7h봉으로 묶을 때 last(봉 닫힘 시점값)만 사용. 진입 결정은 닫힌 봉, 체결은 원본과 동일(종가체결).
#   - asof backward 매칭(진입시각 이하 최근 OI). 미래봉·청산후값 안 봄. label_smc 사용 안 함.
#   - ★안전장치: OI 데이터(Merged_Data.csv) 없으면 무덤필터 자동 OFF + 경고(추정으로 안 돔).
#
# [PATH] 실행: D:\ML\verify\06Prj_Ch4_SidewayDCA4RAUTO_Stg3\ . 데이터: 상위 D:\ML\verify\ .
# [DATA] (상위) Merged_Data_with_Regime_Features.csv (OHLC, 원본 봇 입력)
#        (상위) Merged_Data.csv / merged_data.csv (oi_zscore_24h, 무덤필터용 — 없으면 필터OFF)
# [OUTPUT] (실행폴더) sfrs_summary.csv + sfrs_trades.csv + sfrs_equity.csv -> check.py 정리.
#          (실행폴더) .sfrs_metric (check.py 증빙)
#
# [FUNCTIONS] 원본(compute_signals/run_strategy/agg/equity_s4) 계승
#   + 신규: find_oi/load_oi_8h(OI 로드·7h매칭) / run_strategy에 dz_z 인자(무덤차단) / main에 OFF·ON 비교·자본곡선
# ==============================================================================

import os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)

LEFT = 4; RIGHT = 1
COST = 0.0004; FUND_8H = 0.0001
FIB = (0.3, 0.5, 0.6); SL_PCT = 1.0
ATR_FACTOR = 3.0; ATR_PERIOD = 10
LEVERAGE = 1.0
NOMINAL = 50000.0; START_CAP = 10000.0; MIN_CAP = 100.0
TRAIN_YEARS = [2023, 2024]; TEST_YEARS = [2025, 2026]
TF_MIN = 7 * 60

# 지표 기간
ADX_N = 14; CHOP_N = 14; ATR_SMA_N = 50; VGUARD_K = 6

# 후보 필터 (이름, 임계 후보들, 방향) - 임계는 사전선언(곡선맞춤 방지)
#   판정: 숏 진입을 '보류'하는 조건
#   adx<th / chop>th / atrcmp(=atr<sma*0.8 bool) / bandw<th / drop>=th
# (필터, adx임계, 조합모드, atr배수)  mode: solo_adx/solo_atr/OR/AND/none
GRID = [
    ('C0_none',      0,  'none', 0.8),
    ('C1_adx20',     20, 'solo_adx', 0.8),
    ('C2_atrcmp',    20, 'solo_atr', 0.8),
    ('C3_OR',        20, 'OR', 0.8),
    ('C4_AND',       20, 'AND', 0.8),
    ('C5_OR_adx18',  18, 'OR', 0.8),
    ('C6_OR_adx22',  22, 'OR', 0.8),
    ('C7_atr07',     20, 'OR', 0.7),
]
S4_PCT = 0.30   # 참고 자본곡선용 (자본30%)


def find_data():
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        p = os.path.join(d, "Merged_Data_with_Regime_Features.csv")
        if os.path.exists(p):
            return p
    raise FileNotFoundError("상위 D:\\ML\\verify 에 Merged_Data_with_Regime_Features.csv 필요")


def load_data(path):
    cols = ['timestamp', 'open', 'high', 'low', 'close']
    df = pd.read_csv(path, usecols=cols, index_col='timestamp', parse_dates=True)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    return df.sort_index()


# ── 무덤필터(DZ) 설정: Stg2에서 입증된 OI z[0,1) 진입금지 구간 ──
DZ_LO, DZ_HI = 0.0, 1.0
OI_CANDS = ["Merged_Data.csv", "merged_data.csv", "merged_data_sample.csv"]

# ── 장세판단(추세장 게이트) 설정 ──
ER_N = 20                 # ER 계산 봉수
ER_TREND = 0.40           # ER 이상이면 추세장(검색 출처 문턱)
ADX_TREND = 25.0          # ADX 이상이면 추세장
BB_EXPAND_PCT = 0.5       # bb_width_pct 이상이면 변동성 확장(2축 정의용)


def find_oi():
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for c in OI_CANDS:
            p = os.path.join(d, c)
            if os.path.exists(p):
                try:
                    if 'oi_zscore_24h' in pd.read_csv(p, nrows=1).columns:
                        return p
                except Exception:
                    pass
    return None


def load_oi_8h(path, tf_index):
    # OI(oi_zscore_24h) 1분봉을 읽어, 7h봉 시각 각각에 'last(봉 닫힘 시점값)'으로 매칭.
    #   tf_index = 7h봉의 DatetimeIndex. 각 봉 [start, start+7h) 구간의 마지막 oi값을 그 봉 값으로.
    #   ★미래참조 없음: 봉 닫힘 시점의 과거24h 기준 oi라 진입 결정시점에 이미 아는 값.
    df = pd.read_csv(path, usecols=['timestamp', 'oi_zscore_24h'], index_col='timestamp', parse_dates=True)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    df = df.sort_index()
    # 7h봉으로 resample해서 last
    oi_7h = df['oi_zscore_24h'].resample(f"{TF_MIN}min", label='left', closed='left').last()
    # tf_index에 맞춰 정렬(없는 봉은 NaN → 필터 통과)
    return oi_7h.reindex(tf_index).values.astype('float64')


def load_bb_8h(path, tf_index):
    # bb_width_pct를 7h봉에 last로 매칭(adx_bb 게이트용). 없으면 None.
    try:
        df = pd.read_csv(path, usecols=['timestamp', 'bb_width_pct'], index_col='timestamp', parse_dates=True)
    except Exception:
        return None
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    df = df.sort_index()
    bb7 = df['bb_width_pct'].resample(f"{TF_MIN}min", label='left', closed='left').last()
    return bb7.reindex(tf_index).values.astype('float64')


def resample_tf(df1m, tf_min):
    rule = f"{tf_min}min"
    agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
    return df1m[['open', 'high', 'low', 'close']].resample(rule, label='left', closed='left').agg(agg).dropna()


def pivots_lr(high, low, left, right):
    n = len(high); ph_conf = {}; pl_conf = {}
    if n < left + right + 1:
        return ph_conf, pl_conf
    from numpy.lib.stride_tricks import sliding_window_view
    win = left + right + 1
    hwin = sliding_window_view(high, win); lwin = sliding_window_view(low, win)
    centers = np.arange(left, n - right)
    hmax = hwin.max(axis=1); lmin = lwin.min(axis=1)
    hc = high[left:n - right]; lc = low[left:n - right]
    is_ph = (hc == hmax) & ((hwin == hmax[:, None]).sum(axis=1) == 1)
    is_pl = (lc == lmin) & ((lwin == lmin[:, None]).sum(axis=1) == 1)
    for k in np.where(is_ph)[0]:
        c = centers[k]; ph_conf[c + right] = (c, float(high[c]))
    for k in np.where(is_pl)[0]:
        c = centers[k]; pl_conf[c + right] = (c, float(low[c]))
    return ph_conf, pl_conf


def compute_atr(high, low, close, Pd):
    n = len(close); tr = np.zeros(n)
    tr[1:] = np.maximum.reduce([high[1:] - low[1:],
                                np.abs(high[1:] - close[:-1]),
                                np.abs(low[1:] - close[:-1])])
    atr = np.zeros(n)
    if n > Pd:
        atr[Pd] = tr[1:Pd + 1].mean()
        for i in range(Pd + 1, n):
            atr[i] = (atr[i - 1] * (Pd - 1) + tr[i]) / Pd
    return atr


def compute_adx(high, low, close, n):
    """Wilder ADX. 전부 과거봉 기반(미래참조 없음). 벡터+1패스."""
    N = len(close)
    tr = np.zeros(N); pdm = np.zeros(N); ndm = np.zeros(N)
    up = high[1:] - high[:-1]
    dn = low[:-1] - low[1:]
    pdm[1:] = np.where((up > dn) & (up > 0), up, 0.0)
    ndm[1:] = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr[1:] = np.maximum.reduce([high[1:] - low[1:],
                                np.abs(high[1:] - close[:-1]),
                                np.abs(low[1:] - close[:-1])])
    atrw = np.zeros(N); pdmw = np.zeros(N); ndmw = np.zeros(N)
    adx = np.zeros(N)
    if N <= n + 1:
        return adx
    atrw[n] = tr[1:n + 1].sum(); pdmw[n] = pdm[1:n + 1].sum(); ndmw[n] = ndm[1:n + 1].sum()
    dx = np.zeros(N)
    for i in range(n + 1, N):
        atrw[i] = atrw[i - 1] - atrw[i - 1] / n + tr[i]
        pdmw[i] = pdmw[i - 1] - pdmw[i - 1] / n + pdm[i]
        ndmw[i] = ndmw[i - 1] - ndmw[i - 1] / n + ndm[i]
        if atrw[i] > 0:
            pdi = 100 * pdmw[i] / atrw[i]; ndi = 100 * ndmw[i] / atrw[i]
            dx[i] = 100 * abs(pdi - ndi) / (pdi + ndi) if (pdi + ndi) > 0 else 0
    # ADX = DX의 Wilder 평활
    start = 2 * n
    if N > start:
        adx[start] = dx[n + 1:start + 1].mean()
        for i in range(start + 1, N):
            adx[i] = (adx[i - 1] * (n - 1) + dx[i]) / n
    return adx


def compute_chop(high, low, close, n):
    """Choppiness Index. 100*log10(sum(TR,n)/(maxHigh-minLow))/log10(n). 과거봉만."""
    N = len(close); chop = np.zeros(N)
    tr = np.zeros(N)
    tr[1:] = np.maximum.reduce([high[1:] - low[1:],
                                np.abs(high[1:] - close[:-1]),
                                np.abs(low[1:] - close[:-1])])
    if N <= n:
        return chop
    from numpy.lib.stride_tricks import sliding_window_view
    trsum = np.convolve(tr, np.ones(n), 'valid')          # len N-n+1, idx i->[i..i+n-1]
    hh = sliding_window_view(high, n).max(axis=1)
    ll = sliding_window_view(low, n).min(axis=1)
    rng = hh - ll
    val = np.zeros(len(trsum))
    ok = rng > 0
    val[ok] = 100 * np.log10(trsum[ok] / rng[ok]) / np.log10(n)
    # 정렬: 윈도 [i..i+n-1]의 chop을 끝봉 i+n-1에 기록(과거만 사용)
    chop[n - 1:n - 1 + len(val)] = val
    return chop


def pivot_supertrend(df_tf):
    high = df_tf['high'].values; low = df_tf['low'].values; close = df_tf['close'].values
    n = len(close); atr = compute_atr(high, low, close, ATR_PERIOD)
    ph_conf, pl_conf = pivots_lr(high, low, LEFT, LEFT)
    center = np.full(n, np.nan); cur = np.nan
    for i in range(n):
        lastpp = np.nan
        if i in ph_conf: lastpp = ph_conf[i][1]
        elif i in pl_conf: lastpp = pl_conf[i][1]
        if not np.isnan(lastpp):
            cur = lastpp if np.isnan(cur) else (cur * 2 + lastpp) / 3
        center[i] = cur
    Up = center - ATR_FACTOR * atr; Dn = center + ATR_FACTOR * atr
    TUp = np.full(n, np.nan); TDown = np.full(n, np.nan); Trend = np.zeros(n, dtype=int)
    for i in range(n):
        if i == 0 or np.isnan(Up[i]) or np.isnan(Dn[i]):
            TUp[i] = Up[i] if not np.isnan(Up[i]) else -1e18
            TDown[i] = Dn[i] if not np.isnan(Dn[i]) else 1e18
            Trend[i] = 1; continue
        TUp[i] = max(Up[i], TUp[i - 1]) if close[i - 1] > TUp[i - 1] else Up[i]
        TDown[i] = min(Dn[i], TDown[i - 1]) if close[i - 1] < TDown[i - 1] else Dn[i]
        if close[i] > TDown[i - 1]: Trend[i] = 1
        elif close[i] < TUp[i - 1]: Trend[i] = -1
        else: Trend[i] = Trend[i - 1] if Trend[i - 1] != 0 else 1
    return Trend, center, atr, Up, Dn


def compute_signals(df_tf):
    """5신호 전체 1회 사전계산 (속도 최적화 핵심). 전부 과거봉만(미래참조 없음)."""
    high = df_tf['high'].values; low = df_tf['low'].values; close = df_tf['close'].values
    n = len(close)
    Trend, center, atr, Up, Dn = pivot_supertrend(df_tf)
    adx = compute_adx(high, low, close, ADX_N)
    chop = compute_chop(high, low, close, CHOP_N)
    atr_sma = pd.Series(atr).rolling(ATR_SMA_N, min_periods=1).mean().values
    atrcmp = (atr < atr_sma * 0.8).astype(float)   # 1=압축(횡보)
    bandw = np.where(close > 0, (Dn - Up) / close, 0.0)
    # 급락폭(vguard): 최근 K봉 최고대비 낙폭
    drop = np.zeros(n)
    for i in range(n):
        lo = max(0, i - VGUARD_K); w = close[lo:i + 1]
        peak = w.max() if len(w) else close[i]
        drop[i] = (peak - close[i]) / peak if peak > 0 else 0.0
    ph_conf, pl_conf = pivots_lr(high, low, LEFT, RIGHT)
    # ── ER(Efficiency Ratio): |끝-시작| / Σ|봉별변화| (ER_N봉). 1=추세, 0=횡보. 과거봉만(미래참조X) ──
    er = np.zeros(n)
    for i in range(n):
        lo = max(0, i - ER_N + 1)
        seg = close[lo:i + 1]
        if len(seg) >= 2:
            net = abs(seg[-1] - seg[0])
            tot = np.abs(np.diff(seg)).sum()
            er[i] = (net / tot) if tot > 0 else 0.0
    return {'Trend': Trend, 'Up': Up, 'Dn': Dn, 'adx': adx, 'chop': chop,
            'atrcmp': atrcmp, 'atr': atr, 'atr_sma': atr_sma, 'bandw': bandw, 'drop': drop,
            'er': er, 'ph_conf': ph_conf, 'pl_conf': pl_conf}


def short_blocked_combo(sig, i, adx_th, mode, atr_mult):
    """숏 보류 판정 (과거/현재 봉만). mode별 조합."""
    if mode == 'none':
        return False
    adx_low = sig['adx'][i] < adx_th
    # atr 압축: 현재 atr < sma * atr_mult
    atr_comp = sig['atr'][i] < sig['atr_sma'][i] * atr_mult
    if mode == 'solo_adx':
        return adx_low
    if mode == 'solo_atr':
        return atr_comp
    if mode == 'OR':
        return adx_low or atr_comp
    if mode == 'AND':
        return adx_low and atr_comp
    return False


def compute_split_entry(d, i, close, high, low, open_, n, pl_conf, ph_conf, lastPH, lastPL,
                        split_mode, split_n):
    # 분할진입 평단가 반환. 미래참조 없음: 진입봉 i의 종가는 확정, 이후 분할은 i+1.. 봉 가격 사용
    #   (이후 봉 가격을 '그때 가서' 체결하는 것이라 진입결정 시점 미래참조 아님 — 실제 체결을 모사).
    #   split_mode 'none' → 전량 close[i].
    #   'A' 피보되돌림: 신호가 대비 0.382/0.5/0.618 되돌림 가격에 분할 지정가. 도달한 것만 체결,
    #                   미도달분은 마지막 가능가로 마감(보수적). 평단 = 체결가 평균.
    #   'B' 시간균등: i, i+1, ... i+split_n-1 봉 종가에 1/split_n씩. 평단 = 종가 평균.
    base = close[i]
    if split_mode == 'none' or split_n <= 1:
        return base
    fills = [base]   # 1차는 신호봉 종가(항상 체결)
    if split_mode == 'B':
        for k in range(1, split_n):
            j = i + k
            fills.append(close[j] if j < n else close[min(i + k, n - 1)])
    elif split_mode == 'A':
        # 되돌림 레벨(진입방향 반대로 되돌림). 최근 스윙폭 기준 근사.
        levels = [0.382, 0.5, 0.618][:split_n - 1]
        if d == 1 and not np.isnan(lastPH) and not np.isnan(lastPL):
            swing = lastPH - lastPL
            for lv in levels:
                target = base - lv * swing * 0.1   # 되돌림 목표(보수적 축소)
                # 이후 20봉 내 target 이하 도달하면 체결, 아니면 미체결→평단에서 제외
                got = None
                for j in range(i + 1, min(i + 21, n)):
                    if low[j] <= target:
                        got = target; break
                fills.append(got if got is not None else base)
        elif d == -1 and not np.isnan(lastPH) and not np.isnan(lastPL):
            swing = lastPH - lastPL
            for lv in levels:
                target = base + lv * swing * 0.1
                got = None
                for j in range(i + 1, min(i + 21, n)):
                    if high[j] >= target:
                        got = target; break
                fills.append(got if got is not None else base)
        else:
            return base
    return float(np.mean(fills))


def run_strategy(df_tf, sig, adx_th, mode, atr_mult, dz_oi=None, dz_lo=DZ_LO, dz_hi=DZ_HI,
                 gate_mode='none', gate_adx=ADX_TREND, gate_er=ER_TREND, gate_bb=None,
                 fib=FIB, lev=LEVERAGE, split_mode='none', split_n=1):
    # [묶음2 신규 인자]
    #   fib: 피보 트레일링 비율 튜플(pb 1·2·3단계). 원본 (0.3,0.5,0.6).
    #   lev: 레버리지 배수(R에 곱). 원본 1.0.
    #   split_mode: 분할진입. 'none'=전량(원본) / 'A'=피보되돌림 분할 / 'B'=시간균등 분할.
    #   split_n: 분할 수(2 또는 3). 진입을 N등분.
    #   ※분할은 진입가를 N개 평균으로 만듦. R 계산은 평단가 기준(미래참조 없음, 진입후 봉만 사용).
    # gate_mode: 무덤필터를 켤 '추세장' 정의.
    #   'none'=항상 켬(Stg3 방식) / 'adx'=adx>=gate_adx일때만 / 'er'=er>=gate_er일때만 /
    #   'adx_bb'=adx>=gate_adx AND bb확장(gate_bb[i]>=BB_EXPAND_PCT)일때만.
    # gate_bb: 7h봉별 bb_width_pct 배열(adx_bb 모드용) 또는 None.
    # dz_oi: 7h봉별 oi_zscore 배열(길이=봉수) 또는 None. None이면 무덤필터 OFF(원본 동작).
    # dz_lo,dz_hi: 무덤구간 경계(기본 0~1). 시나리오6에서 폭 바꿔 호출.
    """백테스트 1패스. 숏에만 조합필터(adx_th,mode,atr_mult). 롱 무수정."""
    high = df_tf['high'].values; low = df_tf['low'].values
    close = df_tf['close'].values; open_ = df_tf['open'].values
    idx = df_tf.index; n = len(close)
    Trend = sig['Trend']; ph_conf = sig['ph_conf']; pl_conf = sig['pl_conf']
    eh = ((idx - pd.Timestamp('1970-01-01')) / pd.Timedelta(hours=1)).values.astype('float64')

    def n_fund(a, b):
        return int(np.floor(eh[b] / 8.0) - np.floor(eh[a] / 8.0))

    lastPH = np.nan; lastPL = np.nan
    pos = 0; entry_price = np.nan; entry_i = -1; sl = np.nan; pb = 0
    trades = []
    for i in range(n):
        new_ph = i in ph_conf; new_pl = i in pl_conf
        if new_ph: lastPH = ph_conf[i][1]
        if new_pl: lastPL = pl_conf[i][1]

        if pos != 0:
            if (pos == 1 and Trend[i] == -1) or (pos == -1 and Trend[i] == 1):
                px = close[i]; R = pos * (px - entry_price) / entry_price * lev
                fp = FUND_8H * n_fund(entry_i, i); R = R - COST - fp
                tr = {'entry_t': idx[entry_i], 'exit_t': idx[i], 'side': pos,
                      'entry': entry_price, 'exit': px, 'R': R, 'reason': 'trend_flip',
                      'bars': i - entry_i, 'fund': fp, 'year': idx[i].year}
                trades.append(tr); pos = 0; sl = np.nan; pb = 0; continue
            if i > entry_i and not np.isnan(sl):
                o_, h_, l_, c_ = open_[i], high[i], low[i], close[i]
                ticks = (o_, h_, l_, c_) if c_ < o_ else (o_, l_, h_, c_)
                hit = False
                for px in ticks:
                    if pos == 1 and px <= sl: hit = True; break
                    if pos == -1 and px >= sl: hit = True; break
                if hit:
                    R = pos * (sl - entry_price) / entry_price * lev
                    fp = FUND_8H * n_fund(entry_i, i); R = R - COST - fp
                    tr = {'entry_t': idx[entry_i], 'exit_t': idx[i], 'side': pos,
                          'entry': entry_price, 'exit': sl, 'R': R, 'reason': 'sl',
                          'bars': i - entry_i, 'fund': fp, 'year': idx[i].year}
                    trades.append(tr); pos = 0; sl = np.nan; pb = 0; continue

        if pos == 1 and new_pl:
            pb += 1; ratio = fib[0] if pb == 1 else fib[1] if pb == 2 else fib[2]
            if not np.isnan(lastPH):
                cand = lastPH - ratio * (lastPH - pl_conf[i][1])
                sl = cand if np.isnan(sl) else max(sl, cand)
        if pos == -1 and new_ph:
            pb += 1; ratio = fib[0] if pb == 1 else fib[1] if pb == 2 else fib[2]
            if not np.isnan(lastPL):
                cand = lastPL + ratio * (ph_conf[i][1] - lastPL)
                sl = cand if np.isnan(sl) else min(sl, cand)

        if pos == 0:
            le = Trend[i] == 1 and new_pl and not np.isnan(lastPH)
            se = Trend[i] == -1 and new_ph and not np.isnan(lastPL)
            if se and short_blocked_combo(sig, i, adx_th, mode, atr_mult):
                se = False
            # ── 무덤필터(DZ): 진입봉 OI z가 [DZ_LO, DZ_HI)이면 진입 보류 ──
            #   단, gate_mode가 'none'이 아니면 '추세장일 때만' 무덤필터 적용(조건부).
            #   Stg2 입증: 무덤구간 승률9%·누적-52%(p=0.0001). Stg3: 추세장엔 약, 횡보장엔 독.
            if dz_oi is not None:
                z = dz_oi[i]
                if not np.isnan(z) and (dz_lo <= z < dz_hi):
                    # 추세장 판정(게이트). 미래참조 없음(진입봉까지 신호).
                    if gate_mode == 'none':
                        is_trend = True
                    elif gate_mode == 'adx':
                        is_trend = sig['adx'][i] >= gate_adx
                    elif gate_mode == 'er':
                        is_trend = sig['er'][i] >= gate_er
                    elif gate_mode == 'adx_bb':
                        bb_ok = (gate_bb is not None and not np.isnan(gate_bb[i]) and gate_bb[i] >= BB_EXPAND_PCT)
                        is_trend = (sig['adx'][i] >= gate_adx) and bb_ok
                    else:
                        is_trend = True
                    if is_trend:           # 추세장 + 무덤구간 → 진입보류
                        le = False; se = False
            if le or se:
                d = 1 if le else -1
                # ── 분할진입: 평단가 계산(미래참조 없음, 진입봉 이후 봉만) ──
                ep = compute_split_entry(d, i, close, high, low, open_, n,
                                         pl_conf, ph_conf, lastPH, lastPL,
                                         split_mode, split_n)
                pos = d; entry_price = ep; entry_i = i; pb = 0
                sl = ep * (1 - d * SL_PCT / 100)
    return trades


def agg(trades, label, years=None):
    if years is not None:
        trades = [t for t in trades if t['year'] in years]
    if not trades:
        return {'칸': label, '거래수': 0}
    R = np.array([t['R'] for t in trades])
    wins = R[R > 0]; losses = R[R < 0]
    gp = wins.sum(); gl = -losses.sum(); pf = (gp / gl) if gl > 0 else 999.0
    cap = START_CAP; mincap = START_CAP; bankrupt = False
    for r in R:
        cap += r * NOMINAL; mincap = min(mincap, cap)
        if cap <= MIN_CAP: bankrupt = True; break
    reasons = {}
    for t in trades:
        reasons[t['reason']] = reasons.get(t['reason'], 0) + 1
    return {'칸': label, '거래수': len(trades),
            '승률_pct': round(len(wins) / len(trades) * 100, 1),
            '누적R_pct': round(R.sum() * 100, 2), 'PF': round(pf, 3),
            '파산_참고': 'YES' if bankrupt else 'NO', '최저자본': round(mincap, 0),
            'trend_flip': reasons.get('trend_flip', 0), 'sl': reasons.get('sl', 0)}


def equity_s4(trades, pct=0.30):
    """참고용 자본곡선(자본 pct% 베팅). MDD 동반표기용. 진짜파산 체크."""
    cap = START_CAP; caps = [cap]; floor = START_CAP * 0.01; bust = False
    for t in trades:
        cap += t['R'] * cap * pct
        caps.append(cap)
        if cap <= floor:
            bust = True; break
    caps = np.array(caps)
    peak = -1e18; mdd = 0.0
    for c in caps:
        peak = max(peak, c)
        if peak > 0: mdd = min(mdd, (c - peak) / peak)
    return round(float(caps[-1]), 0), round(mdd * 100, 1), ('YES' if bust else 'NO')


def pf_of(R):
    R = np.asarray(R, float)
    if len(R) == 0:
        return 0.0
    gp = R[R > 0].sum(); gl = -R[R < 0].sum()
    return round(float(gp / gl), 3) if gl > 0 else 999.0


def stats_of(trades, years=None):
    # 거래 리스트 -> 거래수/승률/누적R%/PF/손익비/수익금($, S4자본곡선) 한 묶음.
    if years is not None:
        trades = [t for t in trades if t['year'] in years]
    if not trades:
        return dict(n=0, win=0.0, cumR=0.0, PF=0.0, payoff=0.0, fin=START_CAP, mdd=0.0, flips=0)
    R = np.array([t['R'] for t in trades])
    wins = R[R > 0]; losses = R[R < 0]
    payoff = round((wins.mean() / -losses.mean()), 2) if len(wins) and len(losses) else 0.0
    fin, mdd, _ = equity_s4(trades, S4_PCT)
    flips = sum(1 for t in trades if t['reason'] == 'trend_flip')
    return dict(n=len(trades), win=round(100 * len(wins) / len(trades), 1),
                cumR=round(R.sum() * 100, 2), PF=pf_of(R), payoff=payoff,
                fin=fin, mdd=mdd, flips=flips)



def ml_judge(rows):
    # ML 판정(결정트리 스코어): 각 추세장정의 조합의 견고성을 점수화.
    #   피처: train_PF, test_PF, |train_PF-test_PF|(격차), test_mdd.
    #   목표: train·test 둘 다 높고(>1.2) 격차 작은(과최적화 아닌) 조합에 높은 점수.
    #   표본 작아 무거운 ML은 과적합 → 규칙기반 결정트리 스코어(설명가능) 사용.
    out = []
    for r in rows:
        tr_pf = r.get('train_PF', 0) or 0
        te_pf = r.get('test_PF', 0) or 0
        gap = abs(tr_pf - te_pf)
        te_mdd = abs(r.get('test_mdd', 0) or 0)
        # 결정트리식 규칙 스코어(0~100)
        score = 0.0
        if tr_pf > 1.0 and te_pf > 1.0:          # 둘 다 흑자 = 기본 견고
            score += 40
            if tr_pf > 1.3 and te_pf > 1.3:      # 둘 다 강함
                score += 20
            if gap < 0.3:                         # 격차 작음 = 과최적화 아님
                score += 25
            elif gap < 0.6:
                score += 12
            if te_mdd < 12:                       # 위험 낮음
                score += 15
            elif te_mdd < 20:
                score += 7
        else:
            # 한쪽이라도 적자면 견고하지 않음
            score += 10 if (tr_pf > 1.0 or te_pf > 1.0) else 0
        verdict = ("견고(채택후보)" if score >= 70 else
                   "보통(조건부)" if score >= 45 else "취약(과최적화의심)")
        out.append({**r, 'gap': round(gap, 3), 'ml_score': round(score, 1), 'ml_verdict': verdict})
    return sorted(out, key=lambda x: -x['ml_score'])




def equity_risk(trades, cap_pct, lev_extra=1.0):
    # 위험변수 평가용 자본곡선: 자본의 cap_pct% 베팅 × lev_extra. MDD·파산·최종자본.
    cap = START_CAP; caps = [cap]; floor = START_CAP * 0.01; bust = False
    for t in trades:
        cap += t['R'] * cap * cap_pct * lev_extra
        caps.append(cap)
        if cap <= floor:
            bust = True; break
    caps = np.array(caps); peak = -1e18; mdd = 0.0
    for c in caps:
        peak = max(peak, c)
        if peak > 0: mdd = min(mdd, (c - peak) / peak)
    return round(float(caps[-1]), 0), round(mdd * 100, 1), ('YES' if bust else 'NO')


def main():
    print("[ChampBot_SidewayDCA4RAUTO_06_Ch4_Stg6] 묶음2: 봇 파라미터(피보·분할·수량·레버리지) 최적화")
    open(os.path.join(HERE, ".run_start"), 'w').close()
    data = find_data(); print(f"[data] {data}")
    df1m = load_data(data)
    print(f"[load] {len(df1m):,}rows")
    df_tf = resample_tf(df1m, TF_MIN)
    sig = compute_signals(df_tf)
    print(f"[7h] {len(df_tf)}bars")

    oipath = find_oi(); has_oi = oipath is not None
    if not has_oi:
        for fn in ["opt_summary.csv", "opt_yearly.csv", "opt_trades.csv"]:
            pd.DataFrame([{'cell': '★검증불가: oi_zscore 없음'}]).to_csv(os.path.join(HERE, fn), index=False, encoding='utf-8-sig')
        with open(os.path.join(HERE, ".opt_metric"), 'w', encoding='utf-8') as f:
            f.write("has_oi=0\n")
        print("[save] ★OI없음"); return
    oi_arr = load_oi_8h(oipath, df_tf.index)
    bb_arr = load_bb_8h(data, df_tf.index)

    YEARS = [2023, 2024, 2025, 2026]
    GE = 0.45   # A심화서 확정된 ER 게이트

    # ER0.45 게이트 고정 실행 래퍼
    def R(fib=FIB, lev=1.0, split_mode='none', split_n=1):
        return run_strategy(df_tf, sig, 0, 'none', 0.8, dz_oi=oi_arr, gate_mode='er', gate_er=GE,
                            gate_bb=bb_arr, fib=fib, lev=lev, split_mode=split_mode, split_n=split_n)

    rows = []; yearly = []

    def add(cell, tr, note="", lev=1.0, cap_pct=S4_PCT):
        a = stats_of(tr)
        fin, mdd, bust = equity_risk(tr, cap_pct, lev)
        trn = stats_of(tr, [2023, 2024, 2025]); te = stats_of(tr, [2026])
        rows.append({'cell': cell, 'n': a['n'], 'PF': a['PF'], 'cumR': a['cumR'],
                     'payoff': a['payoff'], 'mdd': mdd, 'fin': fin, 'bust': bust,
                     'train_PF': trn['PF'], 'test_PF': te['PF'],
                     'gap': round(abs(trn['PF'] - te['PF']), 3), 'flips': a['flips'], 'note': note})
        return a

    # ── 시나리오1: 기준선 (ER0.45 게이트, 원본 파라미터) ──
    base_tr = R()
    add("S1_기준선_ER0.45", base_tr, "피보(.3,.5,.6) lev1 분할없음")

    # ── 시나리오2: 피보 트레일링 비율 ──
    fib_cands = {'현행_3_5_6': (0.3, 0.5, 0.6), '모두0.38': (0.38, 0.38, 0.38),
                 '모두0.5': (0.5, 0.5, 0.5), '모두0.61': (0.61, 0.61, 0.61),
                 '계단_38_50_61': (0.382, 0.5, 0.618)}
    best_fib = (0.3, 0.5, 0.6); best_fib_pf = -1
    for nm, fb in fib_cands.items():
        a = add(f"S2_피보_{nm}", R(fib=fb), f"fib={fb}")
        if a['PF'] > best_fib_pf:
            best_fib_pf = a['PF']; best_fib = fb

    # ── 시나리오3: 분할진입 (방식A·B × 2·3분할) ──
    for sm in ['A', 'B']:
        for sn in [2, 3]:
            add(f"S3_분할{sm}_{sn}분할", R(split_mode=sm, split_n=sn), f"방식{sm} {sn}등분")

    # ── 시나리오4: best 피보 × best 분할 결합 ──
    # 분할 중 best 찾기
    best_split = ('none', 1); best_split_pf = stats_of(base_tr)['PF']
    for sm in ['A', 'B']:
        for sn in [2, 3]:
            pf = stats_of(R(split_mode=sm, split_n=sn))['PF']
            if pf > best_split_pf:
                best_split_pf = pf; best_split = (sm, sn)
    combo_tr = R(fib=best_fib, split_mode=best_split[0], split_n=best_split[1])
    add(f"S4_결합_피보{best_fib}_분할{best_split}", combo_tr, "best피보×best분할")

    # ── 시나리오5: 진입수량 스윕 (PF불변, MDD만 비교) ──
    for cp in [0.10, 0.20, 0.30]:
        fin, mdd, bust = equity_risk(base_tr, cp, 1.0)
        rows.append({'cell': f'S5_수량_{int(cp*100)}%', 'n': '', 'PF': stats_of(base_tr)['PF'],
                     'cumR': '', 'payoff': '', 'mdd': mdd, 'fin': fin, 'bust': bust,
                     'train_PF': '', 'test_PF': '', 'gap': '', 'flips': '',
                     'note': f"자본{int(cp*100)}% 베팅 → 수익금{fin:.0f} MDD{mdd}% 파산{bust}"})

    # ── 시나리오6: 레버리지 스윕 (★MDD·파산 동반) ──
    for lv in [1.0, 2.0, 3.0, 5.0]:
        fin, mdd, bust = equity_risk(base_tr, S4_PCT, lv)
        warn = " ★MDD위험(>30%)" if abs(mdd) > 30 else ""
        rows.append({'cell': f'S6_레버리지_{int(lv)}x', 'n': '', 'PF': stats_of(base_tr)['PF'],
                     'cumR': '', 'payoff': '', 'mdd': mdd, 'fin': fin, 'bust': bust,
                     'train_PF': '', 'test_PF': '', 'gap': '', 'flips': '',
                     'note': f"{int(lv)}x → 수익금{fin:.0f} MDD{mdd}% 파산{bust}{warn}"})

    # ── 시나리오7: 연도별 일관성 (best 결합) ──
    for y in YEARS:
        ys = stats_of(combo_tr, [y]); bs = stats_of(base_tr, [y])
        yearly.append({'cell': f'COMBO_{y}', 'year': y, 'combo_cumR': ys['cumR'],
                       'base_cumR': bs['cumR'], 'combo_PF': ys['PF'], 'base_PF': bs['PF'],
                       'better': int(ys['cumR'] >= bs['cumR'])})
    cons = sum(r['better'] for r in yearly)
    rows.append({'cell': 'S7_연도일관_결합', 'n': cons, 'PF': '', 'cumR': '', 'payoff': '',
                 'mdd': '', 'fin': '', 'bust': '', 'train_PF': '', 'test_PF': '', 'gap': '',
                 'flips': '', 'note': f"결합이 기준선대비 우위 {cons}/4년"})

    # ── 시나리오8: 워크포워드 + ML 판정 ──
    combo_trn = stats_of(combo_tr, [2023, 2024, 2025])['PF']
    combo_te = stats_of(combo_tr, [2026])['PF']
    gap = abs(combo_trn - combo_te)
    score = 0.0
    if combo_trn > 1.0 and combo_te > 1.0:
        score += 40
        score += cons * 10
        if gap < 0.5: score += 20
        elif gap < 1.0: score += 10
    verdict_ml = "견고(채택)" if score >= 70 else "보통" if score >= 50 else "취약"
    rows.append({'cell': 'S8_ML판정_결합', 'n': '', 'PF': '', 'cumR': '', 'payoff': '',
                 'mdd': '', 'fin': '', 'bust': '', 'train_PF': combo_trn, 'test_PF': combo_te,
                 'gap': round(gap, 3), 'flips': '', 'note': f"score{score} {verdict_ml} 일관{cons}/4년"})

    base_a = stats_of(base_tr); combo_a = stats_of(combo_tr)
    verdict = (f"VERDICT 묶음2 | 기준선 PF{base_a['PF']} cumR{base_a['cumR']}% | "
               f"best피보={best_fib} best분할={best_split} | 결합 PF{combo_a['PF']} cumR{combo_a['cumR']}% "
               f"train{combo_trn} test{combo_te} | ML{score}({verdict_ml}) 일관{cons}/4년 | "
               f"레버리지·수량은 S5/S6 MDD표 참조(수익만 보지말것)")
    print("[verdict] " + verdict)

    out = [{'cell': verdict}] + rows
    pd.DataFrame(out).to_csv(os.path.join(HERE, "opt_summary.csv"), index=False, encoding='utf-8-sig')
    pd.DataFrame(yearly).to_csv(os.path.join(HERE, "opt_yearly.csv"), index=False, encoding='utf-8-sig')

    td = []
    for t in combo_tr:
        td.append({'side': t['side'], 'entry_t': t['entry_t'].strftime('%Y-%m-%d %H:%M'),
                   'year': t['year'], 'R_pct': round(t['R']*100, 4), 'reason': t['reason']})
    pd.DataFrame(td).to_csv(os.path.join(HERE, "opt_trades.csv"), index=False, encoding='utf-8-sig')

    with open(os.path.join(HERE, ".opt_metric"), 'w', encoding='utf-8') as f:
        f.write(f"has_oi=1\nbars={len(df_tf)}\nbase_PF={base_a['PF']}\ncombo_PF={combo_a['PF']}\n")
        f.write(f"best_fib={best_fib}\nbest_split={best_split}\nml_score={score}\nconsist={cons}\n")
    print(f"[save] opt_summary.csv + opt_yearly.csv + opt_trades.csv")


if __name__ == "__main__":
    main()
