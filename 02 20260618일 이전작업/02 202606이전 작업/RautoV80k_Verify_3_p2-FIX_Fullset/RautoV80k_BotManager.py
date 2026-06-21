# ==============================================================================
# 파일명: RautoV80k_BotManager.py
# 코드길이: 약 180줄 / 내부버전: V8.0k (V75 기반 패치)
# 작성일: 2026-04-29
# ==============================================================================
# [패치 사항 (V75 → V80k)]
#   - signal['leverage']를 받아 매매조건 1 적용 (amount = capital × lev / price)
#   - bot_state['bot_id'] 전달 (E 모듈 충돌 방지)
#   - 기존 V75 risk_per_trade_pct fallback 유지 (기존 V75 P 모듈 호환)
# ==============================================================================
import importlib
import logging
import sys
import os
from enum import Enum

# ★ V80k_Verify_1: Sub-regime 관리자 (옵션, import 실패 시 비활성)
try:
    from RautoV80k_Subregime import SubregimeManager
    _SUBREGIME_MGR_AVAILABLE = True
except Exception as _e:
    SubregimeManager = None
    _SUBREGIME_MGR_AVAILABLE = False
    logging.warning(f"[BotManager] SubregimeManager import 실패: {_e}")

BASE_DIR = os.environ.get('PAUTO_BASE_DIR') or os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)


class BotState(Enum):
    WAITING = 0
    RUNNING = 1
    EXITING = 2
    FORCE_CLOSED = 3


class RautoV80k_BotManager:
    def __init__(self, bot_id: str, initial_capital: float = 10000.0):
        self.bot_id = bot_id
        self.state = BotState.WAITING
        
        self.capital = initial_capital
        self.wallet_balance = 0.0
        self.unrealized_pnl = 0.0
        self.realized_pnl = 0.0
        
        self.position = {
            "side": "WAIT", "entry_price": 0.0, "amount": 0.0,
            "sl_price": 0.0, "tp_price": 0.0, "one_r_dist": 0.0,
            "is_breakeven_on": False, "is_half_taken": False,
            "highest_price": 0.0, "lowest_price": float('inf'),
            "leverage": 1
        }
        
        self.modules = {"regime": None, "predict": None, "execute": None}
        self.regime_instance = None
        self.predict_instance = None
        self.exec_instance = None
        self.current_regime = "대기 중"
        
        # 거래 로그 (Bot ID 팝업에서 보여줄 용도)
        self.trade_history = []  # [{time, action, price, pnl, reason, env}, ...]
        
        # ★ V80k v2: 매 봉 마지막 시그널 추적 (로깅용)
        self.last_signal = None  # P 모듈의 마지막 출력
        self.last_exit = None    # E 모듈의 마지막 출력
        
        # ★ V80k_Verify_1: Sub-regime 관리자 (봇별 인스턴스)
        self.subregime_mgr = SubregimeManager() if _SUBREGIME_MGR_AVAILABLE else None
        self._bar_idx = 0  # sub-regime 분류용 봉 카운터
        
        # ★ V80k_Verify_2: 전략 ZIP 메타
        self._is_observer_bot: bool = False
        self._strategy_name: str = ''

    def update_modules(self, regime_mod: str, predict_mod: str, execute_mod: str) -> None:
        """레거시 호환 — 직접 모듈명 import.

        ★ V80k_Verify_2: 전략 ZIP 사용 시 update_strategy() 권장.
        """
        self.modules.update({'regime': regime_mod, 'predict': predict_mod, 'execute': execute_mod})
        try:
            if regime_mod and regime_mod != "모듈 없음":
                self.regime_instance = importlib.import_module(regime_mod)
            if predict_mod and predict_mod != "모듈 없음":
                self.predict_instance = importlib.import_module(predict_mod)
            if execute_mod and execute_mod != "모듈 없음":
                self.exec_instance = importlib.import_module(execute_mod)
            logging.info(f"[{self.bot_id}] 🧠 외부 모듈 이식 완료 ({regime_mod}/{predict_mod}/{execute_mod})")
        except Exception as e:
            logging.error(f"[{self.bot_id}] ❌ 모듈 로드 실패: {e}")

    def update_strategy(self, strategy_name: str) -> bool:
        """★ V80k_Verify_2: 전략 ZIP 단위 로드.

        [📥 IN]
          strategy_name: 'Observer_R001' 등 (strategies/<name>.zip)
        [📤 OUT]
          bool — 성공/실패
        """
        try:
            from StrategyLoader import load_strategy
            bundle = load_strategy(strategy_name)
            
            # ★ Observer 봇 안전 강제 — 메타데이터에 is_observer=true면 추가 검증
            self._is_observer_bot = bool(bundle.is_observer)
            self._strategy_name = strategy_name
            
            self.regime_instance = bundle.R
            self.predict_instance = bundle.P
            self.exec_instance = bundle.E
            
            self.modules.update({
                'regime': f'{strategy_name}.R_module',
                'predict': f'{strategy_name}.P_module',
                'execute': f'{strategy_name}.E_module',
                'strategy': strategy_name,
            })
            
            obs_marker = ' ★ Observer (거래 X)' if bundle.is_observer else ''
            logging.info(f"[{self.bot_id}] 🧠 전략 이식: {strategy_name} v{bundle.version}{obs_marker}")
            return True
        except Exception as e:
            logging.error(f"[{self.bot_id}] ❌ 전략 로드 실패 ({strategy_name}): {e}")
            return False

    def process_step_signal(self, target_step: int) -> None:
        if target_step == 1: self.state = BotState.RUNNING
        elif target_step == 2: self.state = BotState.EXITING
        elif target_step == 3:
            self.state = BotState.FORCE_CLOSED
            if self.position.get("side") != "WAIT":
                self._execute_close(self.position.get("entry_price", 0), "🚨 강제 종료(Panic)")
        elif target_step == 0: self.state = BotState.WAITING

    def on_tick_data(self, df, current_price: float, params: dict) -> None:
        if self.state not in [BotState.RUNNING, BotState.EXITING]: return

        # 실시간 손익 (레버리지 적용)
        leverage = self.position.get("leverage", 1)
        if self.position.get("side") == "LONG":
            self.unrealized_pnl = (current_price - self.position["entry_price"]) * self.position["amount"]
            self.position["highest_price"] = max(self.position["highest_price"], current_price)
        elif self.position.get("side") == "SHORT":
            self.unrealized_pnl = (self.position["entry_price"] - current_price) * self.position["amount"]
            self.position["lowest_price"] = min(self.position["lowest_price"], current_price)

        # 1. 장세 판단
        if self.regime_instance and hasattr(self.regime_instance, 'determine_regime_kinematics'):
            try:
                # ★ V80k_Verify_1: bot_id 주입 (Observer 모듈이 슬롯별 CSV 작성하도록)
                r_params = dict(params)
                r_params['bot_id'] = self.bot_id
                self.current_regime = self.regime_instance.determine_regime_kinematics(df, r_params)
            except Exception as e:
                import traceback as _tb
                err_detail = _tb.format_exc()
                self.current_regime = f"장세 에러: {str(e)[:50]}"
                # ★ v3: 첫 5번까지만 traceback 출력 (콘솔 도배 방지)
                if not hasattr(self, '_regime_err_count'):
                    self._regime_err_count = 0
                self._regime_err_count += 1
                if self._regime_err_count <= 5:
                    print(f"[{self.bot_id}] R 모듈 에러 #{self._regime_err_count}:")
                    print(err_detail)

        # ★ V80k_Verify_1: Sub-regime 갱신 (R 모듈 결과 기반)
        current_subregime = 'UNCERTAIN'
        if self.subregime_mgr is not None and isinstance(self.current_regime, str):
            try:
                self._bar_idx += 1
                current_subregime = self.subregime_mgr.update(self._bar_idx, self.current_regime)
            except Exception as _se:
                if not hasattr(self, '_sub_err_count'):
                    self._sub_err_count = 0
                self._sub_err_count += 1
                if self._sub_err_count <= 3:
                    print(f"[{self.bot_id}] Sub-regime 에러: {_se}")
                current_subregime = 'UNCERTAIN'

        # 2. 진입 결정
        if self.state == BotState.RUNNING and self.position.get("side") == "WAIT" and self.predict_instance:
            try:
                signal = {"action": "NONE"}
                if hasattr(self.predict_instance, 'get_signal'):
                    # ★ V80k_Verify_1: params에 sub-regime + bot_id 주입 (P 모듈 게이트용)
                    p_params = dict(params)  # 복사 (원본 변경 회피)
                    p_params['subregime'] = current_subregime
                    p_params['bot_id'] = self.bot_id
                    # enable_subregime_gates는 master_params에서 흘러오거나 기본 False
                    p_params.setdefault('enable_subregime_gates', params.get('enable_subregime_gates', False))
                    signal = self.predict_instance.get_signal(df, self.current_regime, p_params)
                
                self.last_signal = signal  # ★ v2: 로깅용 추적
                
                action = signal.get("action", "WAIT")
                
                # ★ V80k_Verify_2: Observer 봇 강제 안전장치 — 5중 방어
                # P_Observer는 항상 WAIT 반환하지만, 만에 하나 OPEN 들어와도 코어가 차단
                if self._is_observer_bot and action in ["OPEN_LONG", "OPEN_SHORT"]:
                    logging.error(
                        f"[{self.bot_id}] 🛑 Observer 봇에 OPEN 시그널 감지! 강제 WAIT 변환. "
                        f"(전략: {self._strategy_name}, P 모듈 점검 필요)"
                    )
                    action = "WAIT"
                    signal = {"action": "WAIT", "reason": "[코어 강제] Observer 봇 OPEN 차단"}
                
                if action in ["OPEN_LONG", "OPEN_SHORT"]:
                    self.position["side"] = "LONG" if action == "OPEN_LONG" else "SHORT"
                    self.position["entry_price"] = signal.get("entry_price", current_price)
                    self.position["sl_price"] = signal.get("sl_price", 0.0)
                    self.position["tp_price"] = signal.get("tp_price", 0.0)
                    
                    # ★ V80k: signal에 leverage 있으면 매매조건 1 자동 적용
                    if "leverage" in signal:
                        lev = signal["leverage"]
                        notional = self.capital * lev
                        self.position["amount"] = notional / current_price
                        self.position["leverage"] = lev
                    else:
                        risk_pct = params.get("risk_per_trade_pct", 0.02)
                        self.position["amount"] = (self.capital * risk_pct) / current_price
                        self.position["leverage"] = 1
                    
                    self.position["one_r_dist"] = abs(self.position["entry_price"] - self.position["sl_price"])
                    self.position["highest_price"] = current_price
                    self.position["lowest_price"] = current_price
                    self.position["is_breakeven_on"] = False
                    self.position["is_half_taken"] = False
                    
                    # 거래 로그 (메모리)
                    import time as _t
                    self.trade_history.append({
                        'time': _t.time(),
                        'action': action,
                        'price': self.position["entry_price"],
                        'sl': self.position["sl_price"],
                        'tp': self.position["tp_price"],
                        'leverage': self.position["leverage"],
                        'env': signal.get('env', 'N/A'),
                        'reason': signal.get('reason', ''),
                    })
                    
                    # ★ V80k v2: 거래 CSV 기록 + 시스템 로그
                    try:
                        from RautoV80k_Logger import log_trade_event, setup_system_logger
                        sys_logger, _ = setup_system_logger()
                        # 환경 conf 추출
                        regime_conf_val = ''
                        cr = self.current_regime
                        if '(' in cr and ')' in cr:
                            try:
                                regime_conf_val = float(cr[cr.find('(')+1:cr.find(')')])
                            except Exception: pass
                        log_trade_event(self.bot_id, action, {
                            'side': self.position['side'],
                            'env': signal.get('env', '-'),
                            'regime_conf': f"{regime_conf_val:.4f}" if regime_conf_val else '',
                            'tbm_conf': f"{signal.get('tbm_conf', 0):.4f}",
                            'entry_price': f"{self.position['entry_price']:.2f}",
                            'sl_price': f"{self.position['sl_price']:.2f}",
                            'tp_price': f"{self.position['tp_price']:.2f}",
                            'leverage': self.position['leverage'],
                            'amount': f"{self.position['amount']:.6f}",
                            'risk_pct': f"{signal.get('risk_pct', 0):.4f}",
                            'reason': signal.get('reason', '')[:200],
                        })
                        sys_logger.info(
                            f"[{self.bot_id}] 🟢 {action} @ ${self.position['entry_price']:.2f} | "
                            f"{signal.get('env','-')} | SL ${self.position['sl_price']:.2f} "
                            f"TP ${self.position['tp_price']:.2f} | lev {self.position['leverage']}x | "
                            f"tbm {signal.get('tbm_conf', 0):.2f}"
                        )
                    except Exception as log_e:
                        logging.error(f"[{self.bot_id}] 진입 로그 실패: {log_e}")
            except Exception as e:
                logging.error(f"[{self.bot_id}] Predict 에러: {e}")

        # 3. 청산 결정
        elif self.position.get("side") != "WAIT" and self.exec_instance:
            try:
                if hasattr(self.exec_instance, 'evaluate_exit'):
                    bot_state = {
                        "bot_id": self.bot_id,  # ★ V80k: 봇 ID 전달 (충돌 방지)
                        "position": self.position.get("side"),
                        "entry_price": self.position.get("entry_price"),
                        "sl_price": self.position.get("sl_price"),
                        "tp_price": self.position.get("tp_price"),
                        "one_r_dist": self.position.get("one_r_dist", 0.0),
                        "is_breakeven_on": self.position.get("is_breakeven_on"),
                        "is_half_taken": self.position.get("is_half_taken"),
                        "peak_price": self.position.get("highest_price") if self.position.get("side") == "LONG"
                                      else self.position.get("lowest_price")
                    }
                    # ★ V80k_Verify_1: bot_id 주입 (Observer 모듈 일관성)
                    e_params = dict(params)
                    e_params['bot_id'] = self.bot_id
                    exit_signal = self.exec_instance.evaluate_exit(current_price, bot_state, e_params)
                    self.last_exit = exit_signal  # ★ v2: 로깅용 추적
                    exit_action = exit_signal.get("action", "HOLD")
                    
                    # ★ V80k_Verify_2: E 모듈 청산 흐름을 Observer_Logger에 추가 기록
                    # (Observer 봇이 아니어도, 거래 봇의 청산 결정을 보조 트래킹)
                    try:
                        from Observer_Logger import log_observation
                        log_observation({
                            'bot_id': f'{self.bot_id}_E_TRACK',
                            'bar_ts': int(df['timestamp'].iloc[-1]) if 'timestamp' in df.columns and len(df) > 0 else 0,
                            'price': current_price,
                            'sim_action': exit_action,
                            'sim_entry_price': self.position.get('entry_price', 0.0),
                            'sim_sl_price': self.position.get('sl_price', 0.0),
                            'sim_tp_price': self.position.get('tp_price', 0.0),
                            'block_gate': f'E_DECISION_{exit_action}',
                        })
                    except Exception:
                        pass  # 로깅 실패해도 거래 영향 X
                    exit_action = exit_signal.get("action", "HOLD")
                    
                    if "update_sl" in exit_signal:
                        self.position["sl_price"] = exit_signal["update_sl"]
                        self.position["is_breakeven_on"] = True
                    
                    if exit_action == "CLOSE_ALL":
                        self._execute_close(current_price, exit_signal.get("reason", "일괄 청산"))
                    elif exit_action == "CLOSE_HALF":
                        self._execute_half_close(current_price, exit_signal.get("reason", "반익절"))
            except Exception as e:
                logging.error(f"[{self.bot_id}] Exec 에러: {e}")

    def _execute_close(self, current_price: float, reason: str) -> None:
        # 청산 정보 보존 (reset 전에)
        side_at_exit = self.position.get('side', 'WAIT')
        entry_at_exit = self.position.get('entry_price', 0.0)
        leverage_at_exit = self.position.get('leverage', 1)
        amount_at_exit = self.position.get('amount', 0.0)
        sl_at_exit = self.position.get('sl_price', 0.0)
        tp_at_exit = self.position.get('tp_price', 0.0)
        
        pnl = self.unrealized_pnl
        pnl_pct = (pnl / 10000.0) * 100  # 자본 대비 %
        self.realized_pnl += pnl
        self.capital += pnl
        self.unrealized_pnl = 0.0
        
        # 스윕
        if self.capital > 10000.0:
            excess = self.capital - 10000.0
            self.wallet_balance += excess
            self.capital = 10000.0
        
        logging.info(f"[{self.bot_id}] 🛑 청산 ({reason}): PnL ${pnl:+,.2f} | 선물 ${self.capital:,.2f} / 현물 ${self.wallet_balance:,.2f}")
        
        # 거래 로그 (메모리)
        import time as _t
        self.trade_history.append({
            'time': _t.time(),
            'action': 'CLOSE_ALL',
            'side_was': side_at_exit,    # 청산 직전 방향 보존
            'price': current_price,
            'pnl': pnl,
            'reason': reason,
        })
        
        # ★ V80k v2: 거래 CSV + 시스템 로그
        try:
            from RautoV80k_Logger import log_trade_event, setup_system_logger
            sys_logger, _ = setup_system_logger()
            
            # 청산 타입 분류 (마커용)
            exit_type = 'TP' if pnl > 0 else ('SL' if pnl < 0 else 'EVEN')
            
            log_trade_event(self.bot_id, 'CLOSE_ALL', {
                'side': side_at_exit,
                'entry_price': f"{entry_at_exit:.2f}",
                'exit_price': f"{current_price:.2f}",
                'sl_price': f"{sl_at_exit:.2f}",
                'tp_price': f"{tp_at_exit:.2f}",
                'leverage': leverage_at_exit,
                'amount': f"{amount_at_exit:.6f}",
                'pnl': f"{pnl:+.2f}",
                'pnl_pct': f"{pnl_pct:+.4f}",
                'capital_after': f"{self.capital:.2f}",
                'wallet_after': f"{self.wallet_balance:.2f}",
                'exit_type': exit_type,
                'reason': reason[:200],
            })
            sys_logger.info(
                f"[{self.bot_id}] 🛑 CLOSE_ALL {side_at_exit} @ ${current_price:.2f} | "
                f"PnL ${pnl:+.2f} ({pnl_pct:+.2f}%) | exit_type={exit_type} | {reason[:60]}"
            )
        except Exception as log_e:
            logging.error(f"[{self.bot_id}] 청산 로그 실패: {log_e}")
        
        self.position = {
            "side": "WAIT", "entry_price": 0.0, "amount": 0.0, "sl_price": 0.0, "tp_price": 0.0,
            "one_r_dist": 0.0, "is_breakeven_on": False, "is_half_taken": False,
            "highest_price": 0.0, "lowest_price": float('inf'), "leverage": 1
        }

    def _execute_half_close(self, current_price: float, reason: str) -> None:
        side_at_half = self.position.get('side', 'WAIT')
        entry_at_half = self.position.get('entry_price', 0.0)
        leverage_at_half = self.position.get('leverage', 1)
        sl_at_half = self.position.get('sl_price', 0.0)
        tp_at_half = self.position.get('tp_price', 0.0)
        
        half_amount = self.position["amount"] * 0.5
        pnl = self.unrealized_pnl * 0.5
        pnl_pct = (pnl / 10000.0) * 100
        self.realized_pnl += pnl
        self.capital += pnl
        self.position["amount"] -= half_amount
        self.position["is_half_taken"] = True
        
        if self.capital > 10000.0:
            excess = self.capital - 10000.0
            self.wallet_balance += excess
            self.capital = 10000.0
        
        logging.info(f"[{self.bot_id}] 🎯 반익절 ({reason}): PnL ${pnl:+,.2f}")
        
        import time as _t
        self.trade_history.append({
            'time': _t.time(),
            'action': 'CLOSE_HALF',
            'side_was': side_at_half,
            'price': current_price,
            'pnl': pnl,
            'reason': reason,
        })
        
        # ★ V80k v2: CSV + 로그
        try:
            from RautoV80k_Logger import log_trade_event, setup_system_logger
            sys_logger, _ = setup_system_logger()
            log_trade_event(self.bot_id, 'CLOSE_HALF', {
                'side': side_at_half,
                'entry_price': f"{entry_at_half:.2f}",
                'exit_price': f"{current_price:.2f}",
                'sl_price': f"{sl_at_half:.2f}",
                'tp_price': f"{tp_at_half:.2f}",
                'leverage': leverage_at_half,
                'amount': f"{half_amount:.6f}",
                'pnl': f"{pnl:+.2f}",
                'pnl_pct': f"{pnl_pct:+.4f}",
                'capital_after': f"{self.capital:.2f}",
                'wallet_after': f"{self.wallet_balance:.2f}",
                'exit_type': 'TP_HALF',
                'reason': reason[:200],
            })
            sys_logger.info(
                f"[{self.bot_id}] 🎯 CLOSE_HALF {side_at_half} @ ${current_price:.2f} | "
                f"PnL ${pnl:+.2f} ({pnl_pct:+.2f}%) | {reason[:60]}"
            )
        except Exception as log_e:
            logging.error(f"[{self.bot_id}] 반익절 로그 실패: {log_e}")
