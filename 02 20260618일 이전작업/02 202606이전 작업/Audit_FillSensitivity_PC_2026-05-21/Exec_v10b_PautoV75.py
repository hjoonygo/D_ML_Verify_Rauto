# -*- coding: utf-8 -*-
# [파일명] Exec_v10b_PautoV75.py
# 내부버전명: v10b (원본 Exec_Dynamic_TS 손절구멍 패치본). 원본은 보존, 본 파일만 1곳 수정.
# [수정 사유] 원본은 초기 하드손절(115bp)이 Phase2(OB 목표 소진 후)에서만 작동 →
#   포지션이 처음부터 반대로 가서 첫 OB 목표를 영영 못 맞히면 손절이 아예 없어 무한정 깨짐(36개월 검증서 숏 2건 -37.8% 발생).
# [수정 내용] 진입 즉시 하드손절 '바닥(hard_floor)'을 설정하고, 아직 어떤 스탑도 안 잡힌 구간에서 항상 적용.
#   - 스탑이 이미 잡힌(OB 목표 도달) 거래는 기존 로직 그대로 → 검증된 동작 불변.
# [In/Out] check_exit(current_price, bot_state, params) -> {action, reason}  (원본과 동일)
#   STATE 추가: bot_state['hard_floor'] (진입 즉시 1회 설정되는 손절 바닥 가격)

# ==============================================================================
# 파일명: Exec_Dynamic_TS_PautoV75.py
# 역할: Pauto V7.5 다중 오더블록(OB) 분할 익절 및 피보나치 계단식 트레일링 스탑 청산 모듈
# 특징: 머신러닝(Optuna)과 연동되어 피보나치 비율(0.618 등)을 동적으로 수신하여 최적화함
#
# [변수 파이프라인 (Data I/O Pipeline)]
# 📥 [IN] 
#   - current_price (float): DataEngine에서 공급되는 실시간 0.1초 단위 틱 가격
#   - bot_state (dict): 진입가, 남은물량(remaining_pct), 피보나치 고/저점 메모리 등
#   - params (dict): 엔진 마스터 설정값 (Optuna 최적화 비율 포함)
# 
# 🛠️ [STATE] 
#   - 1차: 실시간 다중 오더블록(OB) 매물대 스캔 및 지지/저항선 확인
#   - 2차: 타겟 도달 시 50% 물량 덜어내기 (REDUCE)
#   - 3차: 잔여 50%에 대한 피보나치 파동(고점/저점) 비율 계산 및 계단식 트레일링 스탑(fib_stop) 갱신
# 
# 📤 [OUT] 
#   - exit_signal (dict): 엔진으로 반환하는 액션 커맨드 (REDUCE/CLOSE/HOLD) 및 청산 사유
# ==============================================================================

import pandas as pd
import numpy as np

class Exec_v10b_PautoV75:
    def __init__(self):
        pass

    def _find_order_blocks(self, df, current_price, pos):
        """최근 100캔들의 스윙을 분석하여 저항/지지 OB(매물대) 지대를 실시간 매핑"""
        lookback = df.tail(100)
        highs = lookback['high'].values
        lows = lookback['low'].values
        bearish_obs, bullish_obs = [], []
        
        for i in range(2, len(highs)-2):
            # 저항선 (위쪽 매물대)
            if highs[i] == max(highs[i-2:i+3]) and highs[i] > current_price: 
                bearish_obs.append({'top': highs[i], 'bottom': lows[i], 'mean': (highs[i]+lows[i])/2})
            # 지지선 (아래쪽 매물대)
            if lows[i] == min(lows[i-2:i+3]) and lows[i] < current_price: 
                bullish_obs.append({'top': highs[i], 'bottom': lows[i], 'mean': (highs[i]+lows[i])/2})
                
        # 롱이면 윗 저항선을 가까운 순 정렬, 숏이면 아래 지지선을 가까운 순 정렬
        bearish_obs = sorted(bearish_obs, key=lambda x: x['bottom'])
        bullish_obs = sorted(bullish_obs, key=lambda x: x['top'], reverse=True)
        return bullish_obs, bearish_obs

    def check_exit(self, current_price: float, bot_state: dict, params: dict) -> dict:
        pos = bot_state['position']
        if pos == "WAIT":
            return {"action": "HOLD", "reason": "포지션 없음"}

        entry = bot_state['entry_price']
        df_1m = bot_state['df_1m']

        # 🌟 [머신러닝 동적 파라미터 로드] Optuna 최적화기가 던져주는 값을 수신
        leverage = params.get('leverage', 1)
        fib_trigger = params.get('fib_trigger_roe', 15.0)     # 피보나치 트레일링 발동 ROE (기본 15%)
        fib_sl_pct = params.get('fib_sl_roe', 5.73) / 100.0   # 초기 하드 손절폭 (기본 5.73%)
        fib_ext = params.get('fib_ext_pct', 0.618)            # 추가 파동 락인 비율 (기본 0.618)

        # 진입 직후 지형 1회 스캔 (목표가 안 바뀌도록 고정)
        if not bot_state['ob_initialized']:
            bot_state['bullish_obs'], bot_state['bearish_obs'] = self._find_order_blocks(df_1m, current_price, pos)
            bot_state['ob_initialized'] = True

        # [v10b 패치] 진입 즉시 하드손절 바닥 설정 (Phase 무관, 손절 구멍 차단)
        if 'hard_floor' not in bot_state:
            if pos == "LONG":
                bot_state['hard_floor'] = entry * (1 - fib_sl_pct / leverage)
            else:
                bot_state['hard_floor'] = entry * (1 + fib_sl_pct / leverage)

        remaining_pct = bot_state['remaining_pct']
        target_idx = bot_state['target_idx']
        
        # ------------------------------------------------------------
        # 🟢 [LONG] SMC 분할 + 피보나치 계단식 청산
        # ------------------------------------------------------------
        if pos == "LONG":
            bearish_obs = bot_state['bearish_obs']

            # [v10b 패치] 아직 어떤 스탑도 안 잡힌 구간(첫 OB 미도달)에서 하드손절 바닥 적용
            if bot_state.get('fib_stop') is None and current_price <= bot_state.get('hard_floor', 0):
                return {"action": "CLOSE_LONG", "reason": f"초기 하드손절(항상,v10b) -{fib_sl_pct/leverage*100:.2f}%"}
            
            # [Phase 1] 다중 OB 타겟팅 (SMC 분할 익절)
            if target_idx < len(bearish_obs):
                target_ob = bearish_obs[target_idx]
                
                # 익절 및 트레일링 스탑 상향
                if current_price >= target_ob['mean']:
                    new_sl = target_ob['bottom'] # 윗엣지로 스탑 상향
                    bot_state['fib_stop'] = new_sl
                    bot_state['target_idx'] += 1
                    if remaining_pct == 1.0:
                        return {"action": "REDUCE_LONG", "reason": f"SMC 1차 타겟(OB중간값) 도달: 50% 분할 익절 및 스탑 상향({new_sl:.2f})"}
                    else:
                        return {"action": "HOLD", "reason": f"SMC N차 타겟 도달: 스탑 상향({new_sl:.2f})"}
                
                # OB 엣지 스탑 체크
                if bot_state['fib_stop'] is not None and current_price <= bot_state['fib_stop']:
                    return {"action": "CLOSE_LONG", "reason": f"SMC OB 엣지 스탑 이탈 ({bot_state['fib_stop']:.2f})"}

            # [Phase 2] 계단식 파동 피보나치 (OB 소멸 및 가격 발견 구역)
            else:
                roe = ((current_price - entry) / entry) * leverage * 100
                max_roe = ((bot_state['fib_extreme'] - entry) / entry) * leverage * 100
                
                # 파동 고점(extreme) 갱신 및 풀백 감지
                if current_price > bot_state['fib_extreme']:
                    if bot_state['pulled_back']: # 눌림 후 재돌파 성공 시 기준점(Reference) 갱신
                        bot_state['fib_wave_start'] = bot_state['fib_extreme'] 
                        bot_state['pulled_back'] = False
                    bot_state['fib_extreme'] = current_price
                elif current_price < bot_state['fib_extreme']:
                    bot_state['pulled_back'] = True # 고점 대비 하락 발생
                
                # 트리거 ROE 도달 시부터 계단식 락인 가동
                if roe >= fib_trigger or max_roe >= fib_trigger:
                    upswing = bot_state['fib_extreme'] - bot_state['fib_wave_start']
                    # 대표님 공식 (머신러닝 조율 적용): 새로운 기준 + (추가 상승분 * 락인 비율)
                    fib_lock = bot_state['fib_wave_start'] + (upswing * fib_ext)
                    _prev = bot_state.get('fib_stop')
                    bot_state['fib_stop'] = fib_lock if _prev is None else max(_prev, fib_lock)
                    
                    if current_price <= bot_state['fib_stop']:
                        return {"action": "CLOSE_LONG", "reason": f"Fibonacci 계단식 스탑 터치 (추가 상승분 {fib_ext:.3f} 락인: {bot_state['fib_stop']:.2f})"}
                else:
                    # 트리거 도달 전 초기 하드 손절
                    hard_sl = entry * (1 - (fib_sl_pct / leverage))
                    if current_price <= hard_sl:
                        return {"action": "CLOSE_LONG", "reason": f"초기 하드 손절 (-{fib_sl_pct*100:.2f}% ROE)"}

        # ------------------------------------------------------------
        # 🔴 [SHORT] SMC 분할 + 피보나치 계단식 청산 (대칭)
        # ------------------------------------------------------------
        elif pos == "SHORT":
            bullish_obs = bot_state['bullish_obs']

            # [v10b 패치] 아직 어떤 스탑도 안 잡힌 구간(첫 OB 미도달)에서 하드손절 바닥 적용
            if bot_state.get('fib_stop') is None and current_price >= bot_state.get('hard_floor', float('inf')):
                return {"action": "CLOSE_SHORT", "reason": f"초기 하드손절(항상,v10b) -{fib_sl_pct/leverage*100:.2f}%"}
            
            # [Phase 1] 다중 OB 타겟팅 (SMC 분할 익절)
            if target_idx < len(bullish_obs):
                target_ob = bullish_obs[target_idx]
                
                # 익절 및 트레일링 스탑 하향
                if current_price <= target_ob['mean']:
                    new_sl = target_ob['top'] # 아랫엣지로 스탑 하향
                    bot_state['fib_stop'] = new_sl
                    bot_state['target_idx'] += 1
                    if remaining_pct == 1.0:
                        return {"action": "REDUCE_SHORT", "reason": f"SMC 1차 타겟(OB중간값) 도달: 50% 분할 익절 및 스탑 하향({new_sl:.2f})"}
                    else:
                        return {"action": "HOLD", "reason": f"SMC N차 타겟 도달: 스탑 하향({new_sl:.2f})"}
                
                # OB 엣지 스탑 체크
                if bot_state['fib_stop'] is not None and current_price >= bot_state['fib_stop']:
                    return {"action": "CLOSE_SHORT", "reason": f"SMC OB 엣지 스탑 이탈 ({bot_state['fib_stop']:.2f})"}

            # [Phase 2] 계단식 파동 피보나치 (OB 소멸 및 가격 발견 구역)
            else:
                roe = ((entry - current_price) / entry) * leverage * 100
                max_roe = ((entry - bot_state['fib_extreme']) / entry) * leverage * 100
                
                # 파동 저점(extreme) 갱신 및 풀백 감지
                if current_price < bot_state['fib_extreme']:
                    if bot_state['pulled_back']:
                        bot_state['fib_wave_start'] = bot_state['fib_extreme'] 
                        bot_state['pulled_back'] = False
                    bot_state['fib_extreme'] = current_price
                elif current_price > bot_state['fib_extreme']:
                    bot_state['pulled_back'] = True 
                
                # 트리거 ROE 도달 시부터 계단식 락인 가동
                if roe >= fib_trigger or max_roe >= fib_trigger:
                    downswing = bot_state['fib_wave_start'] - bot_state['fib_extreme']
                    # 대표님 공식 (머신러닝 조율 적용): 새로운 기준 - (추가 하락분 * 락인 비율)
                    fib_lock = bot_state['fib_wave_start'] - (downswing * fib_ext)
                    _prev = bot_state.get('fib_stop')
                    bot_state['fib_stop'] = fib_lock if _prev is None else min(_prev, fib_lock)
                    
                    if current_price >= bot_state['fib_stop']:
                        return {"action": "CLOSE_SHORT", "reason": f"Fibonacci 계단식 스탑 터치 (추가 하락분 {fib_ext:.3f} 락인: {bot_state['fib_stop']:.2f})"}
                else:
                    # 트리거 도달 전 초기 하드 손절
                    hard_sl = entry * (1 + (fib_sl_pct / leverage))
                    if current_price >= hard_sl:
                        return {"action": "CLOSE_SHORT", "reason": f"초기 하드 손절 (-{fib_sl_pct*100:.2f}% ROE)"}

        return {"action": "HOLD", "reason": "안전"}