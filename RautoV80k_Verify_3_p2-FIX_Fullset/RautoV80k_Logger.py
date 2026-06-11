# ==============================================================================
# 파일명: RautoV80k_Logger.py
# 코드길이: 약 170줄 / 내부버전: V8.0k v2 (자취 남기기 강화)
# 작성일: 2026-04-29
# ==============================================================================
# [정체성]
#   봇 ID별로 로직/모듈의 작동을 자취로 남기는 중앙 로깅 모듈.
#   "테스트의 기본은 자취를 남기는 것" — 선장 원칙.
#
# [생성 파일 4종]
#   1. RautoV80k_System.log              ← 시스템 전체 이벤트 (텍스트)
#   2. RautoV80k_BotState_Bot_N.csv      ← 봇별 매 봉 상태 (regime, conf, action 등)
#   3. RautoV80k_TradeLog_Bot_N.csv      ← 봇별 거래 이벤트 (진입/청산)
#   4. RautoV80k_Equity.csv              ← 통합 자본 곡선 (모든 봇)
#
# [엑셀 충돌 방지]
#   파일이 잠겨있어도 큐에 쌓아 다음 기회에 기록 (시스템 안 멈춤)
# ==============================================================================
import os
import sys
import csv
import logging
import threading
from collections import deque
from datetime import datetime

BASE_DIR = os.environ.get('PAUTO_BASE_DIR') or os.path.dirname(os.path.abspath(__file__))


# ==============================================================================
# 1. 시스템 로거 (System.log)
# ==============================================================================
def setup_system_logger():
    """RautoV80k_System.log + 콘솔 동시 출력."""
    log_path = os.path.join(BASE_DIR, "RautoV80k_System.log")
    
    logger = logging.getLogger('RautoV80k')
    logger.setLevel(logging.INFO)
    
    # 중복 핸들러 방지
    if logger.handlers:
        return logger, log_path
    
    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    
    # 파일 핸들러
    fh = logging.FileHandler(log_path, encoding='utf-8')
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    
    # 콘솔 핸들러
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    
    logger.info(f"=== RautoV80k 시스템 로거 시작 (파일: {log_path}) ===")
    return logger, log_path


# ==============================================================================
# 2. CSV Writer 베이스 (엑셀 충돌 방지)
# ==============================================================================
class SafeCsvWriter:
    """파일 잠겼어도 큐에 쌓아 다음 기회에 기록."""
    
    def __init__(self, file_path, columns):
        self.file_path = file_path
        self.columns = columns
        self.queue = deque()
        self.lock = threading.Lock()
        
        # 헤더 초기화 (파일 없으면)
        if not os.path.exists(file_path):
            try:
                with open(file_path, 'w', newline='', encoding='utf-8') as f:
                    csv.writer(f).writerow(columns)
            except Exception as e:
                print(f"[SafeCsvWriter] 헤더 쓰기 실패: {e}")
    
    def write(self, row_dict):
        """row_dict는 {col_name: value, ...}. columns 순서대로 정렬해 기록."""
        row = [row_dict.get(c, '') for c in self.columns]
        
        with self.lock:
            self.queue.append(row)
            self._flush()
    
    def _flush(self):
        if not self.queue:
            return
        try:
            with open(self.file_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                while self.queue:
                    writer.writerow(self.queue.popleft())
        except PermissionError:
            # 엑셀로 열려있으면 큐에 그대로 보관
            pass
        except Exception as e:
            print(f"[SafeCsvWriter] 쓰기 오류 ({self.file_path}): {e}")


# ==============================================================================
# 3. 봇별 상태 CSV (매 봉)
# ==============================================================================
BOTSTATE_COLUMNS = [
    'time_utc', 'time_local', 'bar_ts',
    'bot_id', 'bot_state', 'position_side',
    'regime_module', 'regime_output', 'regime_conf',
    'predict_module', 'tbm_action', 'tbm_conf', 'tbm_env',
    'execute_module', 'exit_action',
    'price', 'capital', 'unrealized_pnl', 'realized_pnl', 'wallet_balance',
    'reason'
]

# 봇별 writer 캐시
_BOTSTATE_WRITERS = {}

def get_botstate_writer(bot_id):
    if bot_id not in _BOTSTATE_WRITERS:
        path = os.path.join(BASE_DIR, f"RautoV80k_BotState_{bot_id}.csv")
        _BOTSTATE_WRITERS[bot_id] = SafeCsvWriter(path, BOTSTATE_COLUMNS)
    return _BOTSTATE_WRITERS[bot_id]


def log_bot_state(bot_id, bot, current_regime, last_signal, last_exit, price, bar_ts):
    """매 봉 마감 시 봇 상태 1줄 기록."""
    now = datetime.utcnow()
    
    # regime conf 추출 (R 모듈 출력 "BULL (0.72)" 형태)
    regime_conf = None
    regime_clean = current_regime
    if '(' in current_regime and ')' in current_regime:
        try:
            regime_conf = float(current_regime[current_regime.find('(')+1:current_regime.find(')')])
            regime_clean = current_regime.split('(')[0].strip()
        except Exception:
            pass
    
    # signal 정보
    tbm_action = last_signal.get('action', '-') if last_signal else '-'
    tbm_conf = last_signal.get('tbm_conf', None) if last_signal else None
    tbm_env = last_signal.get('env', '-') if last_signal else '-'
    sig_reason = last_signal.get('reason', '') if last_signal else ''
    
    # exit 정보
    exit_action = last_exit.get('action', '-') if last_exit else '-'
    exit_reason = last_exit.get('reason', '') if last_exit else ''
    
    reason_combined = sig_reason if sig_reason else exit_reason
    
    row = {
        'time_utc': now.strftime('%Y-%m-%d %H:%M:%S'),
        'time_local': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'bar_ts': bar_ts,
        'bot_id': bot_id,
        'bot_state': bot.state.name if hasattr(bot.state, 'name') else str(bot.state),
        'position_side': bot.position.get('side', 'WAIT'),
        'regime_module': bot.modules.get('regime', '-') or '-',
        'regime_output': regime_clean,
        'regime_conf': f"{regime_conf:.4f}" if regime_conf is not None else '',
        'predict_module': bot.modules.get('predict', '-') or '-',
        'tbm_action': tbm_action,
        'tbm_conf': f"{tbm_conf:.4f}" if tbm_conf is not None else '',
        'tbm_env': tbm_env,
        'execute_module': bot.modules.get('execute', '-') or '-',
        'exit_action': exit_action,
        'price': f"{price:.2f}",
        'capital': f"{bot.capital:.2f}",
        'unrealized_pnl': f"{bot.unrealized_pnl:+.2f}",
        'realized_pnl': f"{bot.realized_pnl:+.2f}",
        'wallet_balance': f"{bot.wallet_balance:.2f}",
        'reason': reason_combined[:200]  # 200자 제한
    }
    get_botstate_writer(bot_id).write(row)


# ==============================================================================
# 4. 봇별 거래 CSV
# ==============================================================================
TRADELOG_COLUMNS = [
    'time_utc', 'time_local', 'bot_id', 'event',
    'side', 'env', 'regime_conf', 'tbm_conf',
    'entry_price', 'exit_price',
    'sl_price', 'tp_price',
    'leverage', 'amount', 'risk_pct',
    'pnl', 'pnl_pct',
    'capital_after', 'wallet_after',
    'exit_type', 'reason'
]

_TRADELOG_WRITERS = {}

def get_tradelog_writer(bot_id):
    if bot_id not in _TRADELOG_WRITERS:
        path = os.path.join(BASE_DIR, f"RautoV80k_TradeLog_{bot_id}.csv")
        _TRADELOG_WRITERS[bot_id] = SafeCsvWriter(path, TRADELOG_COLUMNS)
    return _TRADELOG_WRITERS[bot_id]


def log_trade_event(bot_id, event_type, info):
    """진입(OPEN_LONG/OPEN_SHORT) 또는 청산(CLOSE_ALL/CLOSE_HALF) 발생 시."""
    now = datetime.utcnow()
    row = {
        'time_utc': now.strftime('%Y-%m-%d %H:%M:%S'),
        'time_local': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'bot_id': bot_id,
        'event': event_type,
        **{k: info.get(k, '') for k in [
            'side', 'env', 'regime_conf', 'tbm_conf',
            'entry_price', 'exit_price', 'sl_price', 'tp_price',
            'leverage', 'amount', 'risk_pct',
            'pnl', 'pnl_pct', 'capital_after', 'wallet_after',
            'exit_type', 'reason'
        ]}
    }
    get_tradelog_writer(bot_id).write(row)


# ==============================================================================
# 5. 통합 Equity CSV (모든 봇)
# ==============================================================================
EQUITY_COLUMNS = [
    'time_utc', 'time_local', 'bar_ts',
    'bot_id', 'state', 'side',
    'capital', 'unrealized_pnl', 'realized_pnl', 'wallet_balance', 'total_equity',
    'price'
]

_EQUITY_WRITER = None

def get_equity_writer():
    global _EQUITY_WRITER
    if _EQUITY_WRITER is None:
        path = os.path.join(BASE_DIR, "RautoV80k_Equity.csv")
        _EQUITY_WRITER = SafeCsvWriter(path, EQUITY_COLUMNS)
    return _EQUITY_WRITER


def log_equity_snapshot(bot_id, bot, price, bar_ts):
    """매 봉 마감 시 봇 자본 상태 1줄."""
    now = datetime.utcnow()
    total = bot.capital + bot.unrealized_pnl + bot.wallet_balance
    row = {
        'time_utc': now.strftime('%Y-%m-%d %H:%M:%S'),
        'time_local': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'bar_ts': bar_ts,
        'bot_id': bot_id,
        'state': bot.state.name if hasattr(bot.state, 'name') else str(bot.state),
        'side': bot.position.get('side', 'WAIT'),
        'capital': f"{bot.capital:.2f}",
        'unrealized_pnl': f"{bot.unrealized_pnl:+.2f}",
        'realized_pnl': f"{bot.realized_pnl:+.2f}",
        'wallet_balance': f"{bot.wallet_balance:.2f}",
        'total_equity': f"{total:.2f}",
        'price': f"{price:.2f}"
    }
    get_equity_writer().write(row)


# ==============================================================================
# 6. 봉 마감 추적 헬퍼
# ==============================================================================
_LAST_BAR_TS = None  # 시스템 전체 마지막 봉 timestamp

def is_new_bar(current_bar_ts):
    """이 봉이 새 봉이면 True. 같은 봉(진행 중)이면 False."""
    global _LAST_BAR_TS
    if _LAST_BAR_TS != current_bar_ts:
        _LAST_BAR_TS = current_bar_ts
        return True
    return False


def reset_bar_tracker():
    global _LAST_BAR_TS
    _LAST_BAR_TS = None
