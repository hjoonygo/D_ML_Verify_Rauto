# ==============================================================================
# [파일명] Observer_Analyze.py
# 코드길이: 약 350줄, 내부버전: V80k_Verify_1
# 작성일: 2026-05-01
# ==============================================================================
# [정체성]
#   Observer CSV 데이터를 읽어 시나리오 1~12 진단 리포트 자동 생성.
#   사용자가 가동 후 24시간 데이터 모이면 본 스크립트 실행해 분석.
#
# [📥 IN]
#   --csv: Observer CSV 경로 (단일 파일 또는 glob 패턴)
#   --baseline: 학습 분포 기준 JSON (선택, Phase 0 산출물)
# [📤 OUT]
#   stdout: 시나리오별 진단 리포트
#   --out: 분석 결과 JSON 파일 경로
#
# [사용 예]
#   python Observer_Analyze.py --csv "RautoV80k_Observer_Bot_2_*.csv" --out report.json
# ==============================================================================

import os
import sys
import json
import glob
import argparse
from datetime import datetime
from typing import List, Dict, Any

import pandas as pd
import numpy as np


def load_observer_csvs(pattern: str) -> pd.DataFrame:
    """Glob 패턴으로 여러 CSV 통합 로드."""
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"[ERROR] 파일 없음: {pattern}")
        sys.exit(1)
    print(f"[로드] {len(files)}개 파일")
    dfs = []
    for fp in files:
        try:
            df = pd.read_csv(fp)
            print(f"  {os.path.basename(fp)}: {len(df)}봉")
            dfs.append(df)
        except Exception as e:
            print(f"  ⚠️ {fp} 로드 실패: {e}")
    if not dfs:
        sys.exit(1)
    merged = pd.concat(dfs, ignore_index=True)
    if 'bar_ts' in merged.columns:
        merged = merged.drop_duplicates('bar_ts', keep='last')
        merged = merged.sort_values('bar_ts').reset_index(drop=True)
    print(f"[통합] {len(merged):,}봉")
    return merged


def report_section(title: str):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


# ==============================================================================
# 시나리오별 진단 함수
# ==============================================================================
def diag_s1_regime_distribution(df: pd.DataFrame) -> Dict[str, Any]:
    """시나리오 1: R 모듈 출력 분포."""
    report_section("시나리오 1: R 모듈 출력 분포 (distribution shift 진단)")
    out = {}

    if 'regime_output' in df.columns:
        dist = df['regime_output'].value_counts()
        print("환경 분포:")
        print(dist)
        out['env_distribution'] = dist.to_dict()

    if 'regime_proba_BULL' in df.columns:
        for env in ['BULL', 'BEAR', 'CHOP']:
            col = f'regime_proba_{env}'
            if col in df.columns:
                vals = df[col].dropna()
                if len(vals) > 0:
                    p50 = float(vals.quantile(0.50))
                    p90 = float(vals.quantile(0.90))
                    p99 = float(vals.quantile(0.99))
                    over_05 = (vals >= 0.5).mean() * 100
                    print(f"  {col}: median {p50:.3f}, p90 {p90:.3f}, p99 {p99:.3f}, ≥0.5 비율 {over_05:.1f}%")
                    out[f'{col}_p50'] = p50
                    out[f'{col}_p90'] = p90
                    out[f'{col}_p99'] = p99
                    out[f'{col}_over_05_pct'] = over_05

        # 핵심: BULL/BEAR conf 0.5 이상 도달 빈도
        bull_strong = ((df['regime_output'] == 'BULL') & (df['regime_proba_BULL'] >= 0.5)).sum()
        bear_strong = ((df['regime_output'] == 'BEAR') & (df['regime_proba_BEAR'] >= 0.5)).sum()
        chop_strong = ((df['regime_output'] == 'CHOP') & (df['regime_proba_CHOP'] >= 0.5)).sum()
        print(f"\n확정 환경 (conf ≥ 0.5):")
        print(f"  BULL: {bull_strong}봉, BEAR: {bear_strong}봉, CHOP: {chop_strong}봉")
        out['confirmed_BULL'] = int(bull_strong)
        out['confirmed_BEAR'] = int(bear_strong)
        out['confirmed_CHOP'] = int(chop_strong)
    else:
        print("⚠️ regime_proba_* 컬럼 없음 (구버전 데이터)")

    return out


def diag_s2_tbm_distribution(df: pd.DataFrame) -> Dict[str, Any]:
    report_section("시나리오 2: TBM 모듈 출력 분포")
    out = {}
    cols = ['tbm_proba_LONG', 'tbm_proba_SHORT', 'tbm_proba_NO_PROFIT']
    if all(c in df.columns for c in cols):
        # 학습 분포: NO_PROFIT 73:13:13 (Phase 1 측정)
        print("학습 분포 (Phase 1): LONG 13.3% / SHORT 13.3% / NO_PROFIT 73.4%")
        for col in cols:
            vals = df[col].dropna()
            if len(vals) > 0:
                mean = vals.mean()
                p50 = vals.quantile(0.50)
                p90 = vals.quantile(0.90)
                print(f"  {col}: mean {mean:.3f}, median {p50:.3f}, p90 {p90:.3f}")
                out[f'{col}_mean'] = float(mean)
                out[f'{col}_p50'] = float(p50)

        # NO_PROFIT 우세 봉 비율 (운영 시 73%여야 함)
        no_prof_dominant = (df['tbm_proba_NO_PROFIT'] > df[['tbm_proba_LONG', 'tbm_proba_SHORT']].max(axis=1)).mean() * 100
        print(f"\nNO_PROFIT 우세 봉: {no_prof_dominant:.1f}% (학습 73% 대비)")
        out['no_profit_dominant_pct'] = float(no_prof_dominant)
        if no_prof_dominant > 90:
            print("  ⚠️ 학습 분포 대비 NO_PROFIT 과도 — distribution shift 의심")
            out['shift_warning'] = True
    else:
        print("⚠️ tbm_proba_* 컬럼 없음")

    return out


def diag_s3_features(df: pd.DataFrame) -> Dict[str, Any]:
    report_section("시나리오 3: 30 피처 분포 (학습 vs 운영)")
    feature_cols = [c for c in df.columns if c.startswith('feature_')]
    out = {'feature_count': len(feature_cols)}
    if not feature_cols:
        print("⚠️ feature_* 컬럼 없음")
        return out
    print(f"피처 수: {len(feature_cols)}")
    print(f"\n피처 통계 (top 5 outlier 후보):")
    stats = []
    for col in feature_cols:
        vals = df[col].dropna()
        if len(vals) < 10:
            continue
        stats.append({
            'feature': col.replace('feature_', ''),
            'mean': float(vals.mean()),
            'std': float(vals.std()),
            'min': float(vals.min()),
            'max': float(vals.max()),
            'p99-p1': float(vals.quantile(0.99) - vals.quantile(0.01)),
        })
    # std 큰 순 (변동 폭 큰 피처)
    stats_sorted = sorted(stats, key=lambda s: -s['std'])
    print(f"  {'feature':30s} {'mean':>10s} {'std':>10s} {'p99-p1':>10s}")
    for s in stats_sorted[:5]:
        print(f"  {s['feature']:30s} {s['mean']:>10.3f} {s['std']:>10.3f} {s['p99-p1']:>10.3f}")
    out['top5_volatile'] = stats_sorted[:5]
    return out


def diag_s4_ob(df: pd.DataFrame) -> Dict[str, Any]:
    report_section("시나리오 4: OB 분석 정상성")
    out = {}
    if 'ob_bull_count' in df.columns:
        bull_zero = (df['ob_bull_count'] == 0).mean() * 100
        bear_zero = (df['ob_bear_count'] == 0).mean() * 100
        print(f"OB 부족 비율 (둘 중 하나라도 0):")
        print(f"  bull_obs == 0: {bull_zero:.1f}%, bear_obs == 0: {bear_zero:.1f}%")
        out['ob_bull_zero_pct'] = float(bull_zero)
        out['ob_bear_zero_pct'] = float(bear_zero)
    if 'sl_raw_pct_candidate' in df.columns:
        sl = df['sl_raw_pct_candidate'].dropna()
        sl_nonzero = sl[sl > 0]
        if len(sl_nonzero) > 0:
            print(f"sl_raw_pct (OB 발견된 봉): mean {sl_nonzero.mean():.3f}%, p90 {sl_nonzero.quantile(0.9):.3f}%")
            print(f"  > 0.10% (SL_TOO_FAR 임계 초과) 비율: {(sl_nonzero > 0.10).mean() * 100:.1f}%")
            out['sl_too_far_pct'] = float((sl_nonzero > 0.10).mean() * 100)
    return out


def diag_s5_block_gates(df: pd.DataFrame) -> Dict[str, Any]:
    report_section("시나리오 5: 게이트별 차단 분포 (핫스팟 식별) ★ 핵심")
    out = {}
    if 'block_gate' not in df.columns:
        print("⚠️ block_gate 컬럼 없음")
        return out
    dist = df['block_gate'].value_counts()
    total = len(df)
    print("게이트별 분포:")
    for gate, n in dist.items():
        pct = n / total * 100
        print(f"  {gate:20s}: {n:7,}봉 ({pct:5.1f}%)")
        out[gate] = {'count': int(n), 'pct': float(pct)}

    # 핵심 진단: PASS 비율
    pass_pct = (df['block_gate'] == 'PASS').mean() * 100
    out['_pass_pct'] = float(pass_pct)
    print(f"\n★ PASS (모든 게이트 통과): {pass_pct:.2f}% — 시간당 {pass_pct * 60 / 100:.2f}건 sim 시그널")

    if pass_pct == 0:
        print("  ⚠️ PASS 0건 — 어디선가 모든 게이트 막힘. 분포 보고 진짜 원인 식별 필요")
    return out


def diag_s7_health(df: pd.DataFrame) -> Dict[str, Any]:
    report_section("시나리오 7: 시스템 헬스 (추론 시간)")
    out = {}
    for col in ['r_inference_ms', 'p_inference_ms', 'ob_analysis_ms']:
        if col in df.columns:
            vals = df[col].dropna()
            vals = vals[vals > 0]
            if len(vals) > 0:
                p50 = vals.quantile(0.5)
                p99 = vals.quantile(0.99)
                print(f"  {col}: median {p50:.1f}ms, p99 {p99:.1f}ms, max {vals.max():.0f}ms")
                out[f'{col}_p50'] = float(p50)
                out[f'{col}_p99'] = float(p99)
    return out


def diag_s8_subregime(df: pd.DataFrame) -> Dict[str, Any]:
    report_section("시나리오 8: Sub-regime 분류 안정성")
    out = {}
    if 'subregime' not in df.columns:
        print("⚠️ subregime 컬럼 없음 (Verify_1 게이트 비활성)")
        return out
    dist = df['subregime'].value_counts()
    print("Sub-regime 분포:")
    print(dist)

    # 변경률
    if len(df) > 1:
        changes = (df['subregime'] != df['subregime'].shift(1)).sum()
        change_rate = changes / len(df) * 100
        print(f"\n변경률: {change_rate:.2f}%/봉 (Phase 3b 목표 < 21%)")
        out['change_rate_pct'] = float(change_rate)
    return out


def diag_s11_label_consistency(df: pd.DataFrame) -> Dict[str, Any]:
    report_section("시나리오 11: 사후 라벨 정합성")
    out = {}
    if 'label_class' not in df.columns:
        print("⚠️ label_class 컬럼 없음")
        return out
    labeled = df[df['label_class'].notna() & (df['label_class'] != '')]
    if len(labeled) < 50:
        print(f"⚠️ 사후 라벨 채워진 봉 부족 ({len(labeled)}봉) — 가동 30분 후부터 채워짐")
        return out

    dist = labeled['label_class'].value_counts(normalize=True) * 100
    print(f"운영 라벨 분포 ({len(labeled):,}봉):")
    print(f"  학습 (Phase 1): LONG 13.3% / SHORT 13.3% / NO_PROFIT 73.4%")
    for cls in ['LONG_WIN', 'SHORT_WIN', 'NO_PROFIT']:
        op_pct = dist.get(cls, 0)
        print(f"  운영: {cls} {op_pct:.1f}%")
        out[f'{cls}_pct'] = float(op_pct)
    return out


def diag_s12_simulated_signal(df: pd.DataFrame) -> Dict[str, Any]:
    report_section("시나리오 12: Observer 시뮬 시그널 (만약 진입했다면)")
    out = {}
    if 'sim_action' not in df.columns:
        print("⚠️ sim_action 컬럼 없음")
        return out
    dist = df['sim_action'].value_counts()
    print(f"sim_action 분포:")
    print(dist)
    open_signals = df[df['sim_action'].isin(['OPEN_LONG', 'OPEN_SHORT'])]
    n_signals = len(open_signals)
    out['total_sim_signals'] = int(n_signals)
    if n_signals > 0:
        signal_per_hour = n_signals / (len(df) / 60)
        print(f"\n시뮬 진입 시그널: {n_signals}건 ({signal_per_hour:.3f}건/h)")
        out['signal_per_hour'] = float(signal_per_hour)

        # 시뮬 PnL (라벨 채워진 것만)
        if 'label_class' in df.columns:
            with_label = open_signals[open_signals['label_class'].notna() & (open_signals['label_class'] != '')]
            if len(with_label) > 0:
                # 시뮬 win rate 추정
                long_signals = with_label[with_label['sim_action'] == 'OPEN_LONG']
                short_signals = with_label[with_label['sim_action'] == 'OPEN_SHORT']
                long_wr = (long_signals['label_class'] == 'LONG_WIN').mean() * 100 if len(long_signals) > 0 else 0
                short_wr = (short_signals['label_class'] == 'SHORT_WIN').mean() * 100 if len(short_signals) > 0 else 0
                print(f"  LONG 시뮬: {len(long_signals)}건, win {long_wr:.1f}%")
                print(f"  SHORT 시뮬: {len(short_signals)}건, win {short_wr:.1f}%")
                out['long_sim_wr'] = float(long_wr)
                out['short_sim_wr'] = float(short_wr)
    else:
        print("\n시뮬 진입 시그널 0건 — 모든 게이트가 차단 중 (시나리오 5 분포 확인)")
    return out


# ==============================================================================
# 메인
# ==============================================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv', required=True, help='Observer CSV 경로 또는 glob (예: "*.csv")')
    parser.add_argument('--out', default='Observer_Analysis_Report.json', help='결과 JSON 출력 경로')
    args = parser.parse_args()

    df = load_observer_csvs(args.csv)
    print(f"\n분석 대상: {len(df):,}봉")
    if 'time_local' in df.columns and len(df) > 0:
        print(f"기간: {df['time_local'].iloc[0]} ~ {df['time_local'].iloc[-1]}")

    report = {
        'analyzed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_bars': int(len(df)),
        'period': {
            'start': str(df['time_local'].iloc[0]) if 'time_local' in df.columns and len(df) > 0 else '',
            'end': str(df['time_local'].iloc[-1]) if 'time_local' in df.columns and len(df) > 0 else '',
        },
    }
    report['s1_regime_distribution'] = diag_s1_regime_distribution(df)
    report['s2_tbm_distribution'] = diag_s2_tbm_distribution(df)
    report['s3_features'] = diag_s3_features(df)
    report['s4_ob'] = diag_s4_ob(df)
    report['s5_block_gates'] = diag_s5_block_gates(df)
    report['s7_health'] = diag_s7_health(df)
    report['s8_subregime'] = diag_s8_subregime(df)
    report['s11_label_consistency'] = diag_s11_label_consistency(df)
    report['s12_simulated_signal'] = diag_s12_simulated_signal(df)

    # 저장
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n✓ 리포트 저장: {args.out}")


if __name__ == '__main__':
    main()
