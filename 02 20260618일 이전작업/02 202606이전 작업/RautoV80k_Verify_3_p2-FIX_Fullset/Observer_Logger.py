# ==============================================================================
# [파일명] Observer_Logger.py
# 코드길이: 약 380줄, 내부버전: V80k_Verify_1, 로직축약·생략 없이 전체 출력
# 작성일: 2026-05-01
# ==============================================================================
# [정체성]
#   Observer R/P/E 모듈이 시나리오 1~12 데이터를 단일 CSV에 통합 기록하기 위한 로거.
#   거래 결정에 영향 없음 — 순수 부수 효과(side effect)로만 작동.
#   key노트 #NotifierIntegration 패턴 적용:
#     - Silent disabled (디스크 쓰기 실패 시 비활성)
#     - Try-except 격리 (로깅 실패 → 호출자 영향 X)
#     - 송신 직렬화 (ObserverCSV 단일 파일 동시 쓰기 방지)
#     - 일별 rotation (파일 비대화 방지)
#
# [📥 IN] log_observation(record_dict)
# [📤 OUT] /<base>/RautoV80k_Observer_<bot_id>_YYYYMMDD.csv
#
# [기록 컬럼 (50개) — 시나리오 1~12 통합]
#   기본 (5): time_local, bar_ts, bot_id, price, observer_version
#   시나리오 1 (4): regime_output, regime_proba_BULL/BEAR/CHOP
#   시나리오 2 (5): tbm_action, tbm_proba_LONG/SHORT/NO_PROFIT, tbm_env_used
#   시나리오 3 (30): 30 피처 컬럼 (FEATURE_COLS의 각 값)
#   시나리오 4 (4): ob_bull_count, ob_bear_count, sl_raw_pct_candidate, tp_raw_pct_candidate
#   시나리오 5 (1): block_gate (enum: PASS / WARMUP / NAN / ENV_UNCERTAIN /
#                        TBM_LOW_CONF / NO_PROFIT / MATCHGATE / OB_INSUFFICIENT /
#                        SL_TOO_FAR / RR_INSUFFICIENT)
#   시나리오 6 (2): input_hash (df 마지막 봉 hash), pauto_compatible_signal_dict
#   시나리오 7 (3): r_inference_ms, p_inference_ms, ob_analysis_ms
#   시나리오 8 (4): subregime, prev_subregime, dwell_locked_until, q90/q70/q40
#   시나리오 9 (3): env_changed_flag, prev_env, transition_bar_ago
#   시나리오 10 (2): warmup_bars_seen, regime_warmup_done
#   시나리오 11 (3): label_horizon_high, label_horizon_low, label_horizon_close
#                   (사후 30분 뒤에 채워짐 — 별도 함수)
#   시나리오 12 (4): sim_action, sim_entry_price, sim_sl_price, sim_tp_price
# ==============================================================================

import os
import sys
import csv
import time
import threading
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

# ==============================================================================
# 설정
# ==============================================================================
KST = timezone(timedelta(hours=9))
OBSERVER_VERSION = 'V80k_Verify_1_Observer_R001'

# Base 디렉토리 — 환경변수 우선, 없으면 모듈 위치
BASE_DIR = os.environ.get('PAUTO_BASE_DIR') or os.path.dirname(os.path.abspath(__file__))

# 송신 직렬화 (멀티 봇 동시 쓰기 방지)
_LOG_LOCK = threading.RLock()
_FILE_HANDLES: Dict[str, Any] = {}  # bot_id → (writer, fp, current_date_str)
_INIT_FAILED_NOTIFIED = False

# CSV 컬럼 (순서 고정 — 50개)
COLUMNS = [
    # 기본
    'time_local', 'bar_ts', 'bot_id', 'price', 'observer_version',
    # 시나리오 1: R 분포
    'regime_output', 'regime_proba_BULL', 'regime_proba_BEAR', 'regime_proba_CHOP',
    # 시나리오 2: TBM 분포
    'tbm_action', 'tbm_proba_LONG', 'tbm_proba_SHORT', 'tbm_proba_NO_PROFIT', 'tbm_env_used',
    # 시나리오 3: 30 피처 (값은 동적 — feature_<name> 형식)
    # → write_record에서 feature_dict로 처리
    # 시나리오 4: OB 분석
    'ob_bull_count', 'ob_bear_count', 'sl_raw_pct_candidate', 'tp_raw_pct_candidate',
    # 시나리오 5: 게이트
    'block_gate',
    # 시나리오 6: 챔피언 정합성
    'input_hash',
    # 시나리오 7: 시스템 헬스
    'r_inference_ms', 'p_inference_ms', 'ob_analysis_ms',
    # 시나리오 8: Sub-regime
    'subregime', 'prev_subregime', 'dwell_locked_until_bar', 'q90', 'q70', 'q40',
    # 시나리오 9: 환경 전환
    'env_changed_flag', 'prev_env',
    # 시나리오 10: Cold-start
    'warmup_bars_seen', 'regime_warmup_done',
    # 시나리오 11: 사후 라벨 (30분 뒤 fill)
    'label_horizon_high', 'label_horizon_low', 'label_horizon_close', 'label_class',
    # 시나리오 12: Observer 시뮬 신호
    'sim_action', 'sim_entry_price', 'sim_sl_price', 'sim_tp_price',
]

# 시나리오 3: 30 피처 (FEATURE_COLS) — lazy import
_FEATURE_COLS = None
def _get_feature_cols():
    global _FEATURE_COLS
    if _FEATURE_COLS is None:
        try:
            sys.path.insert(0, BASE_DIR)
            from PautoV80_Regime_ML import FEATURE_COLS
            _FEATURE_COLS = list(FEATURE_COLS)
        except Exception:
            _FEATURE_COLS = []
    return _FEATURE_COLS


def get_full_columns():
    """기본 컬럼 + feature_* 30개 합친 전체 컬럼 리스트."""
    feat_cols = _get_feature_cols()
    feature_columns = [f'feature_{f}' for f in feat_cols]
    return COLUMNS + feature_columns


# ==============================================================================
# 파일 회전 (일별)
# ==============================================================================
def _get_csv_path(bot_id: str, date_str: Optional[str] = None) -> str:
    if date_str is None:
        date_str = datetime.now(KST).strftime('%Y%m%d')
    return os.path.join(BASE_DIR, f'RautoV80k_Observer_{bot_id}_{date_str}.csv')


def _open_writer(bot_id: str):
    """일별 CSV 파일 열기 — 파일 없으면 헤더 작성."""
    global _INIT_FAILED_NOTIFIED
    today = datetime.now(KST).strftime('%Y%m%d')

    # 기존 핸들 있고 같은 날짜면 재사용
    if bot_id in _FILE_HANDLES:
        writer, fp, prev_date = _FILE_HANDLES[bot_id]
        if prev_date == today:
            return writer, fp
        # 날짜 바뀜 → 닫고 새로
        try:
            fp.close()
        except Exception:
            pass
        del _FILE_HANDLES[bot_id]

    csv_path = _get_csv_path(bot_id, today)
    file_exists = os.path.exists(csv_path)

    try:
        fp = open(csv_path, 'a', newline='', encoding='utf-8-sig', buffering=1)
        writer = csv.DictWriter(fp, fieldnames=get_full_columns(), extrasaction='ignore')
        if not file_exists:
            writer.writeheader()
            fp.flush()
        _FILE_HANDLES[bot_id] = (writer, fp, today)
        return writer, fp
    except Exception as e:
        if not _INIT_FAILED_NOTIFIED:
            logging.warning(f"[Observer_Logger] CSV 열기 실패 ({csv_path}): {e} — 비활성")
            _INIT_FAILED_NOTIFIED = True
        return None, None


# ==============================================================================
# 핵심 API
# ==============================================================================
def log_observation(record: Dict[str, Any]) -> bool:
    """단일 봉 관찰 기록 — 거래 영향 없음, 실패 시 silent.

    [📥 IN] record dict — COLUMNS에 정의된 키들 (없으면 빈 값)
    [📤 OUT] bool (성공/실패, 호출자는 무시 OK)
    """
    if 'bot_id' not in record:
        return False
    bot_id = str(record['bot_id'])

    with _LOG_LOCK:
        try:
            writer, fp = _open_writer(bot_id)
            if writer is None:
                return False
            # time_local 자동
            if 'time_local' not in record or not record.get('time_local'):
                record['time_local'] = datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')
            if 'observer_version' not in record:
                record['observer_version'] = OBSERVER_VERSION
            writer.writerow(record)
            return True
        except Exception as e:
            # 1회만 알림
            global _INIT_FAILED_NOTIFIED
            if not _INIT_FAILED_NOTIFIED:
                logging.warning(f"[Observer_Logger] write 실패: {e}")
                _INIT_FAILED_NOTIFIED = True
            return False


def compute_input_hash(df, last_n_bars: int = 5) -> str:
    """챔피언 정합성 검증용 (시나리오 6) — df 마지막 N봉 hash.

    Pauto 백테에서 같은 데이터로 추론 시 같은 hash → 같은 결과 검증 가능.
    """
    try:
        if df is None or len(df) < last_n_bars:
            return ''
        tail = df.tail(last_n_bars)
        cols_to_hash = ['close', 'high', 'low', 'volume']
        cols_present = [c for c in cols_to_hash if c in tail.columns]
        if not cols_present:
            return ''
        s = tail[cols_present].to_string(float_format='%.4f')
        return hashlib.md5(s.encode('utf-8')).hexdigest()[:16]
    except Exception:
        return ''


# ==============================================================================
# 사후 라벨 (시나리오 11) — 30분 뒤 채우기
# ==============================================================================
def fill_horizon_labels(bot_id: str,
                         current_bar_ts_ms: int,
                         current_high: float,
                         current_low: float,
                         current_close: float,
                         horizon_minutes: int = 30) -> int:
    """현재 봉 정보를 (current_bar_ts - horizon_minutes) 봉의 라벨로 사후 기록.

    [📥 IN]
      bot_id, current_bar_ts_ms (현재 봉 timestamp), current high/low/close
    [📤 OUT]
      업데이트된 행 수 (디버깅용)

    [동작]
      현재 봉이 시각 T라면, T-30분 봉의 record에서 미래 30분 sim 데이터로
      label_horizon_high/low/close + label_class 산출.

    [Lookahead 안전]
      이 함수는 사후 기록 — 학습/추론에 사용 안 함. 분석용 데이터만 채움.
    """
    target_ts_ms = current_bar_ts_ms - horizon_minutes * 60 * 1000
    csv_path = _get_csv_path(bot_id)
    # 어제 파일도 확인 (자정 넘어간 경우)
    yesterday = (datetime.now(KST) - timedelta(days=1)).strftime('%Y%m%d')
    csv_path_yesterday = _get_csv_path(bot_id, yesterday)

    candidates = [p for p in (csv_path, csv_path_yesterday) if os.path.exists(p)]
    if not candidates:
        return 0

    # 단순 in-memory rewrite (동시성 보호)
    with _LOG_LOCK:
        rows_updated = 0
        for path in candidates:
            try:
                with open(path, 'r', encoding='utf-8-sig', newline='') as fp:
                    reader = csv.DictReader(fp)
                    rows = list(reader)
                    fieldnames = reader.fieldnames

                modified = False
                for row in rows:
                    try:
                        bar_ts = int(float(row.get('bar_ts', 0)))
                    except Exception:
                        continue
                    if bar_ts != target_ts_ms:
                        continue
                    if row.get('label_horizon_close'):
                        continue  # 이미 채워짐

                    # 라벨 계산
                    try:
                        entry = float(row.get('price', 0))
                        if entry <= 0:
                            continue
                        # 단순화: TP 0.30% / SL 0.10%, LONG 가정
                        TP_PCT = 0.30
                        SL_PCT = 0.10
                        long_tp = entry * (1 + TP_PCT / 100)
                        long_sl = entry * (1 - SL_PCT / 100)
                        short_tp = entry * (1 - TP_PCT / 100)
                        short_sl = entry * (1 + SL_PCT / 100)

                        long_win = current_high >= long_tp and current_low > long_sl
                        short_win = current_low <= short_tp and current_high < short_sl

                        if long_win:
                            label_class = 'LONG_WIN'
                        elif short_win:
                            label_class = 'SHORT_WIN'
                        else:
                            label_class = 'NO_PROFIT'

                        row['label_horizon_high'] = f'{current_high:.2f}'
                        row['label_horizon_low'] = f'{current_low:.2f}'
                        row['label_horizon_close'] = f'{current_close:.2f}'
                        row['label_class'] = label_class
                        modified = True
                        rows_updated += 1
                    except Exception:
                        continue

                if modified:
                    # 파일 통째 다시 쓰기 (현재 핸들이 같은 파일이면 기존 핸들 충돌 — 임시 닫기)
                    if path == csv_path and bot_id in _FILE_HANDLES:
                        try:
                            _FILE_HANDLES[bot_id][1].close()
                        except Exception:
                            pass
                        del _FILE_HANDLES[bot_id]

                    with open(path, 'w', encoding='utf-8-sig', newline='') as fp:
                        writer = csv.DictWriter(fp, fieldnames=fieldnames, extrasaction='ignore')
                        writer.writeheader()
                        writer.writerows(rows)
            except Exception as e:
                logging.warning(f"[Observer_Logger] horizon label 업데이트 실패 ({path}): {e}")

        return rows_updated


# ==============================================================================
# 종료 처리
# ==============================================================================
def close_all():
    """모든 파일 핸들 닫기 (시스템 종료 시)."""
    with _LOG_LOCK:
        for bot_id, (writer, fp, _) in list(_FILE_HANDLES.items()):
            try:
                fp.flush()
                fp.close()
            except Exception:
                pass
        _FILE_HANDLES.clear()


# 모듈 종료 시 자동 정리
import atexit
atexit.register(close_all)


# ==============================================================================
# Selftest
# ==============================================================================
def _selftest():
    """기본 동작 점검 — 임시 파일에 1행 기록, 읽기, 정리."""
    import tempfile
    global BASE_DIR
    orig_base = BASE_DIR
    BASE_DIR = tempfile.mkdtemp(prefix='observer_test_')

    record = {
        'bot_id': 'TEST',
        'bar_ts': 1735689600000,
        'price': 70000.0,
        'regime_output': 'BULL',
        'regime_proba_BULL': 0.72,
        'regime_proba_BEAR': 0.10,
        'regime_proba_CHOP': 0.18,
        'block_gate': 'PASS',
    }
    ok = log_observation(record)
    print(f"[selftest] log: {ok}")

    record['bot_id'] = 'TEST'
    record['bar_ts'] = 1735689660000
    record['price'] = 70010.0
    record['block_gate'] = 'TBM_LOW_CONF'
    ok = log_observation(record)
    print(f"[selftest] log 2: {ok}")

    close_all()

    # 읽어보기
    today = datetime.now(KST).strftime('%Y%m%d')
    path = os.path.join(BASE_DIR, f'RautoV80k_Observer_TEST_{today}.csv')
    print(f"[selftest] file: {path}")
    if os.path.exists(path):
        with open(path) as f:
            lines = f.readlines()
        print(f"[selftest] lines: {len(lines)}")
        print(f"[selftest] header cols: {len(lines[0].split(','))}")
    else:
        print("[selftest] FAIL: file not created")

    BASE_DIR = orig_base


if __name__ == '__main__':
    _selftest()
