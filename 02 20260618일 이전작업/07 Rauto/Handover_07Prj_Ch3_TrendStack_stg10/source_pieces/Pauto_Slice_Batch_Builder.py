# Pauto_Slice_Batch_Builder.py
import time
import requests
import pandas as pd
import os
from datetime import datetime

class PautoKlinesDownloader:
    def __init__(self):
        # 1. 백테스팅 원칙: 최소 설정값
        self.TIMEFRAME = '1m'
        self.LEVERAGE = 10
        self.ENTRY_QTY = 0.1 # BTC
        self.SL_TP_RATIO = 2.0
        
        # 슬라이싱 다운로드 설정
        self.window_before_hours = 7
        self.window_after_hours = 7
        self.base_url = "https://fapi.binance.com/fapi/v1/klines"
        self.sleep_time = 0.5 # API 트래픽 한도 회피용 0.5초 딜레이
        self.is_position_open = False # 2. 백테스팅 원칙: 기존 매매 청산 완료 여부

    def fetch_binance_klines(self, symbol, start_ts, end_ts):
        """
        기능: 특정 구간(start_ts ~ end_ts)의 1분봉 데이터를 바이낸스에서 가져옴.
        Lookahead Bias 체크: 과거의 명확한 start~end 구간(14시간)만을 쿼리하여 사후(미래) 데이터 유출을 구조적으로 차단.
        """
        params = {
            "symbol": symbol,
            "interval": self.TIMEFRAME,
            "startTime": int(start_ts * 1000), # 밀리초 변환
            "endTime": int(end_ts * 1000),     # 밀리초 변환
            "limit": 1500 # 14시간=840분이므로 1500한도 내에서 안전한 단일 호출
        }
        
        response = requests.get(self.base_url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 
                    'close_time', 'quote_av', 'trades', 'taker_base_vol', 'taker_quote_vol', 'ignore']
            df = pd.DataFrame(data, columns=cols)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        else:
            raise Exception(f"API Error {response.status_code}: {response.text}")

    def process_trade_list(self, symbol, trade_timestamps, output_dir="Pauto_Slices"):
        """
        기능: 264건의 거래 시간 리스트를 받아, 각각 전후 7시간 분량의 1분봉을 CSV로 저장.
        """
        try:
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                
            total_trades = len(trade_timestamps)
            print(f"[시스템] 총 {total_trades}건의 14시간 슬라이스 데이터 다운로드를 시작합니다...")
            
            for idx, signal_ts in enumerate(trade_timestamps):
                # 윈도우 계산 (UTC 초 단위)
                start_ts = signal_ts - (self.window_before_hours * 3600)
                end_ts = signal_ts + (self.window_after_hours * 3600)
                
                # API 데이터 확보
                df_slice = self.fetch_binance_klines(symbol, start_ts, end_ts)
                
                # 타임스탬프를 활용해 파일명 생성 ('BTCUSDT_1m_slice_20230505_160000.csv')
                dt_str = datetime.utcfromtimestamp(signal_ts).strftime('%Y%m%d_%H%M%S')
                file_name = f"{output_dir}/{symbol}_1m_slice_{dt_str}.csv"
                df_slice.to_csv(file_name, index=False)
                
                # 10건 단위로 진행상황 출력
                if (idx + 1) % 10 == 0:
                    print(f" - 진행 상황: {idx + 1} / {total_trades} 건 완료")
                
                time.sleep(self.sleep_time) # 트래픽(Rate Limit) 방어
                
            return f"Success: {total_trades}건의 이벤트 슬라이싱 다운로드 및 CSV 저장이 완료되었습니다."
            
        except Exception as e:
            # 에러 발생 시 수정 코드 선 제시 금지 원칙 준수
            return f"Error Data Process: {str(e)}"

def run_batch():
    """
    기능: stg4_mae_ledger.csv에서 시간을 추출하여 다운로더 실행.
    Lookahead Bias 체크: exit_t(청산시간) 등 미래에 결정되는 결과 데이터는 제외하고 오직 진입시간(entry_t)만 추출.
    """
    csv_filename = "stg4_mae_ledger.csv"
    symbol = "BTCUSDT"
    
    try:
        # 원장 데이터 로드
        df_ledger = pd.read_csv(csv_filename)
        
        # 문자열('2023-05-05 16:00:00') -> 날짜 객체 -> API용 Unix Timestamp(초 단위) 변환
        df_ledger['entry_t'] = pd.to_datetime(df_ledger['entry_t'])
        trade_timestamps = (df_ledger['entry_t'].astype('int64') // 10**9).tolist()
        
        # 다운로드 실행
        downloader = PautoKlinesDownloader()
        result = downloader.process_trade_list(symbol, trade_timestamps)
        
        print(f"\n[최종 완료] {result}")
        
    except Exception as e:
        print(f"Error Batch Exec: {str(e)}")

if __name__ == "__main__":
    run_batch()