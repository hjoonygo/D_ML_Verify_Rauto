# ==============================================================================
# [파일명] P_Observer_V80k_R001.py
# 코드길이: 약 380줄, 내부버전: V80k_Verify_1, 로직축약·생략 없이 전체 출력
# 작성일: 2026-05-01
# ==============================================================================
# [정체성]
#   P_ML_V80k_3balancedTBM_R001의 Observer 변형.
#   인터페이스 100% 동일: get_signal(df, current_regime, params) → dict
#   ★ 절대 OPEN_LONG / OPEN_SHORT 반환하지 않음 — 항상 WAIT.
#   ★ "만약 진입했다면" 시그널은 sim_action 필드에 기록만.
#
#   기록 항목 (Observer_Logger):
#     - 시나리오 2: TBM 3-class proba
#     - 시나리오 4: OB 분석 (bull/bear count, sl_raw, tp_raw)
#     - 시나리오 5: block_gate enum (정확한 차단 사유)
#     - 시나리오 7: P 추론 시간, OB 분석 시간
#     - 시나리오 8: Sub-regime + dwell lock 상태 (params['subregime'] 활용)
#     - 시나리오 12: sim_action (만약 진입할 거였다면)
#
# [📥 IN]
#   df, current_regime, params (bot_id, subregime 포함)
# [📤 OUT]
#   dict {action: 'WAIT', ...}  ← 항상 WAIT
# ==============================================================================

import os
import sys
import time
import logging
import pandas as pd
import numpy as np

# ★ V80k_Verify_2: Observer는 base 전략(3balancedTBM_R001)의 models/ 참조
_STRATEGY_DIR = os.path.dirname(os.path.abspath(__file__))
# 임시 추출 디렉토리: strategies_extracted/Observer_R001 → ../3balancedTBM_R001/models
_BASE_STRATEGY_MODELS = os.path.normpath(os.path.join(_STRATEGY_DIR, '..', '3balancedTBM_R001', 'models'))
BASE_DIR = os.environ.get('PAUTO_BASE_DIR') or _STRATEGY_DIR

if os.path.exists(os.path.join(_BASE_STRATEGY_MODELS, "PautoV80_TBM_BULL_v2.json")):
    BASE_DIR = _BASE_STRATEGY_MODELS
elif not os.path.exists(os.path.join(BASE_DIR, "PautoV80_TBM_BULL_v2.json")):
    for cand in [r"C:\rauto", r"C:\OPT", r"C:\pauto"]:
        if os.path.exists(os.path.join(cand, "PautoV80_TBM_BULL_v2.json")):
            BASE_DIR = cand
            break
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import xgboost as xgb
from PautoV80_Regime_ML import compute_features, FEATURE_COLS

try:
    from Observer_Logger import log_observation
    _LOGGER_OK = True
except Exception:
    _LOGGER_OK = False
    log_observation = lambda *a, **k: False

# ==============================================================================
# 운영 설정 — V80k 원본과 동일
# ==============================================================================
TBM_CONF_THRESHOLD = 0.5
COST_PCT = 0.11
MIN_WARMUP_BARS = 4000

ENV_SL_RR = {
    'BULL': {'sl_raw_pct': 0.10, 'rr_margin_pct': 0.07},
    'BEAR': {'sl_raw_pct': 0.10, 'rr_margin_pct': 0.07},
    'CHOP': {'sl_raw_pct': 0.10, 'rr_margin_pct': 0.07},
}

# ==============================================================================
# 모듈 전역
# ==============================================================================
_TBM_CACHE = {'BULL': None, 'BEAR': None, 'CHOP': None}
_LAST_TS = None
_LAST_RESULT = {'action': 'WAIT', 'reason': 'init'}


def _load_tbm(env_name: str):
    if _TBM_CACHE[env_name] is not None:
        return _TBM_CACHE[env_name]
    p = os.path.join(BASE_DIR, f"PautoV80_TBM_{env_name}_v2.json")
    if not os.path.exists(p):
        return None
    try:
        m = xgb.XGBClassifier()
        m.load_model(p)
        _TBM_CACHE[env_name] = m
        print(f"[P_Observer] ✅ TBM_{env_name}_v2 로드")
        return m
    except Exception as e:
        print(f"[P_Observer] ❌ TBM_{env_name} 로드 실패: {e}")
        return None


def _calc_leverage(sl_raw_pct: float) -> int:
    """원본 V80k 동일 — 매매조건 1: 1.6% notional, SL distance × leverage = 1.6%."""
    if sl_raw_pct <= 0:
        return 1
    lev = max(1, int(1.6 / sl_raw_pct))
    return min(lev, 50)


def _find_order_blocks(df: pd.DataFrame, current_price: float):
    """원본 V80k와 동일한 OB 탐색. 시나리오 4용 정량 데이터 산출."""
    bull_obs = []
    bear_obs = []
    if df is None or len(df) < 20:
        return bull_obs, bear_obs

    LOOKBACK = 100
    sub = df.tail(LOOKBACK).copy()
    if 'high' not in sub.columns or 'low' not in sub.columns or 'open' not in sub.columns or 'close' not in sub.columns:
        return bull_obs, bear_obs

    for i in range(len(sub) - 3):
        # 단순 OB 정의 (원본 동일성 유지 시도)
        if sub['close'].iloc[i] < sub['open'].iloc[i]:
            # 음봉 → bull OB 후보 (반등 시작점)
            if i + 3 < len(sub) and sub['close'].iloc[i + 3] > sub['high'].iloc[i]:
                bull_obs.append({
                    'top': float(sub['high'].iloc[i]),
                    'bottom': float(sub['low'].iloc[i]),
                    'mean': float((sub['high'].iloc[i] + sub['low'].iloc[i]) / 2)
                })
        if sub['close'].iloc[i] > sub['open'].iloc[i]:
            if i + 3 < len(sub) and sub['close'].iloc[i + 3] < sub['low'].iloc[i]:
                bear_obs.append({
                    'top': float(sub['high'].iloc[i]),
                    'bottom': float(sub['low'].iloc[i]),
                    'mean': float((sub['high'].iloc[i] + sub['low'].iloc[i]) / 2)
                })

    # 현재가 기준 가까운 것 우선
    bull_obs = sorted([ob for ob in bull_obs if ob['top'] < current_price],
                      key=lambda o: -o['top'])[:3]
    bear_obs = sorted([ob for ob in bear_obs if ob['bottom'] > current_price],
                      key=lambda o: o['bottom'])[:3]
    return bull_obs, bear_obs


def _wait(reason: str, **extras) -> dict:
    """항상 WAIT 반환. extras는 reason에만 영향."""
    out = {'action': 'WAIT', 'reason': reason}
    out.update(extras)
    return out


def get_signal(df: pd.DataFrame, current_regime: str, params: dict) -> dict:
    """V80k P 모듈 인터페이스 호환. ★ 항상 WAIT 반환 (Observer는 거래 안 함).

    내부적으로 정상 추론 후 모든 데이터 Observer_Logger에 기록.
    'sim_action' 필드에 "만약 진입했다면" 결과 기록 (시나리오 12).
    """
    global _LAST_TS, _LAST_RESULT

    bot_id = str(params.get('bot_id', 'observer'))
    t_start = time.time()

    if df is None or len(df) < MIN_WARMUP_BARS:
        out = _wait("워밍업 부족")
        return out

    # 환경 추출
    env_name = None
    if current_regime.startswith("BULL"):
        env_name = "BULL"
    elif current_regime.startswith("BEAR"):
        env_name = "BEAR"
    elif current_regime.startswith("CHOP"):
        env_name = "CHOP"

    if env_name is None:
        # 환경 미확정 — 추론 자체 안 함
        return _wait(f"환경 미확정 ({current_regime})")

    # 캐시
    if 'timestamp' in df.columns:
        last_ts = int(df['timestamp'].iloc[-1])
    else:
        last_ts = int(time.time() * 1000)
    if last_ts == _LAST_TS:
        return _LAST_RESULT
    _LAST_TS = last_ts

    tbm_model = _load_tbm(env_name)
    if tbm_model is None:
        out = _wait(f"{env_name} 모델 로드 실패")
        _LAST_RESULT = out
        return out

    work_df = df.copy()
    if 'timestamp' in work_df.columns:
        work_df['timestamp'] = pd.to_datetime(work_df['timestamp'], unit='ms', utc=True)
        work_df = work_df.set_index('timestamp')
    closed_df = work_df.iloc[:-1]
    current_price = float(work_df['close'].iloc[-1])

    # === 핵심 추론 (timing 측정) ===
    block_gate = 'PASS'
    tbm_proba = (0.0, 0.0, 0.0)
    sim_action = 'WAIT'
    sim_entry = 0.0
    sim_sl = 0.0
    sim_tp = 0.0
    ob_bull_count = 0
    ob_bear_count = 0
    sl_raw_pct = 0.0
    tp_raw_pct = 0.0
    ob_analysis_ms = 0.0

    try:
        feat = compute_features(closed_df)
        if feat.empty or feat[FEATURE_COLS].iloc[-1].isna().any():
            block_gate = 'NAN'
        else:
            x = feat[FEATURE_COLS].iloc[-1:].values
            proba_arr = tbm_model.predict_proba(x)[0]
            # 클래스 매핑: 0=LONG_WIN, 1=SHORT_WIN, 2=NO_PROFIT
            tbm_proba = (float(proba_arr[0]), float(proba_arr[1]), float(proba_arr[2]))
            pred = int(proba_arr.argmax())
            conf = float(proba_arr.max())

            if conf < TBM_CONF_THRESHOLD:
                block_gate = 'TBM_LOW_CONF'
            elif pred == 2:
                block_gate = 'NO_PROFIT'
            else:
                side = 'LONG' if pred == 0 else 'SHORT'

                # matchgate
                if env_name == 'BULL' and side == 'SHORT':
                    block_gate = 'MATCHGATE'
                elif env_name == 'BEAR' and side == 'LONG':
                    block_gate = 'MATCHGATE'
                else:
                    # OB 분석 (시나리오 4)
                    t_ob = time.time()
                    bull_obs, bear_obs = _find_order_blocks(closed_df, current_price)
                    ob_analysis_ms = (time.time() - t_ob) * 1000.0
                    ob_bull_count = len(bull_obs)
                    ob_bear_count = len(bear_obs)

                    if not bull_obs or not bear_obs:
                        block_gate = 'OB_INSUFFICIENT'
                    else:
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
                            block_gate = 'SL_TOO_FAR'
                        elif tp_raw_pct < sl_raw_pct + cond['rr_margin_pct']:
                            block_gate = 'RR_INSUFFICIENT'
                        else:
                            # === 모든 게이트 통과 → "만약 진입했다면" sim 기록 ===
                            block_gate = 'PASS'
                            sim_action = f'OPEN_{side}'
                            sim_entry = current_price
                            sim_sl = float(sl_price)
                            sim_tp = float(tp_price)

    except Exception as e:
        block_gate = 'NAN'
        if not hasattr(get_signal, '_err_count'):
            get_signal._err_count = 0
        get_signal._err_count += 1
        if get_signal._err_count <= 3:
            print(f"[P_Observer] 추론 오류 #{get_signal._err_count}: {e}")

    p_inference_ms = (time.time() - t_start) * 1000.0

    # === Observer 기록 ===
    try:
        # 시나리오 2 + 4 + 5 + 7 + 8 + 12
        record = {
            'bot_id': bot_id,
            'bar_ts': last_ts,
            'price': current_price,
            # 시나리오 2: TBM 분포
            'tbm_action': sim_action,  # WAIT 또는 OPEN_*
            'tbm_proba_LONG': tbm_proba[0],
            'tbm_proba_SHORT': tbm_proba[1],
            'tbm_proba_NO_PROFIT': tbm_proba[2],
            'tbm_env_used': env_name,
            # 시나리오 4: OB
            'ob_bull_count': ob_bull_count,
            'ob_bear_count': ob_bear_count,
            'sl_raw_pct_candidate': round(sl_raw_pct, 4),
            'tp_raw_pct_candidate': round(tp_raw_pct, 4),
            # 시나리오 5: block_gate (정확한 enum)
            'block_gate': block_gate,
            # 시나리오 7: 시스템 헬스
            'p_inference_ms': round(p_inference_ms, 2),
            'ob_analysis_ms': round(ob_analysis_ms, 2),
            # 시나리오 8: Sub-regime (params에서)
            'subregime': params.get('subregime', 'UNCERTAIN'),
            'prev_subregime': params.get('prev_subregime', ''),
            # 시나리오 12: 시뮬 시그널
            'sim_action': sim_action,
            'sim_entry_price': round(sim_entry, 2),
            'sim_sl_price': round(sim_sl, 2),
            'sim_tp_price': round(sim_tp, 2),
        }
        log_observation(record)
    except Exception as log_e:
        if not hasattr(get_signal, '_log_err'):
            get_signal._log_err = 0
        get_signal._log_err += 1
        if get_signal._log_err <= 3:
            logging.warning(f"[P_Observer] 로그 실패: {log_e}")

    # ★ 항상 WAIT 반환 — 거래 일체 안 함
    out = _wait(
        f"[Observer] block_gate={block_gate} sim={sim_action} "
        f"tbm=({tbm_proba[0]:.2f},{tbm_proba[1]:.2f},{tbm_proba[2]:.2f})"
    )
    _LAST_RESULT = out
    return out


def reset_cache():
    global _LAST_TS, _LAST_RESULT
    _LAST_TS = None
    _LAST_RESULT = {'action': 'WAIT', 'reason': 'init'}


if __name__ == '__main__':
    print(f"[P_Observer] BASE_DIR: {BASE_DIR}")
    print(f"[P_Observer] Logger OK: {_LOGGER_OK}")
    for env in ['BULL', 'BEAR', 'CHOP']:
        m = _load_tbm(env)
        print(f"[P_Observer] TBM_{env}: {'OK' if m else 'FAIL'}")
