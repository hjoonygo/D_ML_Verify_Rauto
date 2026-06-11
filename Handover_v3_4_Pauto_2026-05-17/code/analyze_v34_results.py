"""
[파일명] analyze_v34_results.py
코드길이: 약 200줄, 내부버전 v3.4-pauto
목적: measure_pf_v34_pauto.py의 결과 csv를 분석하여 알파 후보 정리

사용법:
  python analyze_v34_results.py [outputs_v34_pauto 폴더 경로]
  인자 없으면 ./outputs_v34_pauto 자동 검색

In: all_scenarios_summary_v34.csv
Out: 알파 후보 보고서 (콘솔 + .txt)
"""
import os
import sys
import pandas as pd
import numpy as np


def analyze(output_dir: str):
    summary_path = os.path.join(output_dir, 'all_scenarios_summary_v34.csv')
    if not os.path.exists(summary_path):
        print(f"[ERROR] 파일 없음: {summary_path}")
        sys.exit(1)
    
    df = pd.read_csv(summary_path)
    
    print(f"\n{'='*78}")
    print(f"Pauto v3.4 측정 결과 분석")
    print(f"{'='*78}")
    print(f"전체 행수: {len(df)} (시나리오 × 4 장세 + 1 overall)")
    
    # === 1) 전체 시나리오 ===
    df_overall = df[df['regime'] == 'overall']
    print(f"\n[전체 시나리오] {len(df_overall)}개")
    print(f"  PF 통계: min={df_overall['pf'].min():.3f}, "
          f"median={df_overall['pf'].median():.3f}, "
          f"max={df_overall['pf'].max():.3f}")
    print(f"  net_return_sum 통계: min={df_overall['net_return_sum'].min():.3f}, "
          f"median={df_overall['net_return_sum'].median():.3f}, "
          f"max={df_overall['net_return_sum'].max():.3f}")
    print(f"  n_valid 통계: min={df_overall['n_valid'].min()}, "
          f"median={df_overall['n_valid'].median()}, "
          f"max={df_overall['n_valid'].max()}")
    
    # === 2) 알파 후보 (ADR-W3 통과) ===
    alphas = df_overall[df_overall['adr_w3_passed']]
    print(f"\n[ADR-W3 통과 시나리오] {len(alphas)}건")
    if len(alphas) > 0:
        print(f"  Lev/SL/TPr/H 분포:")
        cols = ['lev', 'sl_acct', 'tp_ratio', 'holding_bars', 'pf', 'win_rate',
                'net_return_sum', 'n_valid']
        cols_exist = [c for c in cols if c in alphas.columns]
        print(alphas[cols_exist].sort_values('pf', ascending=False).head(20).to_string(index=False))
    else:
        print(f"  ⚠️ ADR-W3 통과 시나리오 없음 — PautoV75 진입 로직의 OOS 알파 약함")
    
    # === 3) 4 장세별 분석 ===
    print(f"\n[4 장세별 상위 PF]")
    for r in ['uptrend', 'downtrend', 'hivol_range', 'lovol_range']:
        df_r = df[df['regime'] == r]
        if len(df_r) > 0:
            top = df_r.nlargest(3, 'pf')[['lev','sl_acct','tp_ratio','holding_bars','pf','win_rate','net_return_sum','n_valid']]
            print(f"\n  [{r}] {len(df_r)}건")
            print(top.to_string(index=False))
    
    # === 4) PautoV75 IS 결과와 비교 ===
    print(f"\n{'='*78}")
    print(f"PautoV75 IS 결과 (참고):")
    print(f"  4.5mo 기간, +58.4% 수익, Max DD -13%, RR 2.87, PF 1.73")
    print(f"  월 환산 +13.07%/월")
    print(f"\nv3.4 결합 측정 (OOS 12mo) 결과:")
    if len(alphas) > 0:
        best = alphas.nlargest(1, 'pf').iloc[0]
        print(f"  최고 시나리오 PF: {best['pf']:.3f}")
        print(f"  net_return_sum: {best['net_return_sum']:.3f} (자본 누적 수익률)")
        print(f"  거래수: {best['n_valid']}")
        print(f"  IS PF 1.73 대비: {'★ 알파 유지' if best['pf'] >= 1.3 else '✗ 알파 감소'}")
    else:
        print(f"  최고 PF: {df_overall['pf'].max():.3f}")
        print(f"  ✗ ADR-W3 임계 미달 — PautoV75 IS 알파가 OOS에서 *유지 안 됨*")
        print(f"     점프 ⓟ-9 (학습=백테스트) 우려가 *실측 확인됨*")
    
    # === 5) 저장 ===
    out_path = os.path.join(output_dir, 'v34_analysis_report.txt')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write("Pauto v3.4 측정 결과 분석\n")
        f.write(f"전체: {len(df_overall)} 시나리오\n")
        f.write(f"ADR-W3 통과: {len(alphas)}\n")
        f.write(f"최대 PF: {df_overall['pf'].max():.3f}\n")
        f.write(f"평균 PF: {df_overall['pf'].mean():.3f}\n")
        if len(alphas) > 0:
            f.write(f"\n알파 후보:\n")
            f.write(alphas[cols_exist].sort_values('pf', ascending=False).head(20).to_string(index=False))
    print(f"\n[저장] {out_path}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        analyze(sys.argv[1])
    else:
        # 자동 검색
        for cand in ['./outputs_v34_pauto', 'outputs_v34_pauto']:
            if os.path.exists(cand):
                analyze(cand)
                break
        else:
            print("사용법: python analyze_v34_results.py <outputs_v34_pauto 경로>")
            sys.exit(1)
