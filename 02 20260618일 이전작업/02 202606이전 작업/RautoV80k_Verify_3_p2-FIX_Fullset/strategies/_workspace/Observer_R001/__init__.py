# ==============================================================================
# [파일명] strategies/Observer_R001/__init__.py
# 내부버전: V80k_Verify_2
# ==============================================================================

from . import R_module
from . import P_module
from . import E_module


def get_modules():
    return R_module, P_module, E_module


__strategy_name__ = 'Observer_R001'
__internal_version__ = 'V80k_Verify_1'
__is_observer__ = True
__safety_guarantee__ = 'P always WAIT, E always NO_ACTION'
