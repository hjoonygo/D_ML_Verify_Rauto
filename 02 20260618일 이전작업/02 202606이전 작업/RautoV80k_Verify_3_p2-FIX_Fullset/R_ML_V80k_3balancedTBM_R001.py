# ==============================================================================
# 파일명: R_ML_V80k_3balancedTBM_R001.py
# 코드길이: 약 130줄 / 내부버전: V8.0k 챔피언 시스템 외부 R 모듈 첫 번째
# 작성일: 2026-04-29
# ==============================================================================
# [전략 정체성]
#   ML 기반 환경 판단. BULL/BEAR/CHOP 3환경 균형 잡힌 알파.
#   Regime v6 (33MB) → 환경 1단계 게이트 (conf>=0.5)
#
# [V75 인터페이스 — Pauto/Rauto 공용]
#   📥 IN
#     - df (DataFrame): 1m 봉 (timestamp ms 또는 DatetimeIndex)
#     - params (dict): TradingEngine master_params (사용 안 함)
#   📤 OUT
#     - str: "BULL (0.72)" / "BEAR (0.65)" / "CHOP (0.81)"
#            "UNCERTAIN (0.43)" / "워밍업 (n/4000)"
#
# [페어 모듈]
#   - P_ML_V80k_3balancedTBM_R001.py  ← 진입 결정
#   - E_ML_V80k_3balancedTBM_R001.py  ← 청산 결정
# ==============================================================================
import os
import sys
import pandas as pd
import numpy as np

# ★ V80k_Verify_2: BASE_DIR 결정 (모델 위치 우선순위)
BASE_DIR = os.environ.get('PAUTO_BASE_DIR') or os.path.dirname(os.path.abspath(__file__))
# 1순위: 환경변수 또는 자기 폴더
if not os.path.exists(os.path.join(BASE_DIR, "PautoV80_Regime_Model_v6.json")):
    # 2순위: strategies/_workspace의 모델 폴더 (Verify_2 권장 위치)
    _workspace_models = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     'strategies', '_workspace', '3balancedTBM_R001', 'models')
    if os.path.exists(os.path.join(_workspace_models, "PautoV80_Regime_Model_v6.json")):
        BASE_DIR = _workspace_models
    else:
        # 3순위: strategies_extracted (런타임 추출 디렉토리)
        _extracted_models = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         'strategies_extracted', '3balancedTBM_R001', 'models')
        if os.path.exists(os.path.join(_extracted_models, "PautoV80_Regime_Model_v6.json")):
            BASE_DIR = _extracted_models
        else:
            # 4순위: 기존 fallback
            for cand in [r"C:\rauto", r"C:\OPT", r"C:\pauto"]:
                if os.path.exists(os.path.join(cand, "PautoV80_Regime_Model_v6.json")):
                    BASE_DIR = cand
                    break
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import xgboost as xgb
from PautoV80_Regime_ML import compute_features, FEATURE_COLS

# ==============================================================================
# 운영 설정
# ==============================================================================
REGIME_CONF_THRESHOLD = 0.5
MIN_WARMUP_BARS = 4000

# ==============================================================================
# 모듈 전역 (lazy load + 캐시)
# ==============================================================================
_REGIME_MODEL = None
_LAST_FEAT_TS = None
_LAST_RESULT = "UNCERTAIN"


def _load_model():
    global _REGIME_MODEL
    if _REGIME_MODEL is not None:
        return _REGIME_MODEL
    
    model_path = os.path.join(BASE_DIR, "PautoV80_Regime_Model_v6.json")
    if not os.path.exists(model_path):
        print(f"[R_ML_V80k] ❌ 모델 파일 없음: {model_path}")
        return None
    
    try:
        m = xgb.XGBClassifier()
        m.load_model(model_path)
        _REGIME_MODEL = m
        print(f"[R_ML_V80k] ✅ Regime v6 로드 완료")
        return m
    except Exception as e:
        print(f"[R_ML_V80k] ❌ 모델 로드 실패: {e}")
        return None


def determine_regime_kinematics(df: pd.DataFrame, params: dict) -> str:
    """V75 환경 판단 인터페이스."""
    global _LAST_FEAT_TS, _LAST_RESULT
    
    if df is None or len(df) < MIN_WARMUP_BARS:
        n = len(df) if df is not None else 0
        return f"워밍업 ({n}/{MIN_WARMUP_BARS})"
    
    # 캐시 — 같은 timestamp는 재추론 안 함
    if 'timestamp' in df.columns:
        last_ts = df['timestamp'].iloc[-1]
    else:
        last_ts = df.index[-1]
    
    if last_ts == _LAST_FEAT_TS:
        return _LAST_RESULT
    
    is_first_call = (_LAST_FEAT_TS is None)
    _LAST_FEAT_TS = last_ts
    
    # ★ v3: 첫 호출 시 진단 print
    if is_first_call:
        print(f"[R_ML_V80k] 첫 추론 시작 — df 크기 {len(df)}봉, 4500봉 피처 산출 중 (10~60초 소요)")
    
    try:
        model = _load_model()
        if model is None:
            return "UNCERTAIN"
    except Exception as e:
        import traceback as _tb
        print(f"[R_ML_V80k] ❌ 모델 로드 실패:")
        print(_tb.format_exc())
        return "UNCERTAIN"
    
    # 데이터 표준화 — V75 df는 timestamp 컬럼, 우리 모듈은 DatetimeIndex 요구
    try:
        work_df = df.copy()
        if 'timestamp' in work_df.columns:
            work_df['timestamp'] = pd.to_datetime(work_df['timestamp'], unit='ms', utc=True)
            work_df = work_df.set_index('timestamp')
        closed_df = work_df.iloc[:-1]  # 마감 봉만 (lookahead 차단)
    except Exception as e:
        import traceback as _tb
        print(f"[R_ML_V80k] ❌ 데이터 표준화 실패:")
        print(_tb.format_exc())
        return "UNCERTAIN"
    
    try:
        if is_first_call:
            import time as _t
            t0 = _t.time()
            print(f"[R_ML_V80k] compute_features 시작...")
        feat = compute_features(closed_df)
        if is_first_call:
            print(f"[R_ML_V80k] compute_features 완료 ({_t.time()-t0:.1f}초)")
        if feat.empty or feat[FEATURE_COLS].iloc[-1].isna().any():
            _LAST_RESULT = "UNCERTAIN"
            return _LAST_RESULT
        x = feat[FEATURE_COLS].iloc[-1:].values
    except Exception as e:
        import traceback as _tb
        print(f"[R_ML_V80k] ❌ 피처 산출 오류:")
        print(_tb.format_exc())
        _LAST_RESULT = "UNCERTAIN"
        return _LAST_RESULT
    
    try:
        proba = model.predict_proba(x)[0]
        pred = int(np.argmax(proba))
        conf = float(proba.max())
        
        if is_first_call:
            print(f"[R_ML_V80k] ✅ 첫 추론 완료 — pred={['BULL','BEAR','CHOP'][pred]} conf={conf:.4f}")
        
        if conf < REGIME_CONF_THRESHOLD:
            _LAST_RESULT = f"UNCERTAIN ({conf:.2f})"
            return _LAST_RESULT
        
        env_name = ['BULL', 'BEAR', 'CHOP'][pred]
        _LAST_RESULT = f"{env_name} ({conf:.2f})"
        return _LAST_RESULT
    except Exception as e:
        import traceback as _tb
        print(f"[R_ML_V80k] ❌ 추론 오류:")
        print(_tb.format_exc())
        _LAST_RESULT = "UNCERTAIN"
        return _LAST_RESULT


def reset_cache():
    global _LAST_FEAT_TS, _LAST_RESULT
    _LAST_FEAT_TS = None
    _LAST_RESULT = "UNCERTAIN"
