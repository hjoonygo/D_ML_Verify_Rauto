# -*- coding: utf-8 -*-
"""
[파일명] analyze_entry_path.py
코드길이: 약 280줄, 내부버전명: v1.0 (entry_path_analysis), 로직 축약/생략 없이 전체 출력

[목적]
  사용자 가설 검증: "상승장 진입 거래가 휩쏘 후 회복하는가?"
  - uptrend long 44건 + hivol_range long 74건 = 118건의 진입 후 12H 가격 path 추출
  - 4H timeout 이후 8H/12H 시점 가격 비교 → timeout 후 회복 패턴 측정
  - initial_sl 발동 거래의 SL 시점부터 +4H 가격 → 휩쏘 후 회복 비율 측정
  - 진입 후 path 패턴 분류 (휩쏘 / 정체 / 즉시 역방향 / 점진적 손실)

[실행 환경 위치]
  실행 폴더: D:\\ML\\Verify\\code_stage_3\\
  Raw 1m봉 데이터: D:\\ML\\Verify\\Merged_Data.csv (부모 폴더에 존재)
  진입 거래 csv: D:\\ML\\Verify\\code_stage_3\\outputs_stage_3\\trades_sl_max_180bp.csv
  결과 출력: D:\\ML\\Verify\\code_stage_3\\outputs_path_analysis\\

[실행 방법]
  cd D:\\ML\\Verify\\code_stage_3
  python analyze_entry_path.py

[예상 소요 시간]
  5~10분 (데이터 로드 + 118건 path 추출)

[결과 파일]
  outputs_path_analysis/entry_paths_full.csv     - 118건 거래별 path 통계
  outputs_path_analysis/path_analysis_log.txt    - 요약 통계 및 패턴 분류 결과

[결과 zip 만들기 (분석 완료 후)]
  outputs_path_analysis 폴더 전체를 zip으로 묶어 업로드:
  zip명: path_analysis_2026-05-19.zip

[변수 파이프라인]
  IN: trades_sl_max_180bp.csv, Merged_Data.csv (1m봉)
  STATE: 각 거래의 entry_t를 기준으로 raw 데이터에서 +/-시간만큼 slice
  OUT: 거래별 path 통계 csv + 요약 로그

[함수 In/Out]
  load_data() -> (df_trades, df_raw)
    IN: 파일 경로
    OUT: trades DataFrame, raw 1m봉 DataFrame
  
  extract_path(df_raw, entry_t, exit_t, side, entry_price) -> Dict
    IN: raw 데이터, 진입/청산 시각, side, 진입가
    OUT: dict (진입 후 1H/2H/4H/6H/8H/12H 가격, 최고/최저, 휩쏘 지표 등)
  
  classify_pattern(path_dict) -> str
    IN: extract_path 결과
    OUT: 'whipsaw_recover' / 'stagnation' / 'immediate_reverse' / 'gradual_loss' / 'normal_win' / 'other'
"""
import os
import sys
import time
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_PATH = os.path.join(WORK_DIR, "..", "Merged_Data.csv")
TRADES_PATH = os.path.join(WORK_DIR, "outputs_stage_3", "trades_sl_max_180bp.csv")
OUTPUT_DIR = os.path.join(WORK_DIR, "outputs_path_analysis")
LOG_PATH = os.path.join(OUTPUT_DIR, "path_analysis_log.txt")
RESULT_CSV = os.path.join(OUTPUT_DIR, "entry_paths_full.csv")

# 분석 시간 윈도우 (분)
HORIZONS_MIN = [60, 120, 240, 360, 480, 720]  # 1H, 2H, 4H, 6H, 8H, 12H

log_lines = []
def log(msg):
    print(msg)
    log_lines.append(str(msg))


def load_data():
    log("\n[1/4] 데이터 로드")
    
    if not os.path.exists(RAW_PATH):
        log(f"X Raw 데이터 없음: {RAW_PATH}")
        sys.exit(1)
    if not os.path.exists(TRADES_PATH):
        log(f"X Trades csv 없음: {TRADES_PATH}")
        sys.exit(1)
    
    log(f"  Raw 1m봉: {RAW_PATH}")
    df_raw = pd.read_csv(RAW_PATH, parse_dates=['timestamp']).set_index('timestamp')
    if df_raw.index.tz is None:
        df_raw.index = df_raw.index.tz_localize('UTC')
    log(f"    {df_raw.index.min()} ~ {df_raw.index.max()} ({len(df_raw):,}봉)")
    
    log(f"  Trades csv: {TRADES_PATH}")
    df_trades = pd.read_csv(TRADES_PATH, parse_dates=['entry_t', 'exit_t'])
    
    # 진입 거래만
    valid_exits = ['initial_sl','step1_sl','step2_sl','step3_sl',
                   'timeout_4h','timeout_step_active','reversal_2h']
    df_trades = df_trades[df_trades['exit_reason'].isin(valid_exits)].copy()
    log(f"    진입 거래: {len(df_trades)}건")
    
    # uptrend long + hivol_range long만
    mask = ((df_trades['regime']=='uptrend') & (df_trades['side']=='long')) | \
           ((df_trades['regime']=='hivol_range') & (df_trades['side']=='long'))
    df_target = df_trades[mask].copy().reset_index(drop=True)
    log(f"    분석 대상 (uptrend long + hivol_range long): {len(df_target)}건")
    log(f"      uptrend long: {(df_target['regime']=='uptrend').sum()}건")
    log(f"      hivol_range long: {(df_target['regime']=='hivol_range').sum()}건")
    
    return df_target, df_raw


def extract_path(df_raw, entry_t, exit_t, side, entry_price):
    """
    진입 후 path 추출. side는 모두 'long'이라 가정.
    가격 변화는 long 관점에서 + 가 수익 방향.
    """
    result = {
        'entry_price_actual': None,
    }
    
    # entry_t 정확히 일치하는 idx 찾기
    entry_t_pd = pd.Timestamp(entry_t)
    if entry_t_pd.tz is None:
        entry_t_pd = entry_t_pd.tz_localize('UTC')
    
    try:
        # entry_t 시점부터 +12H + 60분 buffer 슬라이스
        end_t = entry_t_pd + pd.Timedelta(minutes=720+60)
        path = df_raw.loc[entry_t_pd:end_t]
    except KeyError:
        return None
    
    if len(path) < 60:
        return None  # 데이터 부족
    
    # 진입 직후 1m봉의 open이 실제 진입가 (시뮬레이터와 동일)
    if len(path) >= 1:
        result['entry_price_actual'] = float(path.iloc[0]['open'])
    else:
        return None
    
    ep = result['entry_price_actual']
    
    # 각 horizon 시점 가격
    for h in HORIZONS_MIN:
        if len(path) > h:
            close_h = float(path.iloc[h]['close'])
            pct = (close_h - ep) / ep
            result[f'price_pct_{h}min'] = pct
        else:
            result[f'price_pct_{h}min'] = None
    
    # 진입 후 4H 내 최저/최고 (long 관점에서 최저=손실, 최고=수익 방향)
    p4h = path.iloc[:min(241, len(path))]  # 0~240분
    result['min_pct_4h'] = (float(p4h['low'].min()) - ep) / ep
    result['max_pct_4h'] = (float(p4h['high'].max()) - ep) / ep
    
    # 진입 후 12H 내 최저/최고
    p12h = path.iloc[:min(721, len(path))]
    result['min_pct_12h'] = (float(p12h['low'].min()) - ep) / ep
    result['max_pct_12h'] = (float(p12h['high'].max()) - ep) / ep
    
    # 4H 시점 가격 대비 12H 시점 가격 변화 (timeout 후 회복 여부)
    if result.get('price_pct_240min') is not None and result.get('price_pct_720min') is not None:
        result['recovery_4h_to_12h'] = result['price_pct_720min'] - result['price_pct_240min']
    
    # 휩쏘 지표: 4H 내 -0.5% 이상 갔다가 회복했는가
    # 휩쏘 = (min_pct_4h < -0.5%) AND (12H 시점 가격이 진입가 이상)
    if result.get('price_pct_720min') is not None:
        result['is_whipsaw'] = (result['min_pct_4h'] < -0.005) and (result['price_pct_720min'] > 0)
    
    # 12H 시점에 결국 어디로 갔는가
    if result.get('price_pct_720min') is not None:
        p12 = result['price_pct_720min']
        if p12 > 0.005:
            result['final_dir_12h'] = 'recovered_up'  # 결국 long 방향 회복
        elif p12 < -0.005:
            result['final_dir_12h'] = 'continued_down'  # 계속 손실 방향
        else:
            result['final_dir_12h'] = 'flat'
    
    return result


def classify_pattern(row):
    """진입 후 path 패턴 분류"""
    min4h = row.get('min_pct_4h', 0)
    max4h = row.get('max_pct_4h', 0)
    p4h = row.get('price_pct_240min', 0)
    p12h = row.get('price_pct_720min')
    
    if min4h is None or max4h is None or p4h is None:
        return 'data_insufficient'
    
    # 분류 로직
    range_4h = max4h - min4h
    
    if abs(min4h) < 0.005 and abs(max4h) < 0.005:
        return 'stagnation'  # 4H 내 ±0.5% 안에서만 움직임
    
    if min4h < -0.01 and max4h < 0.003:
        return 'immediate_reverse'  # 진입 후 즉시 -1% 이상 + long 방향 0.3% 미만
    
    if p12h is not None and p12h > 0.005 and min4h < -0.005:
        return 'whipsaw_recover'  # 4H 내 -0.5% 갔다가 12H 시점 +0.5% 이상 회복
    
    if p4h < -0.005 and min4h < -0.005:
        return 'gradual_loss'  # 4H 시점 -0.5% 이하 + 4H 내 -0.5% 도달
    
    if p4h > 0.005:
        return 'normal_win'  # 4H 시점 +0.5% 이상 (수익 방향)
    
    return 'other'


def main():
    t_start = time.time()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    log("="*78)
    log(f"[Entry Path Analysis 시작] {pd.Timestamp.now()}")
    log("="*78)
    log(f"실행 폴더: {WORK_DIR}")
    log(f"Raw 1m봉:  {RAW_PATH}")
    log(f"Trades csv: {TRADES_PATH}")
    log(f"결과 폴더:  {OUTPUT_DIR}")
    
    # 데이터 로드
    df_target, df_raw = load_data()
    
    # path 추출
    log(f"\n[2/4] 거래별 path 추출 (각 +12H = 720분)")
    t_extract = time.time()
    all_paths = []
    for i, row in df_target.iterrows():
        path_data = extract_path(df_raw, row['entry_t'], row['exit_t'], row['side'], row['entry_price'])
        if path_data is None:
            continue
        
        record = {
            'entry_signal_idx_1m': row['entry_signal_idx_1m'],
            'entry_t': row['entry_t'],
            'side': row['side'],
            'regime': row['regime'],
            'exit_reason': row['exit_reason'],
            'exit_t': row['exit_t'],
            'bars_held_1m': row['bars_held_1m'],
            'price_roe_orig': row['price_roe'],
            'net_return_orig': row['net_return'],
            'initial_sl_dist': row['initial_sl_dist'],
            'atr_pct_at_entry': row['atr_pct_at_entry'],
            'multiplier_used': row['multiplier_used'],
            'step_active_max': row['step_active_max'],
        }
        record.update(path_data)
        all_paths.append(record)
        
        if (i+1) % 20 == 0:
            log(f"    {i+1}/{len(df_target)} 처리 중...")
    
    log(f"  완료: {len(all_paths)}건 (소요 {time.time()-t_extract:.1f}초)")
    
    df_result = pd.DataFrame(all_paths)
    df_result['pattern'] = df_result.apply(classify_pattern, axis=1)
    
    # 결과 저장
    df_result.to_csv(RESULT_CSV, index=False, encoding='utf-8-sig')
    log(f"\n  결과 csv 저장: {RESULT_CSV}")
    
    # ============ 요약 분석 ============
    log(f"\n[3/4] 패턴 분류 결과")
    log("="*78)
    
    # 전체 분류
    log(f"\n[전체 {len(df_result)}건 패턴 분포]")
    pattern_counts = df_result['pattern'].value_counts()
    for p, n in pattern_counts.items():
        log(f"  {p:25s}: {n:3d}건 ({n/len(df_result):.1%})")
    
    # regime별 분류
    log(f"\n[regime별 패턴 분포]")
    pivot = pd.crosstab(df_result['regime'], df_result['pattern'])
    log(pivot.to_string())
    
    # 휩쏘 후 회복 거래 자세히
    log(f"\n[휩쏘 후 회복 거래 — 사용자 가설 핵심]")
    whipsaw_recovery = df_result[df_result['is_whipsaw']==True]
    log(f"  전체 휩쏘 후 회복: {len(whipsaw_recovery)}/{len(df_result)}건 = {len(whipsaw_recovery)/len(df_result):.1%}")
    
    for reg in ['uptrend', 'hivol_range']:
        sub = df_result[df_result['regime']==reg]
        ws = sub[sub['is_whipsaw']==True]
        log(f"  {reg}: {len(ws)}/{len(sub)}건 = {len(ws)/len(sub):.1%}")
    
    # 4H 이후 회복 통계
    log(f"\n[4H timeout 이후 회복 통계 (4H → 12H 가격 변화)]")
    valid = df_result[df_result['recovery_4h_to_12h'].notna()]
    log(f"  유효 데이터: {len(valid)}/{len(df_result)}건")
    if len(valid) > 0:
        log(f"  4H → 12H 평균: {valid['recovery_4h_to_12h'].mean()*100:+.3f}%")
        log(f"  4H → 12H median: {valid['recovery_4h_to_12h'].median()*100:+.3f}%")
        log(f"  회복 (>+0.5%): {(valid['recovery_4h_to_12h']>0.005).sum()}건")
        log(f"  계속 손실 (<-0.5%): {(valid['recovery_4h_to_12h']<-0.005).sum()}건")
        log(f"  무변화 (±0.5%): {((valid['recovery_4h_to_12h']>=-0.005) & (valid['recovery_4h_to_12h']<=0.005)).sum()}건")
    
    # timeout으로 끝난 거래의 12H 결과
    log(f"\n[timeout_4h로 끝난 거래의 12H 시점 가격]")
    tot = df_result[df_result['exit_reason']=='timeout_4h']
    log(f"  n={len(tot)}")
    if len(tot) > 0:
        log(f"  12H 시점 평균 가격 변화: {tot['price_pct_720min'].mean()*100:+.3f}%")
        log(f"  12H 시점 회복 (>+0.5%): {(tot['price_pct_720min']>0.005).sum()}건")
        log(f"  12H 시점 계속 손실: {(tot['price_pct_720min']<-0.005).sum()}건")
    
    # initial_sl로 끝난 거래의 SL 시점 이후
    log(f"\n[initial_sl 발동 거래의 12H 시점 가격]")
    isl = df_result[df_result['exit_reason']=='initial_sl']
    log(f"  n={len(isl)}")
    if len(isl) > 0:
        log(f"  12H 시점 평균 가격 변화: {isl['price_pct_720min'].mean()*100:+.3f}%")
        log(f"  12H 시점 회복 (>+0.5%): {(isl['price_pct_720min']>0.005).sum()}건")
        log(f"  12H 시점 계속 손실: {(isl['price_pct_720min']<-0.005).sum()}건")
        log(f"  → SL 발동 후에도 가격이 회복했는가? 위 회복 건수로 확인")
    
    # 핵심 통계 — 사용자 가설 직접 답
    log(f"\n[4/4] 사용자 가설 직접 답변")
    log("="*78)
    n_total = len(df_result)
    n_whipsaw = (df_result['is_whipsaw']==True).sum()
    n_stagnation = (df_result['pattern']=='stagnation').sum()
    n_immediate_rev = (df_result['pattern']=='immediate_reverse').sum()
    n_gradual = (df_result['pattern']=='gradual_loss').sum()
    
    log(f"\n  '휩쏘 후 회복' 패턴: {n_whipsaw}/{n_total}건 = {n_whipsaw/n_total:.1%}")
    log(f"  '정체 (stagnation)' 패턴: {n_stagnation}/{n_total}건 = {n_stagnation/n_total:.1%}")
    log(f"  '즉시 역방향' 패턴: {n_immediate_rev}/{n_total}건 = {n_immediate_rev/n_total:.1%}")
    log(f"  '점진적 손실' 패턴: {n_gradual}/{n_total}건 = {n_gradual/n_total:.1%}")
    log(f"\n  → 휩쏘 비율이 30% 이상이면 사용자 가설 부분 타당")
    log(f"  → 휩쏘 비율이 10% 미만이면 사용자 가설 부정")
    
    # 로그 저장
    t_total = time.time() - t_start
    log(f"\n[총 소요: {t_total:.1f}초]")
    
    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_lines))
    log(f"\n로그 저장: {LOG_PATH}")
    log(f"결과 csv: {RESULT_CSV}")
    log(f"\n[zip 만들기 안내]")
    log(f"  PowerShell 또는 탐색기에서 outputs_path_analysis 폴더를 zip으로 압축:")
    log(f"  zip 이름 예: path_analysis_2026-05-19.zip")
    log(f"  업로드 후 분석 진행")


if __name__ == "__main__":
    main()
