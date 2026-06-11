# ==============================================================================
# 파일명: Historical_DataEngine_PautoV75.py
# 역할: 과거 데이터 틱(Tick) 시뮬레이터 (Zero-Lookahead Bias 구현)
# 
# [변수 파이프라인 (Data I/O Pipeline)]
# 📥 [IN] 
#   - data_path: 코어 엔진에서 전달받은 Merged_Data.csv 파일의 절대 경로
# 
# 🛠️ [STATE] 
#   - 1분봉(OHLC)을 4개의 가상 틱으로 분할 (시가 -> 고/저가 -> 저/고가 -> 종가).
#   - 현재 진행 중인 캔들의 종가를 실시간 틱 가격으로 덮어씌워 미래 데이터 참조를 원천 차단.
# 
# 📤 [OUT] 
#   - pct_progress: 백테스트 진행률 (%)
#   - current_price: 실시간 가상 현재가 (0.1초 단위 틱 대체)
#   - df_1m: 현재까지 누적된 60개의 1분봉 데이터프레임
#   - is_closed: 현재 캔들이 마감되었는지 여부 (마감 시에만 AI 추론 허용)
#   - is_running: 백테스트 구동 상태 유지 여부
# ==============================================================================

import pandas as pd
import numpy as np
import os

class Historical_DataEngine_PautoV75:
    def __init__(self, data_path):
        self.data_path = data_path
        if not os.path.exists(self.data_path):
            raise FileNotFoundError(f"데이터 파일이 존재하지 않습니다: {self.data_path}")
            
        # 과거 데이터 메모리 로드 및 타임스탬프 인덱싱
        self.df = pd.read_csv(self.data_path, index_col='timestamp', parse_dates=True)
        self.total_rows = len(self.df)
        self.current_idx = 0
        
        # 틱 시뮬레이션 상태 변수 (0: Open, 1: High/Low, 2: Low/High, 3: Close)
        self.tick_step = 0 
        
        # AI 추론을 위해 최소한으로 필요한 캔들 윈도우 사이즈
        self.min_history_window = 60 

    def next_step(self):
        # 백테스팅 종료 조건
        if self.current_idx >= self.total_rows:
            return 100.0, 0.0, None, False, False

        row = self.df.iloc[self.current_idx]

        # 틱(Tick) 섀도우 연산 로직: 1분봉을 4틱으로 분할
        # 양봉/음봉에 따라 고가와 저가의 도달 순서를 논리적으로 배치
        if self.tick_step == 0:
            current_price = row['open']
        elif self.tick_step == 1:
            # 음봉이면 고가를 먼저 찍고 내려왔다고 가정, 양봉이면 저가를 먼저 찍었다고 가정
            current_price = row['high'] if row['close'] < row['open'] else row['low']
        elif self.tick_step == 2:
            current_price = row['low'] if row['close'] < row['open'] else row['high']
        elif self.tick_step == 3:
            current_price = row['close']

        is_closed = (self.tick_step == 3)
        pct_progress = (self.current_idx / self.total_rows) * 100.0

        # AI 예측 및 장세 판단 모듈에 넘겨줄 df_1m 슬라이싱
        if self.current_idx < self.min_history_window:
            df_1m = self.df.iloc[0:self.current_idx + 1].copy()
        else:
            df_1m = self.df.iloc[self.current_idx - self.min_history_window + 1 : self.current_idx + 1].copy()

        # [중요] 아직 마감되지 않은 현재 캔들의 종가를 실시간 틱 가격으로 덮어씀 (미래 데이터 참조 방지)
        df_1m.iloc[-1, df_1m.columns.get_loc('close')] = current_price

        # 다음 틱을 위한 스텝 전진
        self.tick_step += 1
        if self.tick_step > 3:
            self.tick_step = 0
            self.current_idx += 1

        return pct_progress, current_price, df_1m, is_closed, True