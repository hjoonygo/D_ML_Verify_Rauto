# Pauto_Slice_Merger.py
import os
import glob
import pandas as pd

class PautoSliceMerger:
    def __init__(self):
        # 1. 백테스팅 원칙: 최소 설정값
        self.TIMEFRAME = '1m'
        self.LEVERAGE = 10
        self.ENTRY_QTY = 0.1 # BTC
        self.SL_TP_RATIO = 2.0
        
        # 입출력 파일 경로 설정
        self.input_dir = "."  
        self.output_filename = "Pauto_Continuous_Merged_Dataset.csv" # 연속 차트임을 명시
        self.is_position_open = False # 2. 백테스팅 원칙: 청산 완료 여부 확인용
        
    def extract_signal_time(self, filename):
        """
        기능: 파일명에서 진입 시점 문자열 추출 (데이터의 원래 출처 파악용)
        """
        base_name = os.path.basename(filename)
        try:
            time_str = base_name.split('_')[-2] + "_" + base_name.split('_')[-1].replace('.csv', '')
            return time_str
        except Exception:
            return "UNKNOWN_EVENT"

    def merge_all_slices(self):
        """
        기능: CSV 파일들을 결합하고 중복 타임스탬프를 제거하여 연속 차트 생성
        """
        search_pattern = os.path.join(self.input_dir, "*_1m_slice_*.csv")
        file_list = glob.glob(search_pattern)
        
        if not file_list:
            return "Error: 병합할 CSV 파일들을 찾을 수 없습니다. 경로를 확인해주세요."
            
        print(f"[시스템] 총 {len(file_list)}개의 파일로 연속 차트 구축을 시작합니다...")
        
        dataframes = []
        for file in file_list:
            try:
                df_slice = pd.read_csv(file)
                event_id = self.extract_signal_time(file)
                df_slice.insert(0, 'signal_event_time', event_id)
                dataframes.append(df_slice)
            except Exception as e:
                print(f"File read error on {file}: {str(e)}")
                
        if dataframes:
            # ==============================================================
            # 핵심 로직: 단일 연속 차트 DB 구축을 위한 병합 및 중복 타임스탬프 제거
            # ==============================================================
            
            # [기존 로직 주석 처리: 독립된 이벤트 샘플 유지를 위한 단순 병합]
            # merged_df = pd.concat(dataframes, ignore_index=True)
            # merged_df = merged_df.sort_values(by=['signal_event_time', 'timestamp'])
            
            # [새 로직 추가: 연속 차트용 중복 시간 제거]
            merged_df = pd.concat(dataframes, ignore_index=True)
            
            # 1. 시계열 데이터의 Lookahead Bias 방지를 위해 절대 시간순(과거->미래) 정렬
            merged_df = merged_df.sort_values(by='timestamp')
            
            # 2. 동일한 타임스탬프가 겹칠 경우, 가장 먼저 기록된 과거 데이터 하나만 남기고 삭제
            initial_rows = len(merged_df)
            merged_df = merged_df.drop_duplicates(subset=['timestamp'], keep='first')
            final_rows = len(merged_df)
            
            deleted_rows = initial_rows - final_rows
            
            merged_df.to_csv(self.output_filename, index=False)
            return f"Success: 병합 완료. 겹치는 시간 {deleted_rows}행 제거됨. 총 {final_rows}행의 연속 데이터가 '{self.output_filename}'로 저장되었습니다."
        else:
            return "Error: 병합 가능한 유효 데이터가 없습니다."

def run_merger():
    merger = PautoSliceMerger()
    result = merger.merge_all_slices()
    print(f"\n[최종 완료] {result}")

if __name__ == "__main__":
    run_merger()