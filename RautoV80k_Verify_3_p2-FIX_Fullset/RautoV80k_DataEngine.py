# ==============================================================================
# 파일명: RautoV80k_DataEngine.py
# 코드길이: 약 180줄 / 내부버전: V8.0k v5 (REST 폴링 — WebSocket 대안)
# 작성일: 2026-04-29
# ==============================================================================
# [v5 핵심 변경 — WebSocket 차단 우회]
#   배경:
#     v4의 SUBSCRIBE 패치 후에도 AWS Seoul/Singapore 등 일부 IP에서
#     fstream.binance.com이 result:null만 응답하고 데이터 송신 차단.
#     반면 REST API (fapi.binance.com)는 정상 작동 확인.
#   
#   해결:
#     WebSocket 대신 REST API로 5초마다 마지막 1봉 폴링.
#     봉 마감 시점에 마감된 봉이 자동으로 들어옴.
#   
#   영향 분석:
#     - 학습 데이터(선물 1m): 100% 정합
#     - 실시간성: 5초 지연 (1m 봉 기반이라 영향 거의 없음)
#     - Rate Limit: 1200/min 한도 중 12/min (5초 폴링)만 사용 — 안전
#
# [v4 패치 유지 — 적용 안 되지만 코드 보존]
#   - URL/SUBSCRIBE 메서드는 코드에 남기지만 실제론 호출 안 함
#
# [V75 인터페이스 100% 유지]
#   - get_latest_data(): TradingEngine 0.1초 폴링용
#   - add_log(): CSV 로그 (엑셀 충돌 방지 큐)
# ==============================================================================
import os
import sys
import json
import time
import threading
import requests
from collections import deque
import pandas as pd

BASE_DIR = os.environ.get('PAUTO_BASE_DIR') or os.path.dirname(os.path.abspath(__file__))


class RautoV80k_DataEngine:
    """V75 인터페이스 호환 + V8.0k v5 REST 폴링.
    
    Public API:
        - start_engine() : 엔진 시작 (REST 워밍업 + 폴링 스레드 시작)
        - get_latest_data() : 최신 DataFrame 반환
        - add_log(...) : 거래 로그 큐 추가
    """
    
    def __init__(self, symbol="BTCUSDT", interval="1m"):
        self.symbol = symbol
        self.interval = interval
        self.max_length = 4500  # V8.0k 30 피처 정합 (EMA420 + rolling1000)
        
        self.df_1m = pd.DataFrame()
        self.lock = threading.Lock()
        
        self.rest_base_url = "https://fapi.binance.com/fapi/v1/klines"
        # ★ v5: 폴링 간격 (초) — 1m 봉이라 5초로 충분
        self.poll_interval_seconds = 5
        
        self.is_ready = False
        self.is_running = False
        self.poll_count = 0
        self.last_successful_poll = 0
        self.consecutive_errors = 0
        
        self.log_queue = deque()
        self.log_file = os.path.join(BASE_DIR, "RautoV80k_Trade_Log.csv")
        self.log_columns = ['timestamp', 'bot_id', 'action', 'price', 'amount', 'pnl', 'reason']

    # ==========================================================================
    # 시작/워밍업
    # ==========================================================================
    def start_engine(self):
        """엔진 시작 — REST 워밍업 4500봉 → 5초 폴링 스레드 시작."""
        print(f"[RautoV80k_DataEngine] 🚀 V8.0k v5 — REST 폴링 모드")
        self._warmup_rest()
        self.is_running = True
        threading.Thread(target=self._poll_loop, daemon=True).start()
        print(f"[RautoV80k_DataEngine] ✅ 폴링 스레드 시작 (간격 {self.poll_interval_seconds}초)")

    def _warmup_rest(self):
        """REST API로 4500봉 워밍업 (페이지네이션, V75 동일)."""
        try:
            print(f"[RautoV80k_DataEngine] 🔄 과거 데이터 예열 중... ({self.symbol}, {self.max_length}봉)")
            
            all_klines = []
            end_time = None
            pages = 3  # 1500 × 3 = 4500봉
            
            for page in range(pages):
                params = {
                    'symbol': self.symbol,
                    'interval': self.interval,
                    'limit': 1500
                }
                if end_time is not None:
                    params['endTime'] = end_time
                
                resp = requests.get(self.rest_base_url, params=params, timeout=15)
                resp.raise_for_status()
                klines = resp.json()
                
                if not klines:
                    break
                
                all_klines = klines + all_klines
                end_time = klines[0][0] - 1  # 가장 오래된 봉의 open_time - 1
                
                print(f"[RautoV80k_DataEngine]   페이지 {page+1}/{pages}: {len(klines)}봉 (총 {len(all_klines)}봉)")
            
            # DataFrame 변환
            rows = []
            for k in all_klines:
                rows.append({
                    'timestamp': float(k[0]),
                    'open': float(k[1]),
                    'high': float(k[2]),
                    'low': float(k[3]),
                    'close': float(k[4]),
                    'volume': float(k[5]),
                    'taker_buy_volume': float(k[9])  # V8.0k 30 피처
                })
            
            df = pd.DataFrame(rows)
            df = df.drop_duplicates(subset='timestamp', keep='last').sort_values('timestamp').reset_index(drop=True)
            
            with self.lock:
                self.df_1m = df.iloc[-self.max_length:].reset_index(drop=True)
            
            self.is_ready = True
            self.last_successful_poll = time.time()
            print(f"[RautoV80k_DataEngine] ✅ 예열 완료 (총 {len(df)}봉). REST 폴링 시작.")
        except Exception as e:
            print(f"[RautoV80k_DataEngine] ❌ 예열 실패: {e}")
            import traceback
            traceback.print_exc()

    # ==========================================================================
    # ★ v5: REST 폴링 루프 (WebSocket 대체)
    # ==========================================================================
    def _poll_loop(self):
        """5초마다 마지막 1봉 가져오기. 봉 마감 시 자동으로 마감된 봉 들어옴."""
        while self.is_running:
            try:
                self._poll_latest_bar()
                self.consecutive_errors = 0
                self.last_successful_poll = time.time()
            except Exception as e:
                self.consecutive_errors += 1
                if self.consecutive_errors <= 3 or self.consecutive_errors % 20 == 0:
                    print(f"[RautoV80k_DataEngine] ⚠️ 폴링 오류 #{self.consecutive_errors}: {str(e)[:80]}")
            
            time.sleep(self.poll_interval_seconds)
    
    def _poll_latest_bar(self):
        """REST로 마지막 1봉 가져와 df_1m 갱신."""
        params = {
            'symbol': self.symbol,
            'interval': self.interval,
            'limit': 2  # 마지막 2봉 (안전 마진)
        }
        resp = requests.get(self.rest_base_url, params=params, timeout=10)
        resp.raise_for_status()
        klines = resp.json()
        
        if not klines:
            return
        
        self.poll_count += 1
        new_rows = []
        for k in klines:
            new_rows.append({
                'timestamp': float(k[0]),
                'open': float(k[1]),
                'high': float(k[2]),
                'low': float(k[3]),
                'close': float(k[4]),
                'volume': float(k[5]),
                'taker_buy_volume': float(k[9])
            })
        
        with self.lock:
            for new_row in new_rows:
                if not self.df_1m.empty and self.df_1m.iloc[-1]['timestamp'] == new_row['timestamp']:
                    # 진행 중인 봉 갱신
                    self.df_1m.iloc[-1] = new_row
                elif not self.df_1m.empty and new_row['timestamp'] < self.df_1m.iloc[-1]['timestamp']:
                    # 옛 봉 — 무시
                    continue
                else:
                    # 새 봉 추가
                    self.df_1m = pd.concat([self.df_1m, pd.DataFrame([new_row])], ignore_index=True)
                    if len(self.df_1m) > self.max_length:
                        self.df_1m = self.df_1m.iloc[-self.max_length:].reset_index(drop=True)
                    
                    if self.poll_count > 1:  # 첫 번째는 워밍업과 중복이라 출력 안 함
                        print(f"[RautoV80k_DataEngine] 🔔 새 봉: ${new_row['close']:.2f} (poll #{self.poll_count})")

    # ==========================================================================
    # 데이터 / 로그 인터페이스 (V75 호환)
    # ==========================================================================
    def get_latest_data(self):
        """TradingEngine이 0.1초마다 호출."""
        with self.lock:
            return self.df_1m.copy() if not self.df_1m.empty else pd.DataFrame()

    def add_log(self, log_dict):
        """거래 로그 추가 — CSV 큐."""
        self.log_queue.append(log_dict)
        self._flush_log()

    def _flush_log(self):
        if not self.log_queue:
            return
        try:
            file_exists = os.path.exists(self.log_file)
            with open(self.log_file, 'a', encoding='utf-8', newline='') as f:
                import csv as _csv
                writer = _csv.DictWriter(f, fieldnames=self.log_columns)
                if not file_exists:
                    writer.writeheader()
                while self.log_queue:
                    row = self.log_queue.popleft()
                    writer.writerow({k: row.get(k, '') for k in self.log_columns})
        except PermissionError:
            pass  # 엑셀 잠금
        except Exception as e:
            print(f"[RautoV80k_DataEngine] 로그 쓰기 오류: {e}")

    def stop(self):
        self.is_running = False
        print(f"[RautoV80k_DataEngine] 정지. 총 폴링 {self.poll_count}회.")
