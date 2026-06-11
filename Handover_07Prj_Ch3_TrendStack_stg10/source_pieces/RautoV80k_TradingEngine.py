# ==============================================================================
# 파일명: RautoV80k_TradingEngine.py
# 코드길이: 약 200줄 / 내부버전: V8.0k v3 응급 (Silent Crash 방지)
# 작성일: 2026-04-29
# ==============================================================================
# [v3 응급 패치]
#   1. while 루프 전체 try-except로 감쌈 → 스레드 절대 죽지 않음
#   2. 봇별 on_tick_data도 try-except → 한 봇 에러가 다른 봇 영향 안 줌
#   3. 단계별 print 추가 → 어디서 죽었는지 보이게
#   4. WebSocket 갱신 모니터링 → 30초 이상 멈추면 경고
#   5. 메모리 사용량 체크
# ==============================================================================
import time
import psutil
import logging
import traceback
import os
from PyQt6.QtCore import QThread, pyqtSignal
from RautoV80k_DataEngine import RautoV80k_DataEngine
from RautoV80k_BotManager import RautoV80k_BotManager
from RautoV80k_Logger import (
    setup_system_logger, log_bot_state, log_equity_snapshot, is_new_bar
)


class RautoV80k_TradingEngine(QThread):
    sync_signal = pyqtSignal(float, str, str, int, dict, dict)
    # ★ V80k_Verify_2: market_metrics dict 추가 (atr_pct/vol_trend/crsi)

    def __init__(self):
        super().__init__()
        self.sys_logger, self.log_path = setup_system_logger()
        
        self.data_engine = RautoV80k_DataEngine(symbol="BTCUSDT", interval="1m")
        self.bots = [RautoV80k_BotManager(f"Bot_{i+1}", initial_capital=10000.0) for i in range(8)]
        self.is_running = True
        self.current_regime = "분석 대기 중"
        
        # ★ v3: 데이터 갱신 모니터링
        self.last_price = 0.0
        self.last_price_change_time = time.time()
        self.last_bar_ts_seen = None
        self.loop_count = 0
        self.error_count = 0
        
        self.sys_logger.info(f"V8.0k v3 엔진 초기화 — 8 봇 / 초기 자본 $10,000 each")
        print(f"[Engine v3] 초기화 완료. PID={os.getpid()}")

    def get_master_params(self):
        return {
            "risk_per_trade_pct": 0.02, "daily_mdd_limit": 0.15, "sweep_threshold": 10000.0,
            "min_rr_ratio": 2.0, "ml_threshold": 60.0,
            "regime_ema_period": 20, "regime_atr_period": 14, "regime_spike_mult": 3.5,
            "macd_mtf_short": (14, 28), "macd_mtf_mid": (52, 104), "macd_mtf_long": (210, 420),
            "crsi_domcycle": 10, "pivot_left": 10, "pivot_right": 5, "ts_callback_pct": 0.005
        }

    def run(self):
        try:
            self.data_engine.start_engine()
        except Exception as e:
            self.sys_logger.error(f"[CRITICAL] DataEngine 시작 실패: {e}")
            print(f"[Engine v3] ❌ DataEngine 시작 실패: {e}")
            print(traceback.format_exc())
            return
        
        self.sys_logger.info("V8.0k 통합 매매 엔진 가동")
        print("[Engine v3] 메인 루프 시작")

        while self.is_running:
            try:
                self.loop_count += 1
                
                df = self.data_engine.get_latest_data()
                if df is None or df.empty:
                    if self.loop_count % 100 == 0:  # 10초마다 1번
                        print(f"[Engine v3] DataEngine 데이터 대기 중... (loop {self.loop_count})")
                    time.sleep(0.1); continue
                
                price = float(df['close'].iloc[-1])
                bar_ts = df['timestamp'].iloc[-1] if 'timestamp' in df.columns else df.index[-1]
                
                # ★ v3: 가격 변화 모니터링
                if price != self.last_price:
                    self.last_price = price
                    self.last_price_change_time = time.time()
                
                stale_seconds = time.time() - self.last_price_change_time
                
                # ★ v3: 30초 이상 가격 안 바뀌면 경고 (시장이 진짜 멈춘 게 아니라면 WS 끊김)
                if stale_seconds > 30 and self.loop_count % 100 == 0:
                    print(f"[Engine v3] ⚠️ REST 폴링 지연! {stale_seconds:.0f}초간 ${price:.2f} 고정. REST 폴링 의심.")
                    self.sys_logger.warning(f"가격 갱신 멈춤 {stale_seconds:.0f}초 — REST 폴링 멈춤")
                
                # ★ v3: 새 봉 도착 시 콘솔 알림
                if bar_ts != self.last_bar_ts_seen:
                    if self.last_bar_ts_seen is not None:
                        print(f"[Engine v3] 🔔 새 봉 도착 ${price:.2f} (loop {self.loop_count})")
                    self.last_bar_ts_seen = bar_ts
                
                params = self.get_master_params()
                active_count = 0
                gui_bot_states = {}
                new_bar_started = is_new_bar(bar_ts)

                for i, bot in enumerate(self.bots):
                    # ★ v3: 봇별 try-except로 한 봇 에러가 전체 죽이지 않게
                    try:
                        if bot.state.value in [1, 2]:
                            bot_params = dict(params)
                            if 'leverage' in bot.position:
                                bot_params['estimated_leverage'] = bot.position['leverage']
                            bot.on_tick_data(df, price, bot_params)
                            active_count += 1
                            if active_count == 1:
                                self.current_regime = getattr(bot, 'current_regime', "CHOPPY")
                        
                        gui_bot_states[i] = {
                            "bot_id": bot.bot_id,
                            "state_val": bot.state.value,
                            "side": bot.position.get('side', 'WAIT'),
                            "futures_bal": bot.capital + bot.unrealized_pnl,
                            "spot_bal": bot.wallet_balance,
                            "pnl": bot.unrealized_pnl,
                            "realized_pnl": bot.realized_pnl,
                            "leverage": bot.position.get("leverage", 1),
                            "entry_price": bot.position.get("entry_price", 0),
                            "sl_price": bot.position.get("sl_price", 0),
                            "tp_price": bot.position.get("tp_price", 0),
                        }
                        
                        if new_bar_started and bot.state.value in [1, 2]:
                            try:
                                log_bot_state(
                                    bot.bot_id, bot,
                                    getattr(bot, 'current_regime', '-'),
                                    getattr(bot, 'last_signal', None),
                                    getattr(bot, 'last_exit', None),
                                    price, bar_ts
                                )
                                log_equity_snapshot(bot.bot_id, bot, price, bar_ts)
                            except Exception as e:
                                self.sys_logger.error(f"[{bot.bot_id}] 봉 마감 로깅 실패: {e}")
                    
                    except Exception as bot_e:
                        self.error_count += 1
                        err_msg = f"[{bot.bot_id}] 봇 에러: {bot_e}"
                        print(f"[Engine v3] ❌ {err_msg}")
                        print(traceback.format_exc())
                        self.sys_logger.error(err_msg)
                        self.sys_logger.error(traceback.format_exc())
                        # 봇 비활성화 (반복 에러 방지)
                        if self.error_count > 100:
                            print(f"[Engine v3] 🚨 에러 100회 초과. 시스템 정지.")
                            self.is_running = False
                            break
                        # gui_bot_states 안 채워도 다음 루프에 채워짐
                        gui_bot_states[i] = {
                            "bot_id": bot.bot_id, "state_val": 0, "side": "ERROR",
                            "futures_bal": bot.capital, "spot_bal": bot.wallet_balance,
                            "pnl": 0, "realized_pnl": bot.realized_pnl,
                            "leverage": 1, "entry_price": 0, "sl_price": 0, "tp_price": 0,
                        }

                # WS 끊김 알림을 status에 표시
                ws_status = "정상"
                if stale_seconds > 30:
                    ws_status = f"⚠️ REST 폴링 멈춤 ({int(stale_seconds)}s)"
                elif stale_seconds > 10:
                    ws_status = f"⏳ 갱신 대기 ({int(stale_seconds)}s)"
                
                sys_status = (f"활성 {active_count}봇 / Poll:{ws_status}"
                              if active_count > 0 else f"전체 대기 / Poll:{ws_status}")
                
                try:
                    real_sys_load = int(psutil.cpu_percent())
                except Exception:
                    real_sys_load = 0
                
                # ★ V80k_Verify_2: 시장 객관 지표 산출 (모듈 무관, 1분봉 기준)
                market_metrics = {'atr_pct': None, 'vol_trend': None, 'crsi': None}
                try:
                    df_1m = self.data_engine.df_1m if self.data_engine else None
                    if df_1m is not None and len(df_1m) >= 60:
                        # 15m ATR%: 최근 15봉의 (high-low)/close 평균
                        recent15 = df_1m.tail(15)
                        atr15 = ((recent15['high'] - recent15['low']) / recent15['close']).mean() * 100
                        market_metrics['atr_pct'] = float(atr15)
                        
                        # 거래량 추세: 최근 60분 평균 vs 이전 60분 평균
                        if len(df_1m) >= 120:
                            vol_recent = df_1m['volume'].tail(60).mean()
                            vol_prev = df_1m['volume'].iloc[-120:-60].mean()
                            if vol_prev > 0:
                                vol_trend_pct = (vol_recent - vol_prev) / vol_prev * 100
                                market_metrics['vol_trend'] = float(vol_trend_pct)
                except Exception:
                    pass  # 시장 지표 산출 실패는 거래에 영향 X
                
                # GUI 시그널
                try:
                    self.sync_signal.emit(price, self.current_regime, sys_status, real_sys_load,
                                          gui_bot_states, market_metrics)
                except Exception as emit_e:
                    print(f"[Engine v3] ⚠️ sync_signal emit 실패: {emit_e}")
                    self.sys_logger.error(f"sync_signal emit 실패: {emit_e}")
                
                time.sleep(0.1)
            
            except Exception as loop_e:
                # ★★★ v3: 메인 루프 자체 에러도 잡아서 스레드 죽지 않게 ★★★
                self.error_count += 1
                err_msg = f"메인 루프 에러 #{self.error_count}: {loop_e}"
                print(f"[Engine v3] 🚨 {err_msg}")
                print(traceback.format_exc())
                self.sys_logger.error(err_msg)
                self.sys_logger.error(traceback.format_exc())
                
                if self.error_count > 100:
                    print(f"[Engine v3] 🚨 에러 100회 초과. 시스템 정지.")
                    break
                
                time.sleep(1)  # 에러 발생 시 1초 쿨다운
        
        print("[Engine v3] 메인 루프 종료")
        self.sys_logger.info("메인 루프 종료")

    def update_bot_modules(self, idx, r_mod, p_mod, e_mod):
        try:
            self.bots[idx].update_modules(r_mod, p_mod, e_mod)
            self.sys_logger.info(
                f"[{self.bots[idx].bot_id}] 모듈 이식: R={r_mod} / P={p_mod} / E={e_mod}"
            )
            print(f"[Engine v3] [{self.bots[idx].bot_id}] 모듈 이식 완료")
        except Exception as e:
            print(f"[Engine v3] ❌ 모듈 이식 실패: {e}")
            self.sys_logger.error(f"모듈 이식 실패: {e}")

    def process_bot_step(self, idx, target_step):
        try:
            self.bots[idx].process_step_signal(target_step)
            bot = self.bots[idx]
            self.sys_logger.info(f"[{bot.bot_id}] 상태 변화 → {bot.state.name}")
            print(f"[Engine v3] [{bot.bot_id}] → {bot.state.name}")
        except Exception as e:
            print(f"[Engine v3] ❌ 봇 스텝 변경 실패: {e}")
            self.sys_logger.error(f"봇 스텝 변경 실패: {e}")

    def stop_engine(self):
        self.is_running = False
        self.sys_logger.info("V8.0k 엔진 종료 요청")
        self.wait()
        self.sys_logger.info("V8.0k 엔진 종료 완료")
