# -*- coding: utf-8 -*-
# [파일명] forced_entry.py
# 코드길이: 약 180줄 | 내부버전: 06Prj_Ch6_Stg5_ForcedEntry_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 모듈이 하는 일 — 고딩 설명]  사장님 확정 (C)+방식2+보유상한 자동계산.
#   목적: ML 표본을 408개(실제거래)→수천개(전봉)로 늘린다. 매 봉에서 '그 자리 진입 시 가상수익'을 계산.
#   엔진 무수정. 엔진 청산로직(트렌드플립/피벗SL)을 흉내내다 틀리는 위험을 피하려고 '방식2 고정청산' 사용:
#     강제진입 후 [트렌드 반대전환 OR N봉 경과 OR ATR배수 손절] 중 먼저 오는 것으로 청산. 투명·재현가능.
#   ★(C) 핵심: 강제진입 봉이 '실제론 봇이 거른 자리'인지 플래그로 표시 → ML이 진짜/가짜를 구분.
#   ★보유상한 N: 실제 거래의 봇별 평균 보유봉을 실행 시 자동계산(추정 아님).
#   ★미래참조: 가상수익 계산은 미래봉을 보지만, 그건 '타깃(라벨)' 용도(지도학습 정상). 특징 X에는 진입봉 이전만.
#              청산에 쓴 미래봉이 특징에 새지 않게 분리(테스트 코드에서 feat=진입봉-1만 사용).
#
# [In] OHLC·Trend·atr 배열, 진입봉 리스트(전봉), side(롱/숏), 보유상한N, ATR손절배수
# [Out] 각 봉의 가상R(롱/숏 각각), 청산이유, 보유봉수
# [사용함수] avg_hold_bars(실제거래 평균보유) / forced_vret(강제진입 가상수익) / skip_reason_flags(거른이유)
# ==============================================================================
import numpy as np

COST_RT = 0.0014    # 왕복 0.14%(테스트 표준, 엔진 0.04%보다 보수적)
FUND_8H = 0.0001    # 펀딩 근사(실펀딩은 테스트코드서 별도 차감 가능)


def avg_hold_bars(trades, default=8):
    # 실제 거래의 평균 보유봉(entry~exit 봉수). 거래 없으면 default.
    if not trades:
        return default
    hb = []
    for t in trades:
        b = t.get('bars')
        if b is not None and b > 0:
            hb.append(int(b))
    if not hb:
        return default
    return max(1, int(round(np.mean(hb))))


def forced_vret(close, high, low, Trend, atr, side, hold_cap, sl_mult, lev=1.0, fund_n=None):
    # 매 봉 i에서 side(+1/-1)로 강제진입 → 방식2 고정청산. 가상R 배열 반환(길이=len(close)).
    #   청산: (a)트렌드 반대전환  (b)ATR손절(진입가 ± sl_mult*atr)  (c)hold_cap봉 경과  중 먼저.
    #   ★미래봉 사용은 '라벨'이므로 정상. 각 i의 결과는 i 시점엔 모르는 값(타깃).
    n = len(close)
    vR = np.full(n, np.nan)
    vreason = np.array(['none'] * n, dtype=object)
    vbars = np.zeros(n, dtype=int)
    for i in range(n):
        if i + 1 >= n:
            continue
        entry = close[i]
        if not np.isfinite(entry) or entry <= 0:
            continue
        a = atr[i] if (atr is not None and np.isfinite(atr[i])) else 0.0
        sl = entry - side * sl_mult * a if a > 0 else np.nan   # 롱이면 아래, 숏이면 위
        exit_px = np.nan; reason = 'cap'; held = 0
        jend = min(i + 1 + hold_cap, n)
        for j in range(i + 1, jend):
            held = j - i
            # (a) 트렌드 반대전환
            if (side == 1 and Trend[j] == -1) or (side == -1 and Trend[j] == 1):
                exit_px = close[j]; reason = 'flip'; break
            # (b) ATR 손절(고가/저가로 터치 판정)
            if not np.isnan(sl):
                if side == 1 and low[j] <= sl:
                    exit_px = sl; reason = 'sl'; break
                if side == -1 and high[j] >= sl:
                    exit_px = sl; reason = 'sl'; break
        if np.isnan(exit_px):
            j = jend - 1; exit_px = close[j]; reason = 'cap'; held = j - i
        R = side * (exit_px - entry) / entry * lev - COST_RT
        if fund_n is not None:
            R -= FUND_8H * fund_n  # 보유기간 펀딩 근사(옵션)
        vR[i] = R; vreason[i] = reason; vbars[i] = held
    return vR, vreason, vbars


def skip_reason_flags(sig, n, dz_oi=None, dz_lo=None, dz_hi=None,
                      gate_mode='er', gate_er=0.45, gate_adx=25.0):
    # (C) 거른이유 특징: 각 봉에서 봇이 '실제론 거를' 이유를 0/1 플래그로. 전부 과거봉(진입봉)까지만.
    #   f_no_signal: 트렌드 신호 자체가 약(추세봇 진입조건 미충족 근사)
    #   f_grave: 무덤필터(OI z가 [dz_lo,dz_hi) 구간) — 추세장일 때 진입보류 대상
    #   f_low_gate: 게이트(ER/ADX) 미달 — 추세장 아님
    flags = {}
    adx = sig.get('adx'); er = sig.get('er'); Trend = sig.get('Trend')
    flags['f_low_gate'] = np.zeros(n, dtype=float)
    flags['f_grave'] = np.zeros(n, dtype=float)
    flags['f_trend_up'] = np.zeros(n, dtype=float)
    for i in range(n):
        # 게이트 미달(추세장 아님)
        if gate_mode == 'er' and er is not None:
            flags['f_low_gate'][i] = 1.0 if (np.isfinite(er[i]) and er[i] < gate_er) else 0.0
        elif gate_mode == 'adx' and adx is not None:
            flags['f_low_gate'][i] = 1.0 if (np.isfinite(adx[i]) and adx[i] < gate_adx) else 0.0
        # 무덤필터 구간
        if dz_oi is not None and dz_lo is not None and dz_hi is not None:
            z = dz_oi[i]
            flags['f_grave'][i] = 1.0 if (np.isfinite(z) and dz_lo <= z < dz_hi) else 0.0
        # 트렌드 방향(참고특징)
        if Trend is not None:
            flags['f_trend_up'][i] = 1.0 if Trend[i] == 1 else 0.0
    return flags
