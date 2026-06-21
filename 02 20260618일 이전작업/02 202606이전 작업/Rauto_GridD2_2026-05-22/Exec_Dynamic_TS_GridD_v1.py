# -*- coding: utf-8 -*-
# [파일명] Exec_Dynamic_TS_GridD_v1.py
# 코드길이: 약 200줄, 내부버전명: GridD_v1, 로직 축약/생략 없이 전체 출력
#
# [목적]
#   검증된 수익난 모델(Exec_Dynamic_TS_PautoV75, PF 2.864)의 청산로직을 그대로 두되,
#   단계 D 그리드 실험을 위해 '혁신1(눌림목 이후 피보 기준점 재설정) on/off 토글' 1개만 추가한다.
#   - 원본 대비 변경점은 단 한 곳: Phase2의 fib_wave_start 재설정을 params['innovation1']로 조건화.
#   - 그 외 모든 계산식·OB탐색·분할익절 신호·하드손절은 원본과 100% 동일(verbatim).
#
# [원본과의 차이 — 단 1줄 로직]
#   원본: 눌림 후 재돌파 시 무조건 fib_wave_start = fib_extreme (혁신1 항상 ON)
#   패치: params.get('innovation1', True) 일 때만 재설정. False면 기준점을 진입가에 고정.
#
# [함수 In/Out]
#   _find_order_blocks(df, current_price, pos)  : 최근 100봉 -> (bullish_obs, bearish_obs) 리스트
#       IN  df(DataFrame 최근봉), current_price(float), pos(str 'LONG'/'SHORT')
#       OUT (bullish_obs:list[dict], bearish_obs:list[dict])  각 dict={top,bottom,mean}
#   check_exit(current_price, bot_state, params) : 현재가/상태/설정 -> 청산액션 dict
#       IN  current_price(float), bot_state(dict), params(dict: leverage, fib_*, innovation1)
#       OUT {'action': 'HOLD'/'REDUCE_LONG'/'REDUCE_SHORT'/'CLOSE_LONG'/'CLOSE_SHORT', 'reason': str}
#
# [bot_state 주요 키]  position, entry_price, df_1m, ob_initialized, bullish_obs, bearish_obs,
#                       remaining_pct(1.0->그리드비율), target_idx, fib_stop, fib_extreme,
#                       fib_wave_start, pulled_back
# ==============================================================================

import pandas as pd
import numpy as np


class Exec_Dynamic_TS_GridD_v1:
    def __init__(self):
        pass

    def _find_order_blocks(self, df, current_price, pos):
        """최근 100캔들 스윙으로 저항/지지 OB(매물대)를 실시간 매핑. (원본 verbatim)"""
        lookback = df.tail(100)
        highs = lookback['high'].values
        lows = lookback['low'].values
        bearish_obs, bullish_obs = [], []

        for i in range(2, len(highs) - 2):
            # 저항선 (위쪽 매물대) — 좌우 2봉 중 최고, 현재가보다 위
            if highs[i] == max(highs[i - 2:i + 3]) and highs[i] > current_price:
                bearish_obs.append({'top': highs[i], 'bottom': lows[i], 'mean': (highs[i] + lows[i]) / 2})
            # 지지선 (아래쪽 매물대) — 좌우 2봉 중 최저, 현재가보다 아래
            if lows[i] == min(lows[i - 2:i + 3]) and lows[i] < current_price:
                bullish_obs.append({'top': highs[i], 'bottom': lows[i], 'mean': (highs[i] + lows[i]) / 2})

        bearish_obs = sorted(bearish_obs, key=lambda x: x['bottom'])
        bullish_obs = sorted(bullish_obs, key=lambda x: x['top'], reverse=True)
        return bullish_obs, bearish_obs

    def check_exit(self, current_price: float, bot_state: dict, params: dict) -> dict:
        pos = bot_state['position']
        if pos == "WAIT":
            return {"action": "HOLD", "reason": "포지션 없음"}

        entry = bot_state['entry_price']
        df_1m = bot_state['df_1m']

        # [머신러닝 동적 파라미터 로드] — 원본과 동일
        leverage = params.get('leverage', 1)
        fib_trigger = params.get('fib_trigger_roe', 15.0)      # 피보 트레일링 발동 ROE
        fib_sl_pct = params.get('fib_sl_roe', 5.73) / 100.0    # 초기 하드 손절폭
        fib_ext = params.get('fib_ext_pct', 0.618)             # 추가 파동 락인 비율
        innovation1 = params.get('innovation1', True)          # [패치] 혁신1 on/off

        # 진입 직후 지형 1회 스캔 (목표가 고정)
        if not bot_state['ob_initialized']:
            bot_state['bullish_obs'], bot_state['bearish_obs'] = self._find_order_blocks(df_1m, current_price, pos)
            bot_state['ob_initialized'] = True

        remaining_pct = bot_state['remaining_pct']
        target_idx = bot_state['target_idx']

        # ------------------------------------------------------------
        # [LONG] SMC 분할 + 피보나치 계단식 청산
        # ------------------------------------------------------------
        if pos == "LONG":
            bearish_obs = bot_state['bearish_obs']

            # [Phase 1] 다중 OB 타겟팅 (SMC 분할 익절)
            if target_idx < len(bearish_obs):
                target_ob = bearish_obs[target_idx]

                if current_price >= target_ob['mean']:
                    new_sl = target_ob['bottom']           # 윗엣지로 스탑 상향
                    bot_state['fib_stop'] = new_sl
                    bot_state['target_idx'] += 1
                    if remaining_pct == 1.0:
                        return {"action": "REDUCE_LONG", "reason": f"SMC 1차 타겟(OB중간값) 도달: 분할 익절 및 스탑 상향({new_sl:.2f})"}
                    else:
                        return {"action": "HOLD", "reason": f"SMC N차 타겟 도달: 스탑 상향({new_sl:.2f})"}

                if bot_state['fib_stop'] is not None and current_price <= bot_state['fib_stop']:
                    return {"action": "CLOSE_LONG", "reason": f"SMC OB 엣지 스탑 이탈 ({bot_state['fib_stop']:.2f})"}

            # [Phase 2] 계단식 파동 피보나치
            else:
                roe = ((current_price - entry) / entry) * leverage * 100
                max_roe = ((bot_state['fib_extreme'] - entry) / entry) * leverage * 100

                if current_price > bot_state['fib_extreme']:
                    if bot_state['pulled_back']:
                        # [패치] 혁신1 ON일 때만 기준점 재설정. OFF면 진입 기준 고정.
                        if innovation1:
                            bot_state['fib_wave_start'] = bot_state['fib_extreme']
                        bot_state['pulled_back'] = False
                    bot_state['fib_extreme'] = current_price
                elif current_price < bot_state['fib_extreme']:
                    bot_state['pulled_back'] = True

                if roe >= fib_trigger or max_roe >= fib_trigger:
                    upswing = bot_state['fib_extreme'] - bot_state['fib_wave_start']
                    fib_lock = bot_state['fib_wave_start'] + (upswing * fib_ext)
                    bot_state['fib_stop'] = max(bot_state.get('fib_stop', 0) or 0, fib_lock)

                    if current_price <= bot_state['fib_stop']:
                        return {"action": "CLOSE_LONG", "reason": f"Fibonacci 계단식 스탑 터치 (추가상승분 {fib_ext:.3f} 락인: {bot_state['fib_stop']:.2f})"}
                else:
                    hard_sl = entry * (1 - (fib_sl_pct / leverage))
                    if current_price <= hard_sl:
                        return {"action": "CLOSE_LONG", "reason": f"초기 하드 손절 (-{fib_sl_pct*100:.2f}% ROE)"}

        # ------------------------------------------------------------
        # [SHORT] SMC 분할 + 피보나치 계단식 청산 (대칭)
        # ------------------------------------------------------------
        elif pos == "SHORT":
            bullish_obs = bot_state['bullish_obs']

            # [Phase 1] 다중 OB 타겟팅
            if target_idx < len(bullish_obs):
                target_ob = bullish_obs[target_idx]

                if current_price <= target_ob['mean']:
                    new_sl = target_ob['top']              # 아랫엣지로 스탑 하향
                    bot_state['fib_stop'] = new_sl
                    bot_state['target_idx'] += 1
                    if remaining_pct == 1.0:
                        return {"action": "REDUCE_SHORT", "reason": f"SMC 1차 타겟(OB중간값) 도달: 분할 익절 및 스탑 하향({new_sl:.2f})"}
                    else:
                        return {"action": "HOLD", "reason": f"SMC N차 타겟 도달: 스탑 하향({new_sl:.2f})"}

                if bot_state['fib_stop'] is not None and current_price >= bot_state['fib_stop']:
                    return {"action": "CLOSE_SHORT", "reason": f"SMC OB 엣지 스탑 이탈 ({bot_state['fib_stop']:.2f})"}

            # [Phase 2] 계단식 파동 피보나치
            else:
                roe = ((entry - current_price) / entry) * leverage * 100
                max_roe = ((entry - bot_state['fib_extreme']) / entry) * leverage * 100

                if current_price < bot_state['fib_extreme']:
                    if bot_state['pulled_back']:
                        # [패치] 혁신1 ON일 때만 기준점 재설정.
                        if innovation1:
                            bot_state['fib_wave_start'] = bot_state['fib_extreme']
                        bot_state['pulled_back'] = False
                    bot_state['fib_extreme'] = current_price
                elif current_price > bot_state['fib_extreme']:
                    bot_state['pulled_back'] = True

                if roe >= fib_trigger or max_roe >= fib_trigger:
                    downswing = bot_state['fib_wave_start'] - bot_state['fib_extreme']
                    fib_lock = bot_state['fib_wave_start'] - (downswing * fib_ext)
                    prev = bot_state.get('fib_stop', None)
                    bot_state['fib_stop'] = min(prev if prev is not None else float('inf'), fib_lock)

                    if current_price >= bot_state['fib_stop']:
                        return {"action": "CLOSE_SHORT", "reason": f"Fibonacci 계단식 스탑 터치 (추가하락분 {fib_ext:.3f} 락인: {bot_state['fib_stop']:.2f})"}
                else:
                    hard_sl = entry * (1 + (fib_sl_pct / leverage))
                    if current_price >= hard_sl:
                        return {"action": "CLOSE_SHORT", "reason": f"초기 하드 손절 (-{fib_sl_pct*100:.2f}% ROE)"}

        return {"action": "HOLD", "reason": "안전"}
