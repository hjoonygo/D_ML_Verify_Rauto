# -*- coding: utf-8 -*-
"""
[파일명] analyze_sl_timeout_grid.py
코드길이: 약 350줄, 내부버전명: v1.0 (sl_timeout_grid_v1), 로직 축약/생략 없이 전체 출력

[목적]
  SL 거리 × timeout 그리드 분석 — 사용자 가설 정밀 검증
  - 118건 (uptrend long 44 + hivol_range long 74)에 대해
  - timeout 10개 × SL 7개 = 70 시나리오 매트릭스 분석
  - 자본 위험(lev 10 시 한 거래 최대 손실 ROE)도 같이 출력

[Grid 정의]
  timeout (분): 120, 240, 360, 480, 600, 720, 840, 960, 1080, 1200
                = 2H, 4H, 6H, 8H, 10H, 12H, 14H, 16H, 18H, 20H
  SL (bp): 100, 180, 240, 300, 400, 500, 800
           각각 lev10 시 ROE 최대 손실: -10%, -18%, -24%, -30%, -40%, -50%, -80%

[실행 환경 위치]
  실행 폴더: D:\\ML\\Verify\\Handover_v34_stage_3_2026-05-19\\
  Raw 1m봉 데이터: D:\\ML\\Verify\\Merged_Data.csv (부모 폴더)
  Trades csv: D:\\ML\\Verify\\Handover_v34_stage_3_2026-05-19\\outputs_stage_3\\trades_sl_max_180bp.csv
  결과 폴더:  D:\\ML\\Verify\\Handover_v34_stage_3_2026-05-19\\outputs_grid_analysis\\

[실행 방법]
  cd D:\\ML\\Verify\\Handover_v34_stage_3_2026-05-19
  python analyze_sl_timeout_grid.py

[예상 소요 시간]
  5~10분 (1m봉 1,578,240봉 로드 + 118건 path 추출 + 70 시나리오 시뮬)

[결과 파일 (outputs_grid_analysis/ 폴더)]
  grid_overall.csv          - 70 시나리오 전체 통계 (PF/win/net)
  grid_uptrend_long.csv     - uptrend long 44건만 그리드
  grid_hivol_range_long.csv - hivol_range long 74건만 그리드
  best_scenarios.csv        - PF >= 1.0 시나리오 정렬
  trade_paths_20h.csv       - 118건 거래별 20H path 데이터 (검증용)
  grid_analysis_log.txt     - 요약 로그

[결과 zip 만들기 (분석 완료 후)]
  outputs_grid_analysis 폴더 전체를 zip으로 압축
  zip명 예: grid_analysis_2026-05-19.zip

[가상 시뮬 가정]
  - SL 풀히트: timeout 시점 전에 min_pct가 -SL 거리 미만이면 즉시 청산 (-SL bp)
  - timeout: SL 미발동 시 timeout 시점 close 가격으로 청산
  - 비용: 왕복 16bp 수수료
  - step 발동 로직은 단순화 위해 무시 (실제 시뮬 시 step 발동 시 결과 더 좋을 수 있음)

[함수 In/Out]
  load_data() -> (df_trades, df_raw)
  extract_path_20h(df_raw, entry_t) -> Dict {min_pct_120/240/.../1200, price_pct_같음}
  simulate_grid(df, sl_bp, timeout_min) -> Dict {pf, win, net_sum, ...}
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
OUTPUT_DIR = os.path.join(WORK_DIR, "outputs_grid_analysis")
LOG_PATH = os.path.join(OUTPUT_DIR, "grid_analysis_log.txt")

# 그리드 정의
TIMEOUTS_MIN = [120, 240, 360, 480, 600, 720, 840, 960, 1080, 1200]
TIMEOUT_LABELS = ['2H', '4H', '6H', '8H', '10H', '12H', '14H', '16H', '18H', '20H']
SL_BPS = [100, 180, 240, 300, 400, 500, 800]
COST = 0.0016  # 16bp 왕복 수수료
LEV = 10  # 레버리지 (자본 위험 표시용)

log_lines = []
def log(msg):
    print(msg)
    log_lines.append(str(msg))


def load_data():
    log("\n[1/5] 데이터 로드")
    
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
    
    valid_exits = ['initial_sl','step1_sl','step2_sl','step3_sl',
                   'timeout_4h','timeout_step_active','reversal_2h']
    df_trades = df_trades[df_trades['exit_reason'].isin(valid_exits)].copy()
    log(f"    진입 거래: {len(df_trades)}건")
    
    mask = ((df_trades['regime']=='uptrend') & (df_trades['side']=='long')) | \
           ((df_trades['regime']=='hivol_range') & (df_trades['side']=='long'))
    df_target = df_trades[mask].copy().reset_index(drop=True)
    log(f"    분석 대상: {len(df_target)}건")
    log(f"      uptrend long: {(df_target['regime']=='uptrend').sum()}건")
    log(f"      hivol_range long: {(df_target['regime']=='hivol_range').sum()}건")
    
    return df_target, df_raw


def extract_path_20h(df_raw, entry_t):
    """20H + 60분 buffer = 1260분 가격 path 추출
    각 timeout 시점의 close 가격, 그 시점까지의 최저/최고 가격 기록
    """
    entry_t_pd = pd.Timestamp(entry_t)
    if entry_t_pd.tz is None:
        entry_t_pd = entry_t_pd.tz_localize('UTC')
    
    try:
        end_t = entry_t_pd + pd.Timedelta(minutes=1260)
        path = df_raw.loc[entry_t_pd:end_t]
    except KeyError:
        return None
    
    if len(path) < 120:
        return None
    
    entry_price = float(path.iloc[0]['open'])
    result = {'entry_price_actual': entry_price}
    
    # 각 timeout 시점 close 가격 + 그 시점까지의 최저/최고
    for h in TIMEOUTS_MIN:
        if len(path) > h:
            close_h = float(path.iloc[h]['close'])
            result[f'close_pct_{h}'] = (close_h - entry_price) / entry_price
            
            # 0~h 분까지의 최저/최고 (long 관점에서 min=손실, max=수익)
            p_sub = path.iloc[:h+1]
            result[f'min_pct_{h}'] = (float(p_sub['low'].min()) - entry_price) / entry_price
            result[f'max_pct_{h}'] = (float(p_sub['high'].max()) - entry_price) / entry_price
        else:
            result[f'close_pct_{h}'] = None
            result[f'min_pct_{h}'] = None
            result[f'max_pct_{h}'] = None
    
    return result


def simulate_grid_cell(df_with_path, sl_bp, timeout_min):
    """한 (SL, timeout) 조합 시뮬 — long 거래만 가정
    
    각 거래에 대해:
    - 0~timeout 분 내 min_pct < -SL/10000 이면 SL 풀히트, 손실 = -SL/10000
    - 아니면 timeout 시점 close 가격으로 청산
    - 비용 16bp 차감
    """
    sl_pct = sl_bp / 10000
    
    min_col = f'min_pct_{timeout_min}'
    close_col = f'close_pct_{timeout_min}'
    
    if min_col not in df_with_path.columns or close_col not in df_with_path.columns:
        return None
    
    df = df_with_path.dropna(subset=[min_col, close_col]).copy()
    if len(df) == 0:
        return None
    
    # SL 풀히트 여부
    sl_hit_mask = df[min_col] <= -sl_pct
    
    # net_return 계산
    df['new_price_roe'] = np.where(sl_hit_mask, -sl_pct, df[close_col])
    df['new_net'] = df['new_price_roe'] - COST
    
    nets = df['new_net'].values
    wins = nets[nets > 0]
    losses = nets[nets <= 0]
    
    pf = wins.sum() / abs(losses.sum()) if losses.sum() < 0 else float('inf')
    win_rate = len(wins) / len(df)
    
    return {
        'sl_bp': sl_bp,
        'timeout_min': timeout_min,
        'timeout_label': TIMEOUT_LABELS[TIMEOUTS_MIN.index(timeout_min)],
        'n': len(df),
        'pf': round(pf, 3) if pf != float('inf') else 'inf',
        'win_rate': round(win_rate, 3),
        'net_sum_pct': round(nets.sum() * 100, 2),
        'avg_bp': round(nets.mean() * 10000, 1),
        'sl_hit_count': int(sl_hit_mask.sum()),
        'sl_hit_rate': round(sl_hit_mask.sum() / len(df), 3),
        'lev10_max_loss_pct': round(sl_bp * LEV / 100, 1),  # lev10 한 거래 ROE 손실
    }


def make_grid_table(df_with_path, label):
    """주어진 거래 집합에 대해 SL × timeout 그리드 시뮬"""
    results = []
    for sl in SL_BPS:
        for t in TIMEOUTS_MIN:
            r = simulate_grid_cell(df_with_path, sl, t)
            if r is not None:
                r['scope'] = label
                results.append(r)
    return pd.DataFrame(results)


def main():
    t_start = time.time()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    log("=" * 80)
    log(f"[SL x Timeout Grid Analysis 시작] {pd.Timestamp.now()}")
    log("=" * 80)
    log(f"실행 폴더: {WORK_DIR}")
    log(f"Raw 1m봉:  {RAW_PATH}")
    log(f"Trades csv: {TRADES_PATH}")
    log(f"결과 폴더:  {OUTPUT_DIR}")
    log(f"\nGrid:")
    log(f"  timeout: {TIMEOUTS_MIN} 분 = {TIMEOUT_LABELS}")
    log(f"  SL: {SL_BPS} bp")
    log(f"  총 시나리오: {len(SL_BPS)} x {len(TIMEOUTS_MIN)} = {len(SL_BPS)*len(TIMEOUTS_MIN)}개")
    log(f"\n자본 위험 (lev {LEV}):")
    for sl in SL_BPS:
        log(f"  SL {sl}bp -> 한 거래 최대 ROE 손실 -{sl*LEV/100:.0f}%")
    
    df_target, df_raw = load_data()
    
    # path 추출
    log(f"\n[2/5] 거래별 20H path 추출")
    t_extract = time.time()
    paths = []
    for i, row in df_target.iterrows():
        p = extract_path_20h(df_raw, row['entry_t'])
        if p is None:
            continue
        record = {
            'entry_signal_idx_1m': row['entry_signal_idx_1m'],
            'entry_t': row['entry_t'],
            'regime': row['regime'],
            'side': row['side'],
            'exit_reason': row['exit_reason'],
            'atr_pct_at_entry': row['atr_pct_at_entry'],
            'multiplier_used': row['multiplier_used'],
            'net_return_orig': row['net_return'],
            'price_roe_orig': row['price_roe'],
        }
        record.update(p)
        paths.append(record)
        if (i+1) % 20 == 0:
            log(f"    {i+1}/{len(df_target)} 처리 중...")
    
    df_paths = pd.DataFrame(paths)
    log(f"  완료: {len(df_paths)}건 (소요 {time.time()-t_extract:.1f}초)")
    
    df_paths.to_csv(os.path.join(OUTPUT_DIR, "trade_paths_20h.csv"), index=False, encoding='utf-8-sig')
    log(f"  거래별 path 저장: trade_paths_20h.csv")
    
    # 그리드 시뮬 — 3가지 집합
    log(f"\n[3/5] 그리드 시뮬 (3가지 집합)")
    
    log(f"  (1) 전체 118건 (uptrend long + hivol_range long)")
    grid_overall = make_grid_table(df_paths, 'overall_118')
    grid_overall.to_csv(os.path.join(OUTPUT_DIR, "grid_overall.csv"), index=False, encoding='utf-8-sig')
    
    log(f"  (2) uptrend long 44건만")
    df_ul = df_paths[df_paths['regime']=='uptrend']
    grid_ul = make_grid_table(df_ul, 'uptrend_long')
    grid_ul.to_csv(os.path.join(OUTPUT_DIR, "grid_uptrend_long.csv"), index=False, encoding='utf-8-sig')
    
    log(f"  (3) hivol_range long 74건만")
    df_hl = df_paths[df_paths['regime']=='hivol_range']
    grid_hl = make_grid_table(df_hl, 'hivol_range_long')
    grid_hl.to_csv(os.path.join(OUTPUT_DIR, "grid_hivol_range_long.csv"), index=False, encoding='utf-8-sig')
    
    # PF 1.0+ 시나리오 정렬
    log(f"\n[4/5] PF >= 1.0 시나리오 정렬")
    all_grids = pd.concat([grid_overall, grid_ul, grid_hl], ignore_index=True)
    # 'inf' string도 처리
    all_grids['pf_num'] = pd.to_numeric(all_grids['pf'], errors='coerce')
    best = all_grids[all_grids['pf_num'] >= 1.0].sort_values('net_sum_pct', ascending=False)
    best.to_csv(os.path.join(OUTPUT_DIR, "best_scenarios.csv"), index=False, encoding='utf-8-sig')
    log(f"  PF >= 1.0 시나리오: {len(best)}개")
    
    # 요약 출력
    log(f"\n[5/5] 핵심 매트릭스 출력")
    log("=" * 80)
    
    log(f"\n[전체 118건 — PF 매트릭스 (SL행 x timeout열)]")
    pivot = grid_overall.pivot(index='sl_bp', columns='timeout_label', values='pf')
    pivot = pivot[TIMEOUT_LABELS]
    log(pivot.to_string())
    
    log(f"\n[전체 118건 — net_sum % 매트릭스]")
    pivot_net = grid_overall.pivot(index='sl_bp', columns='timeout_label', values='net_sum_pct')
    pivot_net = pivot_net[TIMEOUT_LABELS]
    log(pivot_net.to_string())
    
    log(f"\n[uptrend long 44건 — PF 매트릭스]")
    pivot_ul = grid_ul.pivot(index='sl_bp', columns='timeout_label', values='pf')
    pivot_ul = pivot_ul[TIMEOUT_LABELS]
    log(pivot_ul.to_string())
    
    log(f"\n[uptrend long 44건 — net_sum % 매트릭스]")
    pivot_ul_net = grid_ul.pivot(index='sl_bp', columns='timeout_label', values='net_sum_pct')
    pivot_ul_net = pivot_ul_net[TIMEOUT_LABELS]
    log(pivot_ul_net.to_string())
    
    log(f"\n[hivol_range long 74건 — PF 매트릭스]")
    pivot_hl = grid_hl.pivot(index='sl_bp', columns='timeout_label', values='pf')
    pivot_hl = pivot_hl[TIMEOUT_LABELS]
    log(pivot_hl.to_string())
    
    log(f"\n[hivol_range long 74건 — net_sum % 매트릭스]")
    pivot_hl_net = grid_hl.pivot(index='sl_bp', columns='timeout_label', values='net_sum_pct')
    pivot_hl_net = pivot_hl_net[TIMEOUT_LABELS]
    log(pivot_hl_net.to_string())
    
    # Top 10 best
    log(f"\n[Top 10 시나리오 (net_sum 기준)]")
    if len(best) > 0:
        cols = ['scope', 'sl_bp', 'timeout_label', 'n', 'pf', 'win_rate', 'net_sum_pct', 
                'sl_hit_rate', 'lev10_max_loss_pct']
        log(best.head(10)[cols].to_string(index=False))
    
    # 자본 위험 경고
    log(f"\n[자본 위험 요약]")
    log(f"  lev {LEV} 가정. SL 거리별 한 거래 최대 손실:")
    for sl in SL_BPS:
        log(f"    SL {sl}bp -> 한 거래 ROE 최대 -{sl*LEV/100:.0f}% 손실")
    log(f"  연속 풀히트 위험도 고려 필요")
    
    t_total = time.time() - t_start
    log(f"\n[총 소요: {t_total:.1f}초]")
    
    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_lines))
    
    log(f"\n[zip 만들기 안내]")
    log(f"  outputs_grid_analysis 폴더를 zip으로 압축:")
    log(f"  zip명 예: grid_analysis_2026-05-19.zip")


if __name__ == "__main__":
    main()
