# ==============================================================================
# [파일명] R_Observer_V80k_R001.py
# 코드길이: 약 250줄, 내부버전: V80k_Verify_1, 로직축약·생략 없이 전체 출력
# 작성일: 2026-05-01
# ==============================================================================
# [정체성]
#   R_ML_V80k_3balancedTBM_R001의 Observer 변형.
#   인터페이스 100% 동일: determine_regime_kinematics(df, params) → str
#   동작 차이:
#     - R 모델 추론 결과 정상 반환 (BotManager가 받아 P 모듈에 전달)
#     - 추가로 시나리오 1, 3, 7, 9, 10 데이터를 Observer_Logger에 기록
#     - 거래 결정에 영향 X (원본과 동일 출력)
#
# [📥 IN]
#   df: 1m DataFrame
#   params: master_params (bot_id 포함 가정)
# [📤 OUT]
#   str: 'BULL (0.72)' / 'BEAR (0.55)' / 'CHOP (0.83)' / 'UNCERTAIN' / 'UNCERTAIN (0.40)' / '워밍업 (N/M)'
#
# [페어 모듈]
#   - P_Observer_V80k_R001.py
#   - E_Observer_V80k_R001.py
#   - Observer_Logger.py
#
# [Lookahead 안전]
#   compute_features는 t-1까지만 사용 (V80k 검증된 모듈).
#   Observer는 추론 결과만 추가 기록 — lookahead 위험 0.
# ==============================================================================

import os
import sys
import time
import logging
import pandas as pd
import numpy as np

# ★ V80k_Verify_2: BASE_DIR 다중 fallback (모델 위치 우선순위)
BASE_DIR = os.environ.get('PAUTO_BASE_DIR') or os.path.dirname(os.path.abspath(__file__))
if not os.path.exists(os.path.join(BASE_DIR, "PautoV80_Regime_Model_v6.json")):
    # 2순위: strategies/_workspace
    _ws = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'strategies', '_workspace', '3balancedTBM_R001', 'models')
    if os.path.exists(os.path.join(_ws, "PautoV80_Regime_Model_v6.json")):
        BASE_DIR = _ws
    else:
        # 3순위: strategies_extracted
        _ext = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'strategies_extracted', '3balancedTBM_R001', 'models')
        if os.path.exists(os.path.join(_ext, "PautoV80_Regime_Model_v6.json")):
            BASE_DIR = _ext
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

# Observer Logger import (실패 시 silent)
try:
    from Observer_Logger import log_observation, compute_input_hash, fill_horizon_labels
    _OBSERVER_LOGGER_OK = True
except Exception as _e:
    _OBSERVER_LOGGER_OK = False
    log_observation = lambda *a, **k: False
    compute_input_hash = lambda *a, **k: ''
    fill_horizon_labels = lambda *a, **k: 0

# ==============================================================================
# 운영 설정
# ==============================================================================
REGIME_CONF_THRESHOLD = 0.5
MIN_WARMUP_BARS = 4000

# ==============================================================================
# 모듈 전역
# ==============================================================================
_REGIME_MODEL = None
_LAST_FEAT_TS = None
_LAST_RESULT = "UNCERTAIN"
_LAST_PROBA = (0.0, 0.0, 0.0)  # BULL, BEAR, CHOP
_LAST_FEATURES_DICT = {}
_PREV_ENV = None
_BARS_SEEN = 0  # 시나리오 10: warmup tracking

# Observer 사후 라벨 산출용 큐 (bot_id별)
_HORIZON_LABEL_QUEUE = {}  # bot_id → list of (bar_ts_ms, high, low, close)


def _load_model():
    global _REGIME_MODEL
    if _REGIME_MODEL is not None:
        return _REGIME_MODEL
    p = os.path.join(BASE_DIR, "PautoV80_Regime_Model_v6.json")
    if not os.path.exists(p):
        return None
    try:
        m = xgb.XGBClassifier()
        m.load_model(p)
        _REGIME_MODEL = m
        print("[R_Observer] ✅ Regime_Model_v6 로드")
        return m
    except Exception as e:
        print(f"[R_Observer] ❌ 모델 로드 실패: {e}")
        return None


def determine_regime_kinematics(df: pd.DataFrame, params: dict) -> str:
    """V80k R 모듈 인터페이스 호환. 추가로 Observer_Logger에 시나리오 1/3/7/9/10 기록."""
    global _LAST_FEAT_TS, _LAST_RESULT, _LAST_PROBA, _LAST_FEATURES_DICT
    global _PREV_ENV, _BARS_SEEN

    bot_id = str(params.get('bot_id', 'observer'))
    _BARS_SEEN += 1

    # 워밍업
    if df is None or len(df) < MIN_WARMUP_BARS:
        n = len(df) if df is not None else 0
        result = f"워밍업 ({n}/{MIN_WARMUP_BARS})"
        # 워밍업 중 기록 — 시나리오 10
        try:
            log_observation({
                'bot_id': bot_id,
                'bar_ts': int(df['timestamp'].iloc[-1]) if df is not None and 'timestamp' in df.columns else int(time.time() * 1000),
                'price': float(df['close'].iloc[-1]) if df is not None and len(df) > 0 else 0.0,
                'regime_output': 'WARMUP',
                'warmup_bars_seen': n,
                'regime_warmup_done': False,
                'block_gate': 'WARMUP',
            })
        except Exception:
            pass
        return result

    model = _load_model()
    if model is None:
        return "UNCERTAIN"

    # 캐시 (timestamp 기반)
    if 'timestamp' in df.columns:
        last_ts_ms = int(df['timestamp'].iloc[-1])
    else:
        # index 기반
        last_ts_ms = int(time.time() * 1000)

    if last_ts_ms == _LAST_FEAT_TS:
        return _LAST_RESULT

    _LAST_FEAT_TS = last_ts_ms

    # === 핵심 추론 (timing 측정) ===
    t_start = time.time()

    work_df = df.copy()
    if 'timestamp' in work_df.columns:
        work_df['timestamp'] = pd.to_datetime(work_df['timestamp'], unit='ms', utc=True)
        work_df = work_df.set_index('timestamp')
    closed_df = work_df.iloc[:-1]  # 마감된 봉만
    current_price = float(work_df['close'].iloc[-1])

    feat_compute_ms = 0.0
    feature_dict = {}
    proba = (0.0, 0.0, 0.0)
    pred_idx = -1
    conf = 0.0
    block_reason = 'PASS'
    result = 'UNCERTAIN'

    try:
        t_feat = time.time()
        feat = compute_features(closed_df)
        feat_compute_ms = (time.time() - t_feat) * 1000.0

        if feat.empty or feat[FEATURE_COLS].iloc[-1].isna().any():
            result = 'UNCERTAIN'
            block_reason = 'NAN'
        else:
            x_row = feat[FEATURE_COLS].iloc[-1]
            feature_dict = {f'feature_{c}': float(x_row[c]) for c in FEATURE_COLS}
            x = x_row.values.reshape(1, -1)

            t_inf = time.time()
            proba_arr = model.predict_proba(x)[0]
            inference_ms = (time.time() - t_inf) * 1000.0

            # 클래스 매핑: 0=BULL, 1=BEAR, 2=CHOP (V80k 학습 시)
            proba = (float(proba_arr[0]), float(proba_arr[1]), float(proba_arr[2]))
            pred_idx = int(proba_arr.argmax())
            conf = float(proba_arr.max())

            env_map = {0: 'BULL', 1: 'BEAR', 2: 'CHOP'}
            env_str = env_map.get(pred_idx, 'UNCERTAIN')

            if conf >= REGIME_CONF_THRESHOLD:
                result = f"{env_str} ({conf:.2f})"
            else:
                result = f"UNCERTAIN ({conf:.2f})"
                block_reason = 'ENV_UNCERTAIN'

    except Exception as e:
        result = 'UNCERTAIN'
        block_reason = 'NAN'
        feat_compute_ms = (time.time() - t_start) * 1000.0
        # 1회만 출력
        if not hasattr(determine_regime_kinematics, '_err_count'):
            determine_regime_kinematics._err_count = 0
        determine_regime_kinematics._err_count += 1
        if determine_regime_kinematics._err_count <= 3:
            print(f"[R_Observer] 추론 오류 #{determine_regime_kinematics._err_count}: {e}")

    total_r_ms = (time.time() - t_start) * 1000.0

    _LAST_RESULT = result
    _LAST_PROBA = proba
    _LAST_FEATURES_DICT = feature_dict

    # === Observer 로그 기록 ===
    try:
        # 시나리오 9: 환경 전환 추적
        cur_env = result.split(' ')[0] if ' ' in result else result
        env_changed = (_PREV_ENV is not None and _PREV_ENV != cur_env
                       and cur_env in ('BULL', 'BEAR', 'CHOP', 'UNCERTAIN')
                       and _PREV_ENV in ('BULL', 'BEAR', 'CHOP'))

        record = {
            'bot_id': bot_id,
            'bar_ts': last_ts_ms,
            'price': current_price,
            # 시나리오 1: R 분포
            'regime_output': cur_env if cur_env in ('BULL', 'BEAR', 'CHOP', 'UNCERTAIN') else 'UNCERTAIN',
            'regime_proba_BULL': proba[0],
            'regime_proba_BEAR': proba[1],
            'regime_proba_CHOP': proba[2],
            # 시나리오 5: block_gate
            'block_gate': block_reason,
            # 시나리오 6: 정합성 hash
            'input_hash': compute_input_hash(closed_df),
            # 시나리오 7: 시스템 헬스 (R만, P/E는 자기 모듈에서)
            'r_inference_ms': round(total_r_ms, 2),
            # 시나리오 9: 환경 전환
            'env_changed_flag': env_changed,
            'prev_env': _PREV_ENV if _PREV_ENV else '',
            # 시나리오 10: cold-start
            'warmup_bars_seen': _BARS_SEEN,
            'regime_warmup_done': True,
        }
        # 시나리오 3: 30 피처 추가
        record.update(feature_dict)

        log_observation(record)

        # === 시나리오 11: 사후 라벨 (현재 봉이 30분 전 봉의 사후 데이터) ===
        # 큐에 (ts, high, low, close) 추가
        if 'high' in work_df.columns and 'low' in work_df.columns:
            current_high = float(work_df['high'].iloc[-1])
            current_low = float(work_df['low'].iloc[-1])
            current_close = current_price
            # 30분 전 record에 사후 라벨 채우기
            try:
                fill_horizon_labels(bot_id, last_ts_ms, current_high, current_low, current_close,
                                    horizon_minutes=30)
            except Exception:
                pass
    except Exception as log_e:
        # 로깅 실패해도 거래 영향 X
        if not hasattr(determine_regime_kinematics, '_log_err_count'):
            determine_regime_kinematics._log_err_count = 0
        determine_regime_kinematics._log_err_count += 1
        if determine_regime_kinematics._log_err_count <= 3:
            logging.warning(f"[R_Observer] 로그 실패 #{determine_regime_kinematics._log_err_count}: {log_e}")

    _PREV_ENV = cur_env

    return result


def get_last_proba():
    """P_Observer가 R의 proba를 가져갈 때 사용 (시나리오 1 + 2 통합 기록용)."""
    return _LAST_PROBA


def get_last_features():
    """P_Observer가 같은 봉의 피처를 사용 — 중복 compute 회피."""
    return dict(_LAST_FEATURES_DICT)


def reset_cache():
    global _LAST_FEAT_TS, _LAST_RESULT, _LAST_PROBA, _LAST_FEATURES_DICT, _PREV_ENV, _BARS_SEEN
    _LAST_FEAT_TS = None
    _LAST_RESULT = "UNCERTAIN"
    _LAST_PROBA = (0.0, 0.0, 0.0)
    _LAST_FEATURES_DICT = {}
    _PREV_ENV = None
    _BARS_SEEN = 0


if __name__ == '__main__':
    print(f"[R_Observer] BASE_DIR: {BASE_DIR}")
    print(f"[R_Observer] Logger OK: {_OBSERVER_LOGGER_OK}")
    print(f"[R_Observer] FEATURE_COLS: {len(FEATURE_COLS)}")
    m = _load_model()
    print(f"[R_Observer] Model: {'OK' if m else 'FAIL'}")
