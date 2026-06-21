# ==============================================================================
# 파일명: P_ML_V80k_3balancedTBM_R001.py
# 코드길이: 약 280줄 / 내부버전: V80k_Verify_1 / 로직축약·생략 없이 전체 출력
# 작성일: 2026-04-29 (원본) / 갱신: 2026-05-01 (V80k_Verify_1: sub-regime 게이트 통합)
# ==============================================================================
# [전략 정체성]
#   환경별 TBM v2 모델로 진입 결정 + SMC OB 기반 SL/TP 산출
#   매매조건 1·2·3 적용 (1.6% 한도, 0.11% 비용, 환경별 SL/RR 게이트)
#   ★ V80k_Verify_1: Sub-regime 게이트 3종 추가 (옵션, 기본 비활성)
#
# [V75 인터페이스 — Pauto/Rauto 공용]
#   📥 IN
#     - df (DataFrame): 1m 봉
#     - current_regime (str): R 모듈 결과 ("BULL (0.72)" 등)
#     - params (dict): TradingEngine master_params
#       ★ NEW: params['subregime']: 'BULL_T1' 등 (BotManager가 SubregimeManager로 산출)
#       ★ NEW: params['enable_subregime_gates']: bool (기본 False, 기존 V80k 호환)
#       ★ NEW: params['bear_t12_aux_features']: np.ndarray (게이트 3용, optional)
#   📤 OUT
#     - dict: {action, entry_price, sl_price, tp_price, leverage,
#              risk_pct, sl_raw_pct, tp_raw_pct, env, tbm_conf, reason}
#       action: "OPEN_LONG" / "OPEN_SHORT" / "WAIT"
#
# [페어 모듈]
#   - R_ML_V80k_3balancedTBM_R001.py
#   - E_ML_V80k_3balancedTBM_R001.py
#   - RautoV80k_Subregime.py (V80k_Verify_1 신규)
#
# [V80k_Verify_1 게이트 3종 — 19개월 실측 검증 결과]
#   - 게이트 1: CHOP_T1 차단 (NO_PROFIT 정확도 98.6%)
#   - 게이트 2: Tier 1/2만 진입 (BULL_T1 acc 75% > T4 66%)
#   - 게이트 3: BEAR_T12 보조 모델 합의 (short precision 47.1%, 현재 stub)
#
# [⚠️ 운영 주의]
#   walk-forward 12회 검증 미실시. 실거래 가동 전 다음 사이클 Phase 4 검증 필수.
#   기본은 enable_subregime_gates=False (게이트 비활성) — 기존 V80k와 100% 동일 동작.
# ==============================================================================
import os
import sys
import pandas as pd
import numpy as np

# ★ V80k_Verify_2: Strategy ZIP 내부 models/ 우선
_STRATEGY_DIR = os.path.dirname(os.path.abspath(__file__))
_STRATEGY_MODELS_DIR = os.path.join(_STRATEGY_DIR, 'models')
BASE_DIR = os.environ.get('PAUTO_BASE_DIR') or _STRATEGY_DIR

if os.path.exists(os.path.join(_STRATEGY_MODELS_DIR, "PautoV80_TBM_BULL_v2.json")):
    BASE_DIR = _STRATEGY_MODELS_DIR
elif not os.path.exists(os.path.join(BASE_DIR, "PautoV80_TBM_BULL_v2.json")):
    for cand in [r"C:\rauto", r"C:\OPT", r"C:\pauto"]:
        if os.path.exists(os.path.join(cand, "PautoV80_TBM_BULL_v2.json")):
            BASE_DIR = cand
            break
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import xgboost as xgb
from PautoV80_Regime_ML import compute_features, FEATURE_COLS

# ★ V80k_Verify_1: Sub-regime 게이트 모듈 (옵션, lazy import 실패 시 비활성)
try:
    from RautoV80k_Subregime import EntryGates, BearT12AuxModel
    _SUBREGIME_AVAILABLE = True
    _ENTRY_GATES_CACHE = {}  # bot 단위 게이트 캐시 (params['bot_id'] 기준)
except Exception as _sub_e:
    EntryGates = None
    BearT12AuxModel = None
    _SUBREGIME_AVAILABLE = False
    _ENTRY_GATES_CACHE = {}
    print(f"[P 모듈] Subregime 모듈 import 실패 → 게이트 비활성: {_sub_e}")

# ==============================================================================
# 운영 설정 (V8.0k S1_c50 권장값)
# ==============================================================================
TBM_CONF_THRESHOLD = 0.5
MAX_LOSS_PCT = 1.6
COST_PCT = 0.11

ENV_SL_RR = {
    'BULL': {'sl_raw_pct': 0.10, 'rr_margin_pct': 0.07},
    'BEAR': {'sl_raw_pct': 0.10, 'rr_margin_pct': 0.07},
    'CHOP': {'sl_raw_pct': 0.15, 'rr_margin_pct': 0.08},
}

OB_LOOKBACK = 100
MIN_WARMUP_BARS = 4000

# ==============================================================================
# 모듈 전역
# ==============================================================================
_TBM_MODELS = {}
_LAST_TS = None
_LAST_SIGNAL = {"action": "WAIT", "reason": "초기"}


def _load_tbm(env_name: str):
    if env_name in _TBM_MODELS:
        return _TBM_MODELS[env_name]
    
    path = os.path.join(BASE_DIR, f"PautoV80_TBM_{env_name}_v2.json")
    if not os.path.exists(path):
        print(f"[P_ML_V80k] ❌ {env_name} 모델 없음: {path}")
        return None
    
    try:
        m = xgb.XGBClassifier()
        m.load_model(path)
        _TBM_MODELS[env_name] = m
        print(f"[P_ML_V80k] ✅ TBM_{env_name}_v2 로드")
        return m
    except Exception as e:
        print(f"[P_ML_V80k] ❌ {env_name} 로드 실패: {e}")
        return None


def _calc_leverage(sl_raw_pct: float) -> int:
    """매매조건 1: leverage = 1.6% / (SL_raw + 0.11%)"""
    return max(1, min(20, int(MAX_LOSS_PCT / (sl_raw_pct + COST_PCT))))


def _find_order_blocks(df: pd.DataFrame, current_price: float):
    lookback = df.tail(OB_LOOKBACK)
    highs = lookback['high'].values
    lows = lookback['low'].values
    bear_obs, bull_obs = [], []
    for i in range(2, len(highs) - 2):
        if highs[i] == max(highs[i-2:i+3]) and highs[i] > current_price:
            bear_obs.append({
                'top': float(highs[i]), 'bottom': float(lows[i]),
                'mean': float((highs[i] + lows[i]) / 2)
            })
        if lows[i] == min(lows[i-2:i+3]) and lows[i] < current_price:
            bull_obs.append({
                'top': float(highs[i]), 'bottom': float(lows[i]),
                'mean': float((highs[i] + lows[i]) / 2)
            })
    bull_obs = sorted(bull_obs, key=lambda x: x['top'], reverse=True)
    bear_obs = sorted(bear_obs, key=lambda x: x['bottom'])
    return bull_obs, bear_obs


def _wait(reason: str) -> dict:
    return {"action": "WAIT", "reason": reason}


def get_signal(df: pd.DataFrame, current_regime: str, params: dict) -> dict:
    """V75 진입 결정 인터페이스."""
    global _LAST_TS, _LAST_SIGNAL
    
    if df is None or len(df) < MIN_WARMUP_BARS:
        return _wait("워밍업 부족")
    
    # 환경 추출 (R 모듈 출력 "BULL (0.72)")
    env_name = None
    if current_regime.startswith("BULL"): env_name = "BULL"
    elif current_regime.startswith("BEAR"): env_name = "BEAR"
    elif current_regime.startswith("CHOP"): env_name = "CHOP"
    else:
        return _wait(f"환경 미확정 ({current_regime})")
    
    # 캐시
    if 'timestamp' in df.columns:
        last_ts = df['timestamp'].iloc[-1]
    else:
        last_ts = df.index[-1]
    if last_ts == _LAST_TS:
        return _LAST_SIGNAL
    _LAST_TS = last_ts
    
    tbm_model = _load_tbm(env_name)
    if tbm_model is None:
        _LAST_SIGNAL = _wait(f"{env_name} 모델 로드 실패")
        return _LAST_SIGNAL
    
    work_df = df.copy()
    if 'timestamp' in work_df.columns:
        work_df['timestamp'] = pd.to_datetime(work_df['timestamp'], unit='ms', utc=True)
        work_df = work_df.set_index('timestamp')
    closed_df = work_df.iloc[:-1]
    current_price = float(work_df['close'].iloc[-1])
    
    try:
        feat = compute_features(closed_df)
        if feat.empty or feat[FEATURE_COLS].iloc[-1].isna().any():
            _LAST_SIGNAL = _wait("피처 결측")
            return _LAST_SIGNAL
        x = feat[FEATURE_COLS].iloc[-1:].values
    except Exception as e:
        _LAST_SIGNAL = _wait(f"피처 오류: {str(e)[:50]}")
        return _LAST_SIGNAL
    
    try:
        proba = tbm_model.predict_proba(x)[0]
        pred = int(np.argmax(proba))
        conf = float(proba.max())
    except Exception as e:
        _LAST_SIGNAL = _wait(f"TBM 추론 오류: {str(e)[:50]}")
        return _LAST_SIGNAL
    
    if conf < TBM_CONF_THRESHOLD:
        _LAST_SIGNAL = _wait(f"{env_name} TBM conf 미달 ({conf:.2f})")
        return _LAST_SIGNAL
    
    if pred == 2:  # NO_PROFIT
        _LAST_SIGNAL = _wait(f"{env_name} NO_PROFIT 시그널 (conf {conf:.2f})")
        return _LAST_SIGNAL
    
    side = 'LONG' if pred == 0 else 'SHORT'
    
    # 환경-방향 매칭
    if env_name == 'BULL' and side == 'SHORT':
        _LAST_SIGNAL = _wait(f"BULL 환경 + SHORT 시그널 (matchgate)")
        return _LAST_SIGNAL
    if env_name == 'BEAR' and side == 'LONG':
        _LAST_SIGNAL = _wait(f"BEAR 환경 + LONG 시그널 (matchgate)")
        return _LAST_SIGNAL
    
    # ★ V80k_Verify_1: Sub-regime 게이트 3종 (옵션 활성)
    if params.get('enable_subregime_gates', False) and _SUBREGIME_AVAILABLE:
        subregime = params.get('subregime', 'UNCERTAIN')
        if subregime == 'UNCERTAIN':
            _LAST_SIGNAL = _wait(f"Sub-regime UNCERTAIN — 워밍업 또는 conf < 0.5")
            return _LAST_SIGNAL
        
        # 봇별 EntryGates 인스턴스 (캐시)
        bot_id = params.get('bot_id', 'default')
        if bot_id not in _ENTRY_GATES_CACHE:
            aux_mode = params.get('bear_t12_aux_mode', 'always_pass')
            aux_path = params.get('bear_t12_aux_model_path', None)
            aux_model = BearT12AuxModel(mode=aux_mode, model_path=aux_path)
            _ENTRY_GATES_CACHE[bot_id] = EntryGates(
                enable_gate1_chop_t1=params.get('enable_gate1', True),
                enable_gate2_tier12_only=params.get('enable_gate2', True),
                enable_gate3_bear_aux=params.get('enable_gate3', True),
                bear_aux_model=aux_model,
            )
        gates = _ENTRY_GATES_CACHE[bot_id]
        
        features_row = params.get('bear_t12_aux_features', None)
        gate_pass, gate_reason = gates.evaluate_all(subregime, features_row)
        if not gate_pass:
            _LAST_SIGNAL = _wait(f"[Verify_1] {gate_reason}")
            return _LAST_SIGNAL
    
    # OB 기반 SL/TP
    bull_obs, bear_obs = _find_order_blocks(closed_df, current_price)
    if not bull_obs or not bear_obs:
        _LAST_SIGNAL = _wait("OB 부족 (bull/bear 양쪽 필요)")
        return _LAST_SIGNAL
    
    if side == 'LONG':
        sl_price = bull_obs[0]['bottom']
        tp_price = bear_obs[0]['mean']
        sl_raw_pct = (current_price - sl_price) / current_price * 100
        tp_raw_pct = (tp_price - current_price) / current_price * 100
    else:
        sl_price = bear_obs[0]['top']
        tp_price = bull_obs[0]['mean']
        sl_raw_pct = (sl_price - current_price) / current_price * 100
        tp_raw_pct = (current_price - tp_price) / current_price * 100
    
    # 매매조건 3
    cond = ENV_SL_RR[env_name]
    if sl_raw_pct > cond['sl_raw_pct']:
        _LAST_SIGNAL = _wait(
            f"SL 거리 초과 ({sl_raw_pct:.3f}% > {cond['sl_raw_pct']:.2f}%)"
        )
        return _LAST_SIGNAL
    if tp_raw_pct < sl_raw_pct + cond['rr_margin_pct']:
        _LAST_SIGNAL = _wait(
            f"RR margin 미달 (TP {tp_raw_pct:.3f}% < SL+margin {sl_raw_pct + cond['rr_margin_pct']:.3f}%)"
        )
        return _LAST_SIGNAL
    
    leverage = _calc_leverage(sl_raw_pct)
    risk_pct = leverage * (sl_raw_pct + COST_PCT) / 100
    
    action = 'OPEN_LONG' if side == 'LONG' else 'OPEN_SHORT'
    _LAST_SIGNAL = {
        'action': action,
        'entry_price': current_price,
        'sl_price': float(sl_price),
        'tp_price': float(tp_price),
        'leverage': leverage,
        'risk_pct': risk_pct,
        'sl_raw_pct': float(sl_raw_pct),
        'tp_raw_pct': float(tp_raw_pct),
        'env': env_name,
        'tbm_conf': conf,
        'reason': (f"{env_name} {side} | tbm {conf:.2f} | "
                  f"SL {sl_raw_pct:.3f}% TP {tp_raw_pct:.3f}% lev {leverage}x"),
    }
    return _LAST_SIGNAL


def reset_cache():
    global _LAST_TS, _LAST_SIGNAL
    _LAST_TS = None
    _LAST_SIGNAL = {"action": "WAIT", "reason": "리셋"}
