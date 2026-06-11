"""
[파일명] pautov75_signal_wrapper_trace.py
코드길이: 약 200줄, 내부버전 v3.4-pauto-trace
목적: 새 채팅 Claude 요청 1 — prob/regime trace를 봉별 csv로 저장
       ⓟ-12 (ATR 학습/추론 불일치)의 OOS 영향 정량 측정

In:
  - 기존 wrapper와 동일 인자
  - trace_csv_path: 출력 csv 경로 (None이면 outputs_v34_pauto_trace/trace.csv)
  - sample_every: 1봉마다 (1) 또는 N봉마다 (N>1) 기록. 1로 시작 권장

Out:
  - long_indices, short_indices, stats (기존과 동일)
  - trace csv: columns = [bar_idx, timestamp, prob, regime, action]
    525,540행이면 약 30MB. 사용자 PC 부담 작음.

[추가 동작]
  - prob 추출은 Predict_ML.get_signal의 reason 문자열 파싱:
    "AI 11.7% | OI델타 ..." → 11.7
  - Predict_ML 코드 변경 안 함 (사용자 IS 모델과 호환 유지)
"""

import os
import sys
import re
import numpy as np
import pandas as pd
import xgboost as xgb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from Predict_ML_PautoV75 import Predict_ML_PautoV75
from Regime_Master_PautoV75 import Regime_Master_PautoV75


# reason에서 "AI XX.X%" 추출
_PROB_PATTERN = re.compile(r"AI\s*(\d+(?:\.\d+)?)%")


def _extract_prob(reason: str) -> float:
    """reason 문자열에서 prob 추출. 매칭 실패 시 NaN"""
    if not reason:
        return float('nan')
    m = _PROB_PATTERN.search(reason)
    if m:
        return float(m.group(1)) / 100.0  # % → 0~1
    return float('nan')


def extract_signals_pautov75_trace(
    df_1m: pd.DataFrame,
    model_path: str,
    threshold_long: float = 0.80,
    threshold_short: float = 0.20,
    window_size: int = 60,
    start_idx: int = None,
    end_idx: int = None,
    verbose_every: int = 50000,
    trace_csv_path: str = None,
    sample_every: int = 1,
):
    """
    기존 wrapper에 trace 로깅 추가.
    
    추가 기능:
        sample_every=1이면 *모든 봉* 기록 (525,540행 csv ~ 30MB)
        sample_every=10이면 10봉마다 (~3MB)
        sample_every=60이면 1시간마다 (~500KB)
    """
    # === 인스턴스 생성 (기존과 동일) ===
    predict_inst = Predict_ML_PautoV75()
    if not predict_inst.model_loaded:
        if os.path.exists(model_path):
            predict_inst.model = xgb.Booster()
            predict_inst.model.load_model(model_path)
            predict_inst.model_loaded = True
        else:
            raise FileNotFoundError(f"ML 모델 파일 없음: {model_path}")

    regime_inst = Regime_Master_PautoV75()
    params = {
        'ml_long_threshold': threshold_long,
        'ml_short_threshold': threshold_short,
    }

    n_bars = len(df_1m)
    if start_idx is None:
        start_idx = window_size
    if end_idx is None:
        end_idx = n_bars

    if start_idx < window_size:
        print(f"⚠️ start_idx={start_idx} < window_size={window_size}. 자동 조정")
        start_idx = window_size

    long_list = []
    short_list = []
    n_long_signal = 0
    n_short_signal = 0
    n_regime = {'BULLISH_EXPANSION': 0, 'BEARISH_EXPANSION': 0, 'CHOPPY': 0, 'OTHER': 0}
    n_wait = 0
    
    # trace 누적
    trace_rows = []
    
    # 인덱스가 timestamp인지 확인
    has_ts_index = pd.api.types.is_datetime64_any_dtype(df_1m.index)

    print(f"[Pauto wrapper trace] 신호 추출 + trace 로깅 시작")
    print(f"  봉 {start_idx} ~ {end_idx-1} = {end_idx-start_idx:,}개")
    print(f"  trace sample_every = {sample_every} (매 {sample_every}봉마다 기록)")

    for t in range(start_idx, end_idx):
        window = df_1m.iloc[t - window_size + 1 : t + 1].copy()

        try:
            regime = regime_inst.get_regime(window, params)
        except Exception:
            regime = "CHOPPY"
        if regime in n_regime:
            n_regime[regime] += 1
        else:
            n_regime['OTHER'] += 1

        signal = predict_inst.get_signal(window, regime, params)
        action = signal.get('action', 'WAIT')
        reason = signal.get('reason', '')
        prob = _extract_prob(reason)  # NaN이면 모델 미동작 봉

        if action == 'OPEN_LONG':
            long_list.append(t)
            n_long_signal += 1
        elif action == 'OPEN_SHORT':
            short_list.append(t)
            n_short_signal += 1
        else:
            n_wait += 1

        # trace 로깅 (sample_every 봉마다)
        if (t - start_idx) % sample_every == 0:
            ts = df_1m.index[t] if has_ts_index else t
            trace_rows.append({
                'bar_idx': t,
                'timestamp': str(ts),
                'prob': prob,
                'regime': regime,
                'action': action,
            })

        if verbose_every > 0 and (t - start_idx + 1) % verbose_every == 0:
            print(f"  진행: {t - start_idx + 1:,}/{end_idx - start_idx:,} "
                  f"(L={n_long_signal} S={n_short_signal})")

    long_indices = np.array(long_list, dtype=np.int64)
    short_indices = np.array(short_list, dtype=np.int64)

    # trace csv 저장
    if trace_csv_path is None:
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outputs_v34_pauto_trace')
        os.makedirs(out_dir, exist_ok=True)
        trace_csv_path = os.path.join(out_dir, 'trace.csv')
    
    trace_df = pd.DataFrame(trace_rows)
    trace_df.to_csv(trace_csv_path, index=False, encoding='utf-8-sig')
    
    stats = {
        'n_total_bars': end_idx - start_idx,
        'n_long_signals': len(long_indices),
        'n_short_signals': len(short_indices),
        'n_wait': n_wait,
        'regime_distribution': n_regime,
        'signal_pct': {
            'long': 100 * len(long_indices) / max(1, end_idx - start_idx),
            'short': 100 * len(short_indices) / max(1, end_idx - start_idx),
        },
        'trace_csv_path': trace_csv_path,
        'trace_rows': len(trace_rows),
        'prob_nan_count': int(trace_df['prob'].isna().sum()) if len(trace_df) else 0,
    }

    print(f"\n[Pauto wrapper trace] 완료")
    print(f"  전체 봉: {stats['n_total_bars']:,}")
    print(f"  Long 신호: {stats['n_long_signals']:,}")
    print(f"  Short 신호: {stats['n_short_signals']:,}")
    print(f"  trace 저장: {trace_csv_path} ({len(trace_rows):,} 행)")
    print(f"  prob NaN (모델 미동작 봉): {stats['prob_nan_count']:,}")

    return long_indices, short_indices, stats


# ==========================================
# 통계 분석 헬퍼
# ==========================================
def analyze_trace(trace_csv_path: str):
    """trace csv 분포 통계 출력. 새 채팅 Claude의 ⓟ-12 검증용"""
    df = pd.read_csv(trace_csv_path)
    print(f"\n=== Trace 분석: {trace_csv_path} ===")
    print(f"총 행수: {len(df):,}")
    print()
    
    # prob 분포
    prob_valid = df['prob'].dropna()
    print(f"[prob 분포 — 525,540봉 중 유효 {len(prob_valid):,}개]")
    print(f"  평균: {prob_valid.mean():.4f}")
    print(f"  중간값: {prob_valid.median():.4f}")
    print(f"  std: {prob_valid.std():.4f}")
    print(f"  min: {prob_valid.min():.4f}, max: {prob_valid.max():.4f}")
    print()
    
    # prob 분포 buckets
    print(f"[prob 버킷 분포]")
    bins = [0, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.0]
    counts = pd.cut(prob_valid, bins=bins, include_lowest=True).value_counts().sort_index()
    for interval, cnt in counts.items():
        pct = 100 * cnt / len(prob_valid)
        print(f"  {interval}: {cnt:>10,} ({pct:5.2f}%)")
    print()
    
    # regime 분포
    print(f"[regime 분포]")
    print(df['regime'].value_counts().to_string())
    print()
    
    # action 분포
    print(f"[action 분포]")
    print(df['action'].value_counts().to_string())
    print()
    
    # prob × action 교차 검증
    print(f"[prob 평균 × action 교차]")
    print(df.groupby('action')['prob'].agg(['mean', 'median', 'count']).to_string())


# ==========================================
# main entry
# ==========================================
if __name__ == "__main__":
    # 사용자 PC 실행용 — measure_pf_v34_pauto.py 의 신호 추출 단계만 재실행
    import json
    
    WORK_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_PATH = os.path.join(WORK_DIR, "Merged_Data.csv")
    MODEL_PATH = os.path.join(WORK_DIR, "PautoV75_XGB_1to3_Predictor.json")
    
    OOS_START = "2025-05-01 00:00:00+00:00"
    OOS_END = "2026-04-30 23:59:00+00:00"
    
    print("="*70)
    print("[Pauto v3.4 Trace 재실행 — 새 채팅 Claude 요청 1]")
    print("="*70)
    print(f"데이터: {DATA_PATH}")
    print(f"모델: {MODEL_PATH}")
    print(f"OOS: {OOS_START} ~ {OOS_END}")
    
    # 데이터 로딩
    print(f"\n[1/2] 데이터 로딩")
    df = pd.read_csv(DATA_PATH, parse_dates=['timestamp'])
    df.set_index('timestamp', inplace=True)
    
    oos_start_ts = pd.to_datetime(OOS_START)
    oos_end_ts = pd.to_datetime(OOS_END)
    if df.index.tz is not None and oos_start_ts.tz is None:
        oos_start_ts = oos_start_ts.tz_localize(df.index.tz)
        oos_end_ts = oos_end_ts.tz_localize(df.index.tz)
    
    df_oos = df.loc[oos_start_ts:oos_end_ts].copy()
    print(f"  OOS: {df_oos.index.min()} ~ {df_oos.index.max()} ({len(df_oos):,} 행)")
    
    # trace 재실행 (sample_every=1 = 모든 봉)
    print(f"\n[2/2] Trace 신호 추출 (예상 5~10분)")
    long_idx, short_idx, stats = extract_signals_pautov75_trace(
        df_oos, MODEL_PATH,
        threshold_long=0.80, threshold_short=0.20,
        window_size=60,
        sample_every=1,
    )
    
    # stats 저장
    out_dir = os.path.dirname(stats['trace_csv_path'])
    stats_path = os.path.join(out_dir, 'trace_stats.json')
    with open(stats_path, 'w', encoding='utf-8') as f:
        stats_save = {k: (int(v) if hasattr(v, 'item') else v) for k, v in stats.items()}
        json.dump(stats_save, f, indent=2, default=str)
    
    # 분석 자동 실행
    print(f"\n[Trace 분석 자동 실행]")
    analyze_trace(stats['trace_csv_path'])
    
    print(f"\n[저장 위치]")
    print(f"  Trace csv: {stats['trace_csv_path']}")
    print(f"  Stats json: {stats_path}")
    print(f"\n[Claude 업로드 zip 생성 명령]")
    print(f"  outputs_v34_pauto_trace/ 폴더 통째로 zip 압축")
