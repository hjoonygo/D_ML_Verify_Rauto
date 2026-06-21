# -*- coding: utf-8 -*-
# [파일명] cooldown.py
# 코드길이: 약 110줄 | 내부버전: 06Prj_Ch6_Stg9_Cooldown_v1 | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 모듈이 하는 일 — 고딩 설명]  사장님 아이디어 = 휩쏘 누적 방어기제(쿨다운). 검색확인된 표준기법.
#   진입 시점엔 휩쏘를 못 가린다(Stg8). 대신 '연속 손절(sl)이 K번 터지면 = 지금 휩쏘장' 이라고 사후 인식,
#   그때부터 M봉 동안 새 진입을 건너뛴다. 휩쏘 구간만 쉬고, 추세 좋은 구간은 그대로.
#
#   ★엔진 무수정: 엔진이 만든 거래목록을 시간순으로 훑으며 쿨다운 구간 진입 거래를 '제외'(사후 필터링).
#     거래를 새로 만들지 않고 제외만 하므로 포지션 오염 없음(숏격자와 달리 깨끗).
#   ★발동 기준(확인1=가): 연속 sl 횟수. 직전 '수익' 거래 이후 sl이 K연속이면 발동.
#   ★규칙: 쿨다운 발동시각(K번째 sl의 exit_t)부터 M봉 안에 entry_t가 드는 거래는 건너뜀.
#          건너뛴 거래는 카운터에 반영 안 함(실제로 안 한 거래니까). 쿨다운 끝나면 정상 복귀.
#
# [In] 거래목록(시간순, entry_t·exit_t·reason·R), bar_minutes(봉길이), K(임계), M(쉬는봉수)
# [Out] 살아남은 거래 인덱스(쿨다운으로 제외 안 된 것), 제외된 수, 발동 횟수
# [사용함수] apply_cooldown(메인) / bars_between(두 시각 사이 봉수)
# ==============================================================================
import numpy as np
import pandas as pd


def bars_between(t_from, t_to, bar_minutes):
    # t_from~t_to 사이 봉 수(정수). 7h봉이면 bar_minutes=420.
    dt = (pd.Timestamp(t_to) - pd.Timestamp(t_from)).total_seconds() / 60.0
    return dt / bar_minutes


def apply_cooldown(trades, bar_minutes, K, M):
    # 연속 sl K번 → 이후 M봉 진입중단. 엔진 무수정 사후 필터링.
    #   trades: 시간순 거래목록(dict, entry_t·exit_t·reason·R 필요).
    #   반환: keep_idx(살아남은 거래 인덱스 배열), n_excluded, n_trigger
    if not trades:
        return np.array([], dtype=int), 0, 0
    # 시간순 보장(entry_t 기준 정렬)
    order = sorted(range(len(trades)), key=lambda i: pd.Timestamp(trades[i]['entry_t']).value)
    consec_sl = 0
    cooldown_until = None     # 이 시각 전까지 진입 금지(Timestamp)
    keep = []
    n_excluded = 0; n_trigger = 0
    for i in order:
        t = trades[i]
        et = pd.Timestamp(t['entry_t'])
        # 쿨다운 중이면 이 거래 건너뜀(카운터 반영 안 함 — 실제로 안 한 거래)
        if cooldown_until is not None and et < cooldown_until:
            n_excluded += 1
            continue
        # 쿨다운 해제(시간 지남)
        if cooldown_until is not None and et >= cooldown_until:
            cooldown_until = None
        # 이 거래는 실행됨 → keep
        keep.append(i)
        # 결과로 연속 sl 카운터 갱신
        if t.get('reason') == 'sl' and t['R'] < 0:
            consec_sl += 1
        elif t['R'] > 0:
            consec_sl = 0          # 수익 나면 리셋
        # (flip 손실은 카운터 유지: sl만 센다 — 확인1=가)
        # K번 연속 sl이면 발동: 이 거래 exit_t부터 M봉 쿨다운
        if consec_sl >= K:
            xt = pd.Timestamp(t['exit_t'])
            cooldown_until = xt + pd.Timedelta(minutes=bar_minutes * M)
            n_trigger += 1
            consec_sl = 0          # 발동 후 카운터 리셋(중복발동 방지)
    return np.array(sorted(keep), dtype=int), n_excluded, n_trigger


def cooldown_stats_by_year(trades, keep_idx):
    # 쿨다운으로 제외된 거래의 년도 분포(2025에 집중되나 확인용).
    excluded = set(range(len(trades))) - set(keep_idx.tolist())
    yr_exc = {}
    for i in excluded:
        y = int(pd.Timestamp(trades[i]['entry_t']).year)
        yr_exc[y] = yr_exc.get(y, 0) + 1
    return yr_exc
