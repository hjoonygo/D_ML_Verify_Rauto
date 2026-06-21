# ==============================================================================
# [파일명] E_Observer_V80k_R001.py
# 코드길이: 약 100줄, 내부버전: V80k_Verify_1, 로직축약·생략 없이 전체 출력
# 작성일: 2026-05-01
# ==============================================================================
# [정체성]
#   E_ML_V80k_3balancedTBM_R001의 Observer 변형.
#   ★ Observer 봇 슬롯의 "이중 안전장치" — 절대 포지션 보유 안 함.
#
#   E 모듈은 evaluate_exit 인터페이스로 BotManager가 매봉 호출.
#   Observer E 모듈은:
#     - 포지션 정보를 받아도 무조건 'NO_ACTION' 반환
#     - 호출 자체가 일어나면 안 되지만 (P_Observer가 항상 WAIT라서 진입 자체가 없음),
#       이중 방어 차원에서 강제 청산 등 절대 불가하게
#
# [📥 IN]
#   current_price, bot_state, params
# [📤 OUT]
#   dict: {action: 'NO_ACTION', reason: 'Observer mode'}
# ==============================================================================

import os
import time
import logging

try:
    from Observer_Logger import log_observation
    _LOGGER_OK = True
except Exception:
    _LOGGER_OK = False
    log_observation = lambda *a, **k: False


def evaluate_exit(current_price: float, bot_state, params: dict) -> dict:
    """V80k E 모듈 인터페이스 호환. 절대 진입/청산 액션 안 함.

    [📥 IN]
      current_price: 현재가
      bot_state: 봇 상태 객체 (position 등)
      params: master_params
    [📤 OUT]
      dict: action='NO_ACTION', reason='Observer mode — 거래 영향 X'
    """
    bot_id = str(params.get('bot_id', 'observer'))

    # 만약 어떤 이유로든 position이 있다면 (방어적) — 즉시 경고 로그 + 그래도 NO_ACTION
    has_position = False
    try:
        if bot_state is not None and hasattr(bot_state, 'position'):
            has_position = bot_state.position.get('side', 'WAIT') != 'WAIT'
    except Exception:
        pass

    if has_position:
        # 절대 일어나면 안 되는 상황 — Observer 봇에 포지션이 있다는 건 P_Observer가 OPEN을 반환했다는 뜻
        logging.error(f"[E_Observer:{bot_id}] ⚠️ 비정상: Observer 봇에 포지션 발견. P_Observer 점검 필요.")
        # 그래도 액션 안 함 (이중 안전)

    # 정상 경로
    return {
        'action': 'NO_ACTION',
        'reason': 'Observer mode — 거래 영향 X (이중 안전장치)',
    }


def reset_cache():
    """원본 인터페이스 호환 — Observer는 캐시 없음."""
    pass


if __name__ == '__main__':
    print(f"[E_Observer] Logger OK: {_LOGGER_OK}")
    print(f"[E_Observer] 항상 NO_ACTION 반환")
    # 임시 테스트
    class FakeBot:
        position = {'side': 'WAIT'}
    res = evaluate_exit(70000.0, FakeBot(), {'bot_id': 'TEST'})
    print(f"[E_Observer] test result: {res}")
