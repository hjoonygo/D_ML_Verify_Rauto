# -*- coding: utf-8 -*-
"""
[파일명] train_phase_b.py
코드길이: 약 80줄, 내부버전명: v1.0 (phase_b), 로직 축약/생략 없이 전체 출력

[목적] Phase B 학습 wrapper. 사용자 PC 36mo 데이터에서 자동 70% IS 학습.

[흐름]
  1. Merged_Data.csv 로드
  2. 첫 70%를 학습 IS로 자동 분할
  3. ML_Predictor_Pipeline_v2의 train_xgboost_3class 호출
  
[사용 파일]
  ML_Predictor_Pipeline_v2.py (DATA_PATH 자동 인식, train_xgboost_3class 사용)
"""
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    # ML_Predictor_Pipeline_v2의 DATA_PATH 임포트
    from ML_Predictor_Pipeline_v2 import train_xgboost_3class, DATA_PATH
    
    if not os.path.exists(DATA_PATH):
        print(f"❌ 데이터 파일 없음: {DATA_PATH}")
        print(f"  예상 위치: {os.path.abspath(DATA_PATH)}")
        print(f"  D:\\ML\\Verify\\Merged_Data.csv 경로 확인하세요.")
        sys.exit(1)
    
    print(f"[Phase B 학습 wrapper] 데이터 로드: {DATA_PATH}")
    df = pd.read_csv(DATA_PATH, parse_dates=['timestamp']).set_index('timestamp')
    
    # tz 처리
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    
    n_total = len(df)
    n_train = int(n_total * 0.70)
    
    train_start_ts = df.index[0]
    train_end_ts = df.index[n_train - 1]
    oos_start_ts = df.index[n_train]
    oos_end_ts = df.index[-1]
    
    train_start = train_start_ts.strftime('%Y-%m-%d %H:%M:%S')
    train_end = train_end_ts.strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"\n[자동 70% 분할]")
    print(f"  전체: {n_total:,}봉 ({train_start_ts.date()} ~ {oos_end_ts.date()})")
    print(f"  학습 IS: {n_train:,}봉 ({train_start_ts.date()} ~ {train_end_ts.date()}) - 70%")
    print(f"  OOS: {n_total - n_train:,}봉 ({oos_start_ts.date()} ~ {oos_end_ts.date()}) - 30%")
    print()
    
    # 학습 실행
    train_xgboost_3class(
        train_start=train_start,
        train_end=train_end,
        future_n=10,
    )
    
    print(f"\n✓ 학습 완료. 모델: PautoV75_XGB_3class_v2.json")


if __name__ == "__main__":
    main()
