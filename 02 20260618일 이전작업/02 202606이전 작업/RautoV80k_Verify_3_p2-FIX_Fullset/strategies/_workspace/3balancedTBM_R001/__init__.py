# ==============================================================================
# [파일명] strategies/3balancedTBM_R001/__init__.py
# 내부버전: V80k_Verify_2 (V80k_Verify_1 산출물의 ZIP 패키징)
# ==============================================================================
# StrategyLoader가 이 패키지를 import하면 R/P/E 모듈을 자동 노출.
# ==============================================================================

from . import R_module
from . import P_module
from . import E_module

# 표준 인터페이스
def get_modules():
    """StrategyLoader가 호출. (R, P, E) 모듈 객체 반환."""
    return R_module, P_module, E_module


# 메타데이터는 metadata.json에서 읽음 — StrategyLoader가 처리
__strategy_name__ = '3balancedTBM_R001'
__internal_version__ = 'V80k_Verify_1'
__is_observer__ = False
