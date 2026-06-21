# ==============================================================================
# 파일명: E_ML_V80k_3balancedTBM_R001.py
# 코드길이: 약 200줄 / 내부버전: V8.0k 챔피언 시스템 외부 E 모듈 첫 번째
# 작성일: 2026-04-29
# ==============================================================================
# [전략 정체성]
#   V8.0.j 피보나치 트레일링 청산 (Phase 1 / Phase 2)
#   - Phase 1 (반익절 전): TP1 도달 시 50% + breakeven SL, 또는 hard SL
#   - Phase 2 (반익절 후): ROE 20% 도달 시 피보 0.5 락인 트레일링 SL
#
# [V75 인터페이스 — Pauto/Rauto 공용]
#   📥 IN
#     - current_price (float): 실시간 틱 가격
#     - bot_state (dict): {position, entry_price, sl_price, tp_price,
#                          one_r_dist, peak_price, is_breakeven_on, is_half_taken,
#                          bot_id ★신규}
#     - params (dict): TradingEngine master_params (estimated_leverage 사용)
#   📤 OUT
#     - dict: {action: 'HOLD'/'CLOSE_HALF'/'CLOSE_ALL', reason, [update_sl]}
#
# [패치]
#   - _BOT_FIB_STATE 키에 bot_id 포함 → 멀티봇 충돌 방지 (시나리오 C)
#   - bot_state['bot_id']가 없으면 entry_price+side만으로 fallback
# ==============================================================================

# 청산 설정 (V8.0.k 백테와 동일)
FIB_TRIGGER_ROE_PCT = 20.0
FIB_EXTENSION_RATIO = 0.5
PHASE2_HARD_SL_ROE = 1.6

# 봇별 자체 상태 (모듈 전역) — 키: (bot_id, entry_price, side)
_BOT_FIB_STATE = {}


def _make_key(bot_state: dict):
    """봇 충돌 방지 키. bot_id 없으면 fallback."""
    bot_id = bot_state.get('bot_id', 'default')
    entry = round(bot_state.get('entry_price', 0.0), 2)
    side = bot_state.get('position', 'WAIT')
    return (bot_id, entry, side)


def _get_or_create_state(bot_state: dict, entry_price: float):
    key = _make_key(bot_state)
    if key not in _BOT_FIB_STATE:
        _BOT_FIB_STATE[key] = {
            'fib_extreme': entry_price,
            'fib_swing_start': entry_price,
            'pulled_back': False,
            'phase2_active': False,
        }
    return _BOT_FIB_STATE[key], key


def _cleanup_state(key):
    if key in _BOT_FIB_STATE:
        del _BOT_FIB_STATE[key]


def evaluate_exit(current_price: float, bot_state: dict, params: dict) -> dict:
    """V75 청산 결정 인터페이스."""
    side = bot_state.get('position')
    if side not in ['LONG', 'SHORT']:
        return {'action': 'HOLD', 'reason': '포지션 없음'}
    
    entry = bot_state.get('entry_price', 0.0)
    sl = bot_state.get('sl_price', 0.0)
    tp = bot_state.get('tp_price', 0.0)
    is_half_taken = bot_state.get('is_half_taken', False)
    
    if entry == 0 or sl == 0 or tp == 0:
        return {'action': 'HOLD', 'reason': '가격 미설정'}
    
    fib_state, fib_key = _get_or_create_state(bot_state, entry)
    
    # ========================================================================
    # Phase 1 — 반익절 전
    # ========================================================================
    if not is_half_taken:
        if side == 'LONG':
            if current_price >= tp:
                return {
                    'action': 'CLOSE_HALF',
                    'reason': f'Phase1 TP1 50% 익절 @ ${tp:.2f}',
                    'update_sl': entry,  # breakeven
                }
            if current_price <= sl:
                _cleanup_state(fib_key)
                return {
                    'action': 'CLOSE_ALL',
                    'reason': f'Phase1 Hard SL @ ${sl:.2f}',
                }
        else:  # SHORT
            if current_price <= tp:
                return {
                    'action': 'CLOSE_HALF',
                    'reason': f'Phase1 TP1 50% 익절 @ ${tp:.2f}',
                    'update_sl': entry,
                }
            if current_price >= sl:
                _cleanup_state(fib_key)
                return {
                    'action': 'CLOSE_ALL',
                    'reason': f'Phase1 Hard SL @ ${sl:.2f}',
                }
    
    # ========================================================================
    # Phase 2 — 반익절 후 피보나치 트레일링
    # ========================================================================
    else:
        # 피보 extreme/swing 추적
        if side == 'LONG':
            if current_price > fib_state['fib_extreme']:
                if fib_state['pulled_back']:
                    fib_state['fib_swing_start'] = fib_state['fib_extreme']
                    fib_state['pulled_back'] = False
                fib_state['fib_extreme'] = current_price
            elif current_price < fib_state['fib_extreme']:
                fib_state['pulled_back'] = True
        else:
            if current_price < fib_state['fib_extreme']:
                if fib_state['pulled_back']:
                    fib_state['fib_swing_start'] = fib_state['fib_extreme']
                    fib_state['pulled_back'] = False
                fib_state['fib_extreme'] = current_price
            elif current_price > fib_state['fib_extreme']:
                fib_state['pulled_back'] = True
        
        # ROE 20% 도달 시 Phase 2 활성화
        if side == 'LONG':
            roe_to_peak = (fib_state['fib_extreme'] - entry) / entry * 100
        else:
            roe_to_peak = (entry - fib_state['fib_extreme']) / entry * 100
        
        leverage_est = params.get('estimated_leverage', 7)
        roe_with_leverage = roe_to_peak * leverage_est
        
        if roe_with_leverage >= FIB_TRIGGER_ROE_PCT and not fib_state['phase2_active']:
            fib_state['phase2_active'] = True
        
        if fib_state['phase2_active']:
            if side == 'LONG':
                fib_lock_sl = (fib_state['fib_swing_start'] +
                              (fib_state['fib_extreme'] - fib_state['fib_swing_start']) * FIB_EXTENSION_RATIO)
                new_sl = max(fib_lock_sl, sl)
                if current_price <= new_sl:
                    _cleanup_state(fib_key)
                    return {
                        'action': 'CLOSE_ALL',
                        'reason': f'Phase2 Fib Lock SL @ ${new_sl:.2f} (peak ${fib_state["fib_extreme"]:.2f})',
                    }
                if new_sl > sl:
                    return {
                        'action': 'HOLD',
                        'reason': f'Phase2 트레일링 SL 갱신 ${sl:.2f} → ${new_sl:.2f}',
                        'update_sl': new_sl,
                    }
            else:  # SHORT
                fib_lock_sl = (fib_state['fib_swing_start'] -
                              (fib_state['fib_swing_start'] - fib_state['fib_extreme']) * FIB_EXTENSION_RATIO)
                new_sl = min(fib_lock_sl, sl)
                if current_price >= new_sl:
                    _cleanup_state(fib_key)
                    return {
                        'action': 'CLOSE_ALL',
                        'reason': f'Phase2 Fib Lock SL @ ${new_sl:.2f} (peak ${fib_state["fib_extreme"]:.2f})',
                    }
                if new_sl < sl:
                    return {
                        'action': 'HOLD',
                        'reason': f'Phase2 트레일링 SL 갱신 ${sl:.2f} → ${new_sl:.2f}',
                        'update_sl': new_sl,
                    }
        
        # Phase 2 미발동 hard SL (breakeven)
        if side == 'LONG' and current_price <= sl:
            _cleanup_state(fib_key)
            return {
                'action': 'CLOSE_ALL',
                'reason': f'Phase2 Breakeven SL @ ${sl:.2f}',
            }
        if side == 'SHORT' and current_price >= sl:
            _cleanup_state(fib_key)
            return {
                'action': 'CLOSE_ALL',
                'reason': f'Phase2 Breakeven SL @ ${sl:.2f}',
            }
    
    return {'action': 'HOLD', 'reason': f'유지 (현재 ${current_price:.2f})'}


def reset_all_states():
    global _BOT_FIB_STATE
    _BOT_FIB_STATE = {}
