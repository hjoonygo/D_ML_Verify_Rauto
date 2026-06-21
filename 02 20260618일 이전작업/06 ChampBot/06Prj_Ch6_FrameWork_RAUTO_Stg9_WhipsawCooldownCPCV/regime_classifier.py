# -*- coding: utf-8 -*-
# [파일명] regime_classifier.py
# 코드길이: 약 200줄 | 내부버전: 06Prj_Ch6_Stg3_RegimeClassifier_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 모듈이 하는 일 — 고딩 설명]
#   목적: 매 시점(봉)을 4국면으로 분류하는 '독립 장세판단 모듈'. 앞으로 만들 모든 알파가 공유할 토대.
#   4국면: 0=상승장(uptrend) 1=하락장(downtrend) 2=변동레인지(volatile_range) 3=죽은레인지(dead_range)
#
#   [표준 근거 — 검색 출처]
#     · CHOP(Choppiness): 61.8 이상=횡보/칩, 38.2 이하=추세 (피보나치 비율, TradingView/Money365/Positioned)
#     · ADX: 25 이상=추세, 20 이하=약/횡보 (Mind Math Money, StatOasis). 암호화폐는 30까지 상향 가능.
#     · Kaufman ER: 높으면 방향성(추세), 낮으면 choppy (Pointalgo Regime Switching = ADX+ER 조합이 표준).
#     · BB폭<4% = 압축/죽은장 (Collin Seow). 4지표 중 최소 3개 일치 시 'Trending' 다수결.
#
#   [방향 판정 = 가중합 (사장님 확정: 다 = DI와 기울기 둘 다, 가중치 w로 섞음)]
#     dir_score = w*DI신호 + (1-w)*기울기신호   (둘 다 -1~+1 정규화). w=1이면 DI만, w=0이면 기울기만.
#
#   [강도 판정 = 다수결] 4개 추세표(ADX>임계 / CHOP<임계 / ER>임계 / ATR비율>1) 중 vote_n개 이상이면 '추세장'.
#     추세장이면 dir_score 부호로 상승/하락. 추세장 아니면 '레인지' → BB폭<bb_dead면 죽은레인지, 아니면 변동레인지.
#
#   [Lookahead 차단] 모든 지표는 과거봉만 사용(Wilder/rolling/기울기는 i-k..i). 미래 정보 없음.
#                    ※ 정답지 label_smc_8은 이 모듈에 절대 입력 안 함 — 채점(혼동행렬)에서만 외부 사용.
#
# [In] OHLC numpy 배열 + params(dict)   [Out] regime 정수배열(0/1/2/3) + 개별 지표·점수(디버그/ML특징용)
# [사용 함수] wilder_atr / adx_di(adx,+DI,-DI) / choppiness / efficiency_ratio / bb_width_pct / atr_ratio
#             / norm_clip(정규화) / classify(메인) / feature_matrix(ML특징표)
# ==============================================================================
import numpy as np

REGIME_NAMES = {0: 'uptrend', 1: 'downtrend', 2: 'volatile_range', 3: 'dead_range'}
NAME2INT = {v: k for k, v in REGIME_NAMES.items()}

# ── 표준 기본 파라미터(검색 근거). grid에서 일부를 흔들어 검증. ──
DEFAULT_PARAMS = dict(
    adx_n=14, chop_n=14, er_n=10, bb_n=20, bb_k=2.0, atr_n=14, atr_sma_n=20, slope_n=10,
    w=0.5,              # 방향 가중치(DI vs 기울기) — grid: 0.0/0.25/0.5/0.75/1.0
    chop_hi=61.8, chop_lo=38.2,   # CHOP 표준 임계
    adx_hi=25.0, adx_lo=20.0,     # ADX 표준 임계
    er_hi=0.40,                   # ER 추세표 임계
    bb_dead=4.0,                  # BB폭% < 4 = 죽은장(압축)
    vote_n=3,                     # 4표 중 추세 확정에 필요한 표수
    min_hold=0,                   # 휩쏘 방지: 국면 유지 최소봉(0=off)
)


def wilder_atr(high, low, close, n):
    N = len(close); tr = np.zeros(N)
    tr[0] = high[0] - low[0]
    for i in range(1, N):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    atr = np.zeros(N)
    if N <= n:
        return atr, tr
    atr[n] = tr[1:n + 1].mean()
    for i in range(n + 1, N):
        atr[i] = (atr[i - 1] * (n - 1) + tr[i]) / n
    return atr, tr


def adx_di(high, low, close, n):
    # Wilder ADX + +DI/-DI (표준). 과거봉만 사용.
    N = len(close)
    plus_dm = np.zeros(N); minus_dm = np.zeros(N); tr = np.zeros(N)
    for i in range(1, N):
        up = high[i] - high[i - 1]; dn = low[i - 1] - low[i]
        plus_dm[i] = up if (up > dn and up > 0) else 0.0
        minus_dm[i] = dn if (dn > up and dn > 0) else 0.0
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    atrw = np.zeros(N); pdmw = np.zeros(N); ndmw = np.zeros(N)
    pdi = np.zeros(N); ndi = np.zeros(N); dx = np.zeros(N); adx = np.zeros(N)
    if N <= n + 1:
        return adx, pdi, ndi
    atrw[n] = tr[1:n + 1].sum(); pdmw[n] = plus_dm[1:n + 1].sum(); ndmw[n] = minus_dm[1:n + 1].sum()
    for i in range(n + 1, N):
        atrw[i] = atrw[i - 1] - atrw[i - 1] / n + tr[i]
        pdmw[i] = pdmw[i - 1] - pdmw[i - 1] / n + plus_dm[i]
        ndmw[i] = ndmw[i - 1] - ndmw[i - 1] / n + minus_dm[i]
        if atrw[i] > 0:
            pdi[i] = 100 * pdmw[i] / atrw[i]; ndi[i] = 100 * ndmw[i] / atrw[i]
            s = pdi[i] + ndi[i]
            dx[i] = 100 * abs(pdi[i] - ndi[i]) / s if s > 0 else 0.0
    start = 2 * n
    if start < N:
        adx[start] = dx[n + 1:start + 1].mean()
        for i in range(start + 1, N):
            adx[i] = (adx[i - 1] * (n - 1) + dx[i]) / n
    return adx, pdi, ndi


def choppiness(high, low, close, n):
    N = len(close); chop = np.zeros(N)
    _, tr = wilder_atr(high, low, close, n)
    for i in range(n, N):
        atr_sum = tr[i - n + 1:i + 1].sum()
        hh = high[i - n + 1:i + 1].max(); ll = low[i - n + 1:i + 1].min()
        rng = hh - ll
        if rng > 0 and atr_sum > 0:
            chop[i] = 100 * np.log10(atr_sum / rng) / np.log10(n)
    return chop


def efficiency_ratio(close, n):
    N = len(close); er = np.zeros(N)
    for i in range(n, N):
        net = abs(close[i] - close[i - n])
        tot = np.abs(np.diff(close[i - n:i + 1])).sum()
        er[i] = (net / tot) if tot > 0 else 0.0
    return er


def bb_width_pct(close, n, k):
    # 볼린저밴드 폭% = (상단-하단)/중앙*100. 과거 n봉.
    N = len(close); bw = np.zeros(N)
    for i in range(n - 1, N):
        win = close[i - n + 1:i + 1]
        ma = win.mean(); sd = win.std()
        if ma > 0:
            bw[i] = (2 * k * sd) / ma * 100
    return bw


def atr_ratio(atr, sma_n):
    N = len(atr); r = np.ones(N)
    s = np.zeros(N)
    for i in range(N):
        lo = max(0, i - sma_n + 1)
        s[i] = atr[lo:i + 1].mean()
        r[i] = atr[i] / s[i] if s[i] > 0 else 1.0
    return r


def norm_clip(x, scale):
    # -1~+1 정규화(부드럽게): tanh(x/scale)
    return np.tanh(x / scale) if scale > 0 else np.sign(x)


def compute_indicators(o, h, l, c, P):
    adx, pdi, ndi = adx_di(h, l, c, P['adx_n'])
    chop = choppiness(h, l, c, P['chop_n'])
    er = efficiency_ratio(c, P['er_n'])
    bw = bb_width_pct(c, P['bb_n'], P['bb_k'])
    atr, _ = wilder_atr(h, l, c, P['atr_n'])
    atr_r = atr_ratio(atr, P['atr_sma_n'])
    # 기울기신호: (c[i]-c[i-slope_n]) / (slope_n*atr) → ATR로 정규화 후 -1~1
    N = len(c); slope = np.zeros(N); sn = P['slope_n']
    for i in range(sn, N):
        denom = sn * atr[i] if atr[i] > 0 else 1.0
        slope[i] = (c[i] - c[i - sn]) / denom
    return dict(adx=adx, pdi=pdi, ndi=ndi, chop=chop, er=er, bb=bw, atr_r=atr_r, slope=slope)


def classify(o, h, l, c, params=None, ind=None):
    P = dict(DEFAULT_PARAMS); 
    if params:
        P.update(params)
    if ind is None:
        ind = compute_indicators(o, h, l, c, P)
    adx, pdi, ndi = ind['adx'], ind['pdi'], ind['ndi']
    chop, er, bw, atr_r, slope = ind['chop'], ind['er'], ind['bb'], ind['atr_r'], ind['slope']
    N = len(c)
    # 방향신호 -1~+1
    di_raw = np.zeros(N)
    s = pdi + ndi
    nz = s > 0
    di_raw[nz] = (pdi[nz] - ndi[nz]) / s[nz]          # 이미 -1~1
    slope_sig = norm_clip(slope, 1.0)                  # 기울기 정규화
    w = P['w']
    dir_score = w * di_raw + (1.0 - w) * slope_sig
    # 추세표 4개(다수결)
    v1 = (adx > P['adx_hi']).astype(int)
    v2 = (chop < P['chop_hi']).astype(int)   # CHOP가 choppy임계(60/61.8/65) 아래면 '안choppy'=추세표 → 격자 chop_hi가 실제 작동
    v3 = (er > P['er_hi']).astype(int)
    v4 = (atr_r > 1.0).astype(int)
    trend_votes = v1 + v2 + v3 + v4
    is_trend = trend_votes >= P['vote_n']
    reg = np.full(N, 3, dtype=int)   # 기본 죽은레인지
    for i in range(N):
        if is_trend[i]:
            reg[i] = 0 if dir_score[i] >= 0 else 1
        else:
            reg[i] = 3 if bw[i] < P['bb_dead'] else 2
    # 휩쏘 방지(선택): min_hold 봉 동안 국면 유지
    if P['min_hold'] > 1:
        last = reg[0]; hold = 0; out = reg.copy()
        for i in range(1, N):
            if reg[i] != last:
                hold += 1
                if hold >= P['min_hold']:
                    last = reg[i]; hold = 0
                else:
                    out[i] = last
            else:
                hold = 0; out[i] = reg[i]
        reg = out
    return reg, dir_score, trend_votes, ind


def feature_matrix(ind):
    # ML 특징표(실시간 안전 지표만). label_smc는 포함 안 함(타깃은 외부에서).
    return np.column_stack([ind['adx'], ind['pdi'], ind['ndi'], ind['chop'],
                            ind['er'], ind['bb'], ind['atr_r'], ind['slope']])


# ─────────────────────────────────────────────────────────────────────────────
# [칩필터 게이트 — Stg4 신규]  옛 칩필터(진입순간 단일봉 AND 3조건) 실패를 검색근거로 교정.
#   근거: CHOP는 지연지표(LuxAlgo)→진입 전 N봉으로 사전판정 / 단일봉 금지(Chop Zone)→연속 K봉 확정
#         CHOP 무방향(Positioned)→방향짝 옵션 / Squeeze 압축게이트(우리 bb_width_pct 보유)
#   [In] 지표 dict(ind), 봉 인덱스 배열(거래 진입봉), 파라미터  [Out] 각 봉이 '횡보봇 허용'인지 bool 배열
#   ※ 이건 '게이트(통과/차단)'지 4국면 분류가 아님. 횡보봇을 칩(횡보)구간서만 켜는 용도.
# ─────────────────────────────────────────────────────────────────────────────
def chip_gate_series(ind, P):
    # 매 봉마다 '지금이 칩(횡보)인가?'를 bool로. 전부 과거봉만 사용(lookahead 없음).
    chop, adx, er, bb, atr_r = ind['chop'], ind['adx'], ind['er'], ind['bb'], ind['atr_r']
    N = len(chop)
    chop_hi = P.get('chip_chop_hi', 61.8)   # S3: 55 / 61.8 / 65
    adx_lo = P.get('chip_adx_lo', 25.0)     # 칩=약추세, ADX 낮음
    er_lo = P.get('chip_er_lo', 0.35)       # 칩=비효율, ER 낮음
    combo = P.get('chip_combo', 'OR')       # S4: 'AND' / 'OR' / '2of3'
    sqz = P.get('chip_squeeze', 0.0)        # Squeeze 게이트: 0=off, 아니면 bb<sqz면 칩가점
    # 3개 칩 조건(전부 '횡보다움')
    c1 = chop > chop_hi      # choppy
    c2 = adx < adx_lo        # 약추세
    c3 = er < er_lo          # 비효율
    votes = c1.astype(int) + c2.astype(int) + c3.astype(int)
    if combo == 'AND':
        chip = (votes == 3)
    elif combo == '2of3':
        chip = (votes >= 2)
    else:  # OR
        chip = (votes >= 1)
    # Squeeze 게이트: bb폭이 sqz 미만이면 '압축=칩 후보'로 OR 결합
    if sqz > 0:
        chip = chip | (bb < sqz)
    return chip


def chip_gate_at(ind, bar_idx, P):
    # 거래 진입봉(bar_idx)들이 '칩 게이트 통과'인지 판정.
    #   S1 사전게이팅 N: 진입봉이 아니라 N봉 전 상태로 판정(lag 회피, N=0이면 당봉)
    #   S2 연속확정 K: 진입 직전 K봉이 '연속으로' 칩이어야 통과(단일봉 노이즈 제거)
    chip = chip_gate_series(ind, P)
    N = len(chip)
    pre_n = int(P.get('chip_pre_n', 0))     # S1: 0 / 2 / 4
    hold_k = int(P.get('chip_hold_k', 1))   # S2: 1 / 2 / 3
    out = np.zeros(len(bar_idx), dtype=bool)
    for j, bi in enumerate(bar_idx):
        ref = bi - pre_n                    # 사전게이팅: N봉 전 기준
        if ref < 0:
            out[j] = False; continue
        # 연속확정: ref 포함 직전 K봉이 전부 칩인가
        lo = ref - hold_k + 1
        if lo < 0:
            out[j] = False; continue
        out[j] = bool(chip[lo:ref + 1].all())
    return out
