# ==============================================================================
# 파일명: Backtest_Engine_PautoV75.py
# 역할: Pauto V7.5 코어 엔진 (SMC 50% 분할 + 피보나치 락인 + 모듈 자동 로딩 패치)
# ==============================================================================
import os
import sys
import importlib
import inspect
import json
import pandas as pd
from datetime import datetime
from Historical_DataEngine_PautoV75 import Historical_DataEngine_PautoV75

class Backtest_Engine_PautoV75:
    def __init__(self, regime_mod, predict_mod, exec_mod, start_date, end_date):
        # [수정 완료]: 하드코딩된 경로 제거 및 현재 실행 파일 위치 동적 감지
        self.work_dir = os.path.dirname(os.path.abspath(__file__))
        if self.work_dir not in sys.path: sys.path.insert(0, self.work_dir)
            
        self.combo_name = f"{regime_mod}+{predict_mod}+{exec_mod}"
        self.period_str = f"{start_date} ~ {end_date}"
        
        self.initial_capital = 10000.0
        self.capital = self.initial_capital  
        self.spot_wallet = 0.0               
        
        self.stats = {'LONG': {'trades': 0, 'wins': 0, 'fees': 0.0, 'net_profit': 0.0, 'return_pct_sum': 0.0},
                      'SHORT': {'trades': 0, 'wins': 0, 'fees': 0.0, 'net_profit': 0.0, 'return_pct_sum': 0.0}}
        
        self.fee_rate = 0.0004  
        self.funding_rate_daily = 0.0001
        
        self.position = "WAIT" 
        self.entry_price = 0.0
        self.entry_time = None
        self.position_size = 0.0
        self.last_price = 0.0
        self.trade_logs = []
        self.bot_state = {} 
        
        self.params = {
            'leverage': 1, 'ml_long_threshold': 0.80, 'ml_short_threshold': 0.20,
            'fib_trigger_roe': 15.0, 'fib_sl_roe': 5.73, 'fib_ext_pct': 0.618
        }
        
        # 🌟 최적화 파라미터 자동 로드
        param_file = os.path.join(self.work_dir, "Pauto_Best_Params.json")
        if os.path.exists(param_file):
            try:
                with open(param_file, "r", encoding="utf-8") as f:
                    best_params = json.load(f)
                self.params.update(best_params)
                print(f"✅ [Pauto 엔진] 최적화 파라미터 자동 로드 완료! (레버리지 {self.params['leverage']}x)")
            except Exception as e:
                print(f"⚠️ [Pauto 엔진] 파라미터 파일 로드 실패 (기본값 사용): {e}")

        # 🌟 [패치 핵심부] 파일명과 상관없이 클래스를 무조건 찾아내는 강력한 로더
        def load_class_from_module(module_name):
            try:
                mod = importlib.import_module(module_name)
                # 모듈 내에서 선언된 클래스 중, 파이썬 기본 클래스가 아닌 것을 자동 탐색
                for name, obj in inspect.getmembers(mod, inspect.isclass):
                    if obj.__module__ == module_name:
                        return obj() # 인스턴스 생성 후 반환
                raise ValueError(f"'{module_name}.py' 안에 유효한 클래스가 없습니다.")
            except Exception as e:
                raise ImportError(f"모듈 로딩 에러 ({module_name}): {str(e)}")

        self.regime_instance = load_class_from_module(regime_mod)
        self.predict_instance = load_class_from_module(predict_mod)
        self.exec_instance = load_class_from_module(exec_mod)
        
        self.timestamp_str = datetime.now().strftime("%y%m%d_%H%M%S")
        self.data_engine = Historical_DataEngine_PautoV75(os.path.join(self.work_dir, "Merged_Data.csv"))

    def run_simulation(self, progress_callback=None):
        is_running = True
        last_pct = -1
        while is_running:
            pct, current_price, df_1m, is_closed, is_running = self.data_engine.next_step()
            
            if progress_callback and int(pct) != last_pct:
                progress_callback(int(pct))
                last_pct = int(pct)
                
            if not is_running: break
            # [v7.6 변경 ④] 강제청산(margin call) 발생 시 시뮬 종료
            if self.position == "TERMINATED":
                print(f"⚠️ [Pauto v7.6] 강제청산 상태 - 시뮬 종료")
                break
            self.last_price = current_price 
            current_time = df_1m.index[-1]
            
            if self.position == "WAIT":
                # 장세 판독
                current_regime = self.regime_instance.get_regime(df_1m, self.params) if hasattr(self.regime_instance, 'get_regime') else "CHOPPY"
                
                if is_closed:
                    # 타점 판독
                    signal = self.predict_instance.get_signal(df_1m, current_regime, self.params)
                    if signal and signal.get('action') in ["OPEN_LONG", "OPEN_SHORT"]:
                        self.position = "LONG" if signal['action'] == "OPEN_LONG" else "SHORT"
                        self.entry_price = current_price 
                        self.entry_time = current_time
                        self.position_size = self.capital * self.params['leverage']
                        
                        # 🌟 [패치 핵심부] 진입 시 bot_state 필수 메모리 완벽 초기화
                        self.bot_state = {
                            'position': self.position, 
                            'entry_price': current_price,
                            'remaining_pct': 1.0, 
                            'target_idx': 0, 
                            'ob_initialized': False,
                            'fib_wave_start': current_price, 
                            'fib_extreme': current_price,
                            'pulled_back': False, 
                            'fib_stop': None,
                            'bullish_obs': [],
                            'bearish_obs': [],
                            'entry_regime': current_regime, 
                            'entry_reason': signal.get('reason', '')
                        }

            elif self.position in ["LONG", "SHORT"]:
                # 청산 판독
                self.bot_state['df_1m'] = df_1m 
                exit_signal = self.exec_instance.check_exit(current_price, self.bot_state, self.params)
                
                if exit_signal and exit_signal.get('action') in ["REDUCE_LONG", "REDUCE_SHORT"]:
                    self._reduce_position(current_price, current_time, exit_signal['reason'])
                    
                elif exit_signal and exit_signal.get('action') in ["CLOSE_LONG", "CLOSE_SHORT"]:
                    self._close_position(current_price, current_time, exit_signal['reason'])
                    
        self._generate_reports()

    def _reduce_position(self, current_price, current_time, exit_reason):
        reduce_amt = self.position_size * 0.5
        pnl_pct = (current_price - self.entry_price) / self.entry_price if self.position == "LONG" else (self.entry_price - current_price) / self.entry_price
        gross_pnl = reduce_amt * pnl_pct
        fee_cost = reduce_amt * self.fee_rate * 2
        net_pnl = gross_pnl - fee_cost
        
        trade_record = {
            "진입시간": self.entry_time.strftime('%Y-%m-%d %H:%M:%S'),
            "청산시간": current_time.strftime('%Y-%m-%d %H:%M:%S'),
            "포지션": self.position + " (50% 익절)", "레버리지": self.params['leverage'],
            "진입수량($)": round(reduce_amt, 2), "장세판단(Regime)": self.bot_state.get('entry_regime', 'N/A'),
            "진입사유(Predict)": self.bot_state.get('entry_reason', 'N/A'), "청산사유(Exec)": exit_reason,
            "진입가": self.entry_price, "청산가": current_price, "수수료($)": round(fee_cost, 2), "순수익금($)": round(net_pnl, 2)
        }
        self.trade_logs.append(trade_record)
        self.capital += net_pnl
        self.position_size -= reduce_amt
        self.bot_state['remaining_pct'] = 0.5

    def _close_position(self, current_price, current_time, exit_reason):
        pnl_pct = (current_price - self.entry_price) / self.entry_price if self.position == "LONG" else (self.entry_price - current_price) / self.entry_price
        gross_pnl = self.position_size * pnl_pct
        fee_cost = self.position_size * self.fee_rate * 2 
        
        duration_days = (current_time - self.entry_time).total_seconds() / 86400 if self.entry_time else 0
        funding_cost = self.position_size * self.funding_rate_daily * duration_days
        
        net_pnl = gross_pnl - fee_cost - funding_cost
        net_return_pct = (net_pnl / self.position_size) * 100
        
        trade_record = {
            "진입시간": self.entry_time.strftime('%Y-%m-%d %H:%M:%S'),
            "청산시간": current_time.strftime('%Y-%m-%d %H:%M:%S'),
            "포지션": self.position + (" (나머지 50%)" if self.bot_state.get('remaining_pct') == 0.5 else " (전량)"),
            "레버리지": self.params['leverage'], "진입수량($)": round(self.position_size, 2),
            "장세판단(Regime)": self.bot_state.get('entry_regime', 'N/A'), "진입사유(Predict)": self.bot_state.get('entry_reason', 'N/A'),
            "청산사유(Exec)": exit_reason, "진입가": self.entry_price, "청산가": current_price,
            "수수료($)": round(fee_cost, 2), "순수익금($)": round(net_pnl, 2)
        }
        self.trade_logs.append(trade_record)
        
        target_stat = self.stats[self.position]
        target_stat['trades'] += 1
        target_stat['fees'] += fee_cost
        target_stat['net_profit'] += net_pnl
        target_stat['return_pct_sum'] += net_return_pct
        if net_pnl > 0: target_stat['wins'] += 1
            
        self.capital += net_pnl
        # [v7.6 변경 ①] spot_wallet 인출 로직 제거 — 순수 복리 누적
        # 기존: if self.capital > self.initial_capital: self.spot_wallet += ...; self.capital = self.initial_capital
        # (spot_wallet은 호환성 위해 0 유지)
        
        # [v7.6 변경 ③] 강제청산(margin call) 감지 안전장치
        # 자본이 0 이하 도달 = 실거래 청산. 다음 진입 영구 차단
        if self.capital <= 0:
            print(f"⚠️ [Pauto v7.6 강제청산] {current_time}에 자본 {self.capital:.2f}달러로 시뮬 종료 (강제청산)")
            self.capital = 0
            self.position = "TERMINATED"
        else:
            self.position = "WAIT"

    def _generate_reports(self):
        unrealized_pnl = 0.0
        if self.position == "LONG":
            unrealized_pnl = self.position_size * ((self.last_price - self.entry_price) / self.entry_price) - (self.position_size * self.fee_rate)
        elif self.position == "SHORT":
            unrealized_pnl = self.position_size * ((self.entry_price - self.last_price) / self.entry_price) - (self.position_size * self.fee_rate)

        def calc_metrics(side):
            st = self.stats[side]
            tr = max(1, st['trades'])
            return {
                '매매횟수': st['trades'], '수수료($)': round(st['fees'], 2),
                '승률(%)': round((st['wins'] / tr) * 100, 2) if st['trades'] > 0 else 0.0,
                '수익금($)': round(st['net_profit'], 2),
                '평균수익금($)': round(st['net_profit'] / tr, 2) if st['trades'] > 0 else 0.0,
                '평균수익률(%)': round(st['return_pct_sum'] / tr, 2) if st['trades'] > 0 else 0.0
            }

        l_met = calc_metrics('LONG')
        s_met = calc_metrics('SHORT')
        tot_trades = l_met['매매횟수'] + s_met['매매횟수']
        t_met = {
            '매매횟수': tot_trades, '수수료($)': l_met['수수료($)'] + s_met['수수료($)'],
            '승률(%)': round(((self.stats['LONG']['wins'] + self.stats['SHORT']['wins']) / max(1, tot_trades)) * 100, 2) if tot_trades > 0 else 0.0,
            '수익금($)': round(l_met['수익금($)'] + s_met['수익금($)'], 2)
        }

        html_path = os.path.join(self.work_dir, f"Pauto_Report_{self.timestamp_str}.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(f"<html><head><title>Pauto V7.5 (SMC Fibonacci)</title><style>body {{ font-family: Arial; background: #1e1e2e; color: #cdd6f4; margin: 40px; }} table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }} th, td {{ padding: 12px; text-align: center; border: 1px solid #313244; }} th {{ background-color: #313244; }} .highlight {{ color: #a6e3a1; font-weight: bold; }}</style></head><body><h2>📊 Pauto V7.5 리포트 (Optuna Auto-Loaded)</h2><p>선물계좌: ${round(self.capital, 2)} | 현물스윕(격리): <span class='highlight'>${round(self.spot_wallet, 2)}</span> | 미실현: ${round(unrealized_pnl, 2)}</p><p>✅ 적용된 파라미터: 레버리지 {self.params.get('leverage',1)}x | AI 임계값 {self.params.get('ml_long_threshold',0.8)*100}% | 피보나치 락인 {self.params.get('fib_ext_pct', 0.618)}</p><table><tr><th>구분</th><th>매매횟수</th><th>수수료($)</th><th>승률(%)</th><th>수익금($)</th></tr><tr><td style='color:#89dceb;'>LONG</td><td>{l_met['매매횟수']}</td><td>{l_met['수수료($)']}</td><td>{l_met['승률(%)']}%</td><td>{l_met['수익금($)']}</td></tr><tr><td style='color:#f38ba8;'>SHORT</td><td>{s_met['매매횟수']}</td><td>{s_met['수수료($)']}</td><td>{s_met['승률(%)']}%</td><td>{s_met['수익금($)']}</td></tr><tr><td>합계</td><td>{t_met['매매횟수']}</td><td>{t_met['수수료($)']}</td><td>{t_met['승률(%)']}%</td><td class='highlight'>{t_met['수익금($)']}</td></tr></table></body></html>")

        if self.trade_logs:
            log_path = os.path.join(self.work_dir, f"Pauto_TradeLog_{self.timestamp_str}.csv")
            pd.DataFrame(self.trade_logs).to_csv(log_path, index=False, encoding='utf-8-sig')
            try: os.startfile(log_path) 
            except: pass
        try: os.startfile(html_path)
        except: pass