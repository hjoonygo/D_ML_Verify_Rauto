# ==============================================================================
# [파일명] tbm_ob_consistency_V80k_Verify_3.py
# [코드길이] 약 280줄 / 내부버전 V80k_Verify_3_S15b / 로직축약·생략 없이 전체 출력
# [모듈 종류] 분석 도구 (Observer CSV → TBM 라벨 vs OB 정합성 측정)
# ==============================================================================
# [목적]
#   V80k_Verify_2 47h 가동 분석 결과 발견된 본질 문제 정량 측정 도구:
#   "TBM 학습 라벨 (R:R 3:1, 0.30/0.10%) vs Observer OB 기반 SL/TP (RR 2.5~5x, 좁은 임계)"
#   두 평가 함수의 정합성 자동 측정. 신규 학습 후 회귀 테스트로 활용.
#
# [📥 IN]
#   --observer-dir <path>  : Observer CSV 폴더 (RautoV80k_Observer_*.csv 다수)
#   --price-csv <path>     : (선택) 가격 시계열 CSV (Observer 부족 시 fallback)
#   --output <path>        : 출력 JSON 경로
#   --horizon <int>        : 사후 horizon (default 30)
#
# [📤 OUT - JSON]
#   {
#     'data_summary': {봉수, 기간, 가격 변화 등},
#     'pass_analysis': [
#       {
#         'pass_ts', 'sim_action', 'sim_sl_pct', 'sim_tp_pct',
#         'observer_outcome': WIN/LOSS/NO_PROFIT,
#         'tbm_standard_label': 0/1/2,
#         'pnl_30bar_pct',
#         'is_stop_hunt': bool   ← 휩쏘 패턴 자동 검출
#       }, ...
#     ],
#     'gate_distribution': {...},
#     'post_label_distribution': {LONG_WIN/SHORT_WIN/NO_PROFIT 비율},
#     'consistency_metrics': {
#       'observer_win_rate': float,
#       'tbm_standard_win_rate': float,
#       'mismatch_rate': float,    ← 두 평가가 다른 결론을 낸 비율
#       'stop_hunt_rate': float    ← PASS 중 휩쏘 패턴 비율
#     },
#     'verdict': 'A/B/C 가설 판정'
#   }
#
# [출처]
#   분석 로직: /home/claude/analyze_47h.py + /home/claude/pass_post_sim.py 통합
#   휩쏘 검출: PASS #3 사례 패턴 일반화 (SL 깨고 즉시 회복 후 진짜 방향)
# ==============================================================================
import os
import sys
import json
import argparse
import numpy as np
import pandas as pd
from glob import glob

# Stop hunt 검출 임계
STOP_HUNT_RECOVERY_BARS = 5      # SL 깨진 후 N봉 내 회복하면 휩쏘로 판정
STOP_HUNT_RECOVERY_PCT = 0.20    # 회복 후 진입 방향으로 N% 이상 진행

TBM_TP_PCT = 0.30
TBM_SL_PCT = 0.10
HORIZON = 30


def load_observer_data(observer_dir):
    """Observer CSV 다수를 통합 로드."""
    bot_files = sorted(glob(os.path.join(observer_dir, "RautoV80k_Observer_Bot_*.csv")))
    obs_files = sorted(glob(os.path.join(observer_dir, "RautoV80k_Observer_observer_*.csv")))
    
    bot_df = None
    if bot_files:
        bot_df = pd.concat([pd.read_csv(f) for f in bot_files], ignore_index=True)
        bot_df.columns = [c.lstrip('\ufeff') for c in bot_df.columns]
        bot_df['bar_ts_dt'] = pd.to_datetime(bot_df['bar_ts'], unit='ms', utc=True)
        bot_df = bot_df.sort_values('bar_ts_dt').reset_index(drop=True)
    
    obs_df = None
    if obs_files:
        obs_df = pd.concat([pd.read_csv(f) for f in obs_files], ignore_index=True)
        obs_df.columns = [c.lstrip('\ufeff') for c in obs_df.columns]
        obs_df['bar_ts_dt'] = pd.to_datetime(obs_df['bar_ts'], unit='ms', utc=True)
        obs_df = obs_df.sort_values('bar_ts_dt').reset_index(drop=True)
    
    return bot_df, obs_df


def detect_stop_hunt(future_window, entry_price, sim_action, sim_sl):
    """휩쏘 패턴 자동 검출.
    
    조건: 진입 후 N봉 내 sim_sl 깨짐 + 그 후 STOP_HUNT_RECOVERY_BARS 내 진입가 회복
          + horizon 끝에 진입 방향으로 STOP_HUNT_RECOVERY_PCT% 이상 진행
    """
    if len(future_window) < HORIZON:
        return False
    
    prices = future_window['price'].values
    
    # 1) sim_sl 깨진 시점
    sl_break_idx = None
    for j, fp in enumerate(prices):
        if sim_action == 'OPEN_LONG':
            if fp <= sim_sl:
                sl_break_idx = j
                break
        else:  # OPEN_SHORT
            if fp >= sim_sl:
                sl_break_idx = j
                break
    
    if sl_break_idx is None:
        return False  # SL 안 깨짐 → 휩쏘 아님
    
    # 2) STOP_HUNT_RECOVERY_BARS 내 회복?
    recovery_start = sl_break_idx + 1
    recovery_end = min(sl_break_idx + 1 + STOP_HUNT_RECOVERY_BARS, len(prices))
    if recovery_end <= recovery_start:
        return False
    
    recovered = False
    for j in range(recovery_start, recovery_end):
        if sim_action == 'OPEN_LONG':
            if prices[j] >= entry_price:
                recovered = True
                break
        else:
            if prices[j] <= entry_price:
                recovered = True
                break
    
    if not recovered:
        return False
    
    # 3) 끝에 진입 방향으로 STOP_HUNT_RECOVERY_PCT% 이상 진행?
    final_price = prices[-1]
    if sim_action == 'OPEN_LONG':
        final_pnl = (final_price - entry_price) / entry_price * 100
    else:
        final_pnl = (entry_price - final_price) / entry_price * 100
    
    return final_pnl >= STOP_HUNT_RECOVERY_PCT


def analyze_pass_signals(bot_df):
    """PASS 봉의 사후 결과 + 휩쏘 검출."""
    pass_bars = bot_df[bot_df['block_gate'] == 'PASS'].copy()
    results = []
    
    for idx, row in pass_bars.iterrows():
        pass_idx = bot_df[bot_df['bar_ts'] == row['bar_ts']].index[0]
        end_idx = min(pass_idx + HORIZON + 1, len(bot_df))
        future_window = bot_df.iloc[pass_idx+1:end_idx]
        
        if len(future_window) == 0:
            continue
        
        entry = float(row['price'])
        sim_action = row['sim_action']
        sim_sl = float(row['sim_sl_price'])
        sim_tp = float(row['sim_tp_price'])
        
        # Observer SL/TP 시뮬
        sim_outcome = 'NO_PROFIT'
        sim_hit_idx = None
        for j, (i, fr) in enumerate(future_window.iterrows()):
            fp = fr['price']
            if sim_action == 'OPEN_LONG':
                if fp >= sim_tp:
                    sim_outcome = 'WIN'; sim_hit_idx = j+1; break
                if fp <= sim_sl:
                    sim_outcome = 'LOSS'; sim_hit_idx = j+1; break
            else:
                if fp <= sim_tp:
                    sim_outcome = 'WIN'; sim_hit_idx = j+1; break
                if fp >= sim_sl:
                    sim_outcome = 'LOSS'; sim_hit_idx = j+1; break
        
        # TBM 표준 라벨 (0.10/0.30%)
        if sim_action == 'OPEN_LONG':
            tbm_tp_p = entry * (1 + TBM_TP_PCT/100)
            tbm_sl_p = entry * (1 - TBM_SL_PCT/100)
        else:
            tbm_tp_p = entry * (1 - TBM_TP_PCT/100)
            tbm_sl_p = entry * (1 + TBM_SL_PCT/100)
        
        tbm_outcome = 'NO_PROFIT'
        for j, (i, fr) in enumerate(future_window.iterrows()):
            fp = fr['price']
            if sim_action == 'OPEN_LONG':
                if fp >= tbm_tp_p:
                    tbm_outcome = 'WIN'; break
                if fp <= tbm_sl_p:
                    tbm_outcome = 'LOSS'; break
            else:
                if fp <= tbm_tp_p:
                    tbm_outcome = 'WIN'; break
                if fp >= tbm_sl_p:
                    tbm_outcome = 'LOSS'; break
        
        # 30봉 후 PnL (raw, 레버리지 미포함)
        if len(future_window) >= HORIZON:
            final_price = future_window.iloc[HORIZON-1]['price']
        else:
            final_price = future_window.iloc[-1]['price']
        if sim_action == 'OPEN_LONG':
            pnl_pct = (final_price - entry) / entry * 100
        else:
            pnl_pct = (entry - final_price) / entry * 100
        
        # ★ 휩쏘 검출
        is_sh = detect_stop_hunt(future_window, entry, sim_action, sim_sl)
        
        results.append({
            'pass_ts': str(row['bar_ts_dt']),
            'sim_action': sim_action,
            'entry_price': entry,
            'sim_sl_pct': float(row.get('sl_raw_pct_candidate', 0)),
            'sim_tp_pct': float(row.get('tp_raw_pct_candidate', 0)),
            'observer_outcome': sim_outcome,
            'observer_hit_bar': sim_hit_idx,
            'tbm_standard_label': tbm_outcome,
            'pnl_30bar_pct': float(pnl_pct),
            'is_stop_hunt': bool(is_sh),
            'tbm_proba': {
                'LONG': float(row.get('tbm_proba_LONG', 0)),
                'SHORT': float(row.get('tbm_proba_SHORT', 0)),
                'NO_PROFIT': float(row.get('tbm_proba_NO_PROFIT', 0)),
            },
            'regime_output': str(row.get('regime_output', '')),
        })
    
    return results


def compute_consistency_metrics(pass_results):
    """Observer vs TBM 평가 정합성 지표."""
    if not pass_results:
        return {'n': 0}
    
    n = len(pass_results)
    obs_win = sum(1 for r in pass_results if r['observer_outcome'] == 'WIN')
    tbm_win = sum(1 for r in pass_results if r['tbm_standard_label'] == 'WIN')
    mismatch = sum(1 for r in pass_results
                   if r['observer_outcome'] != r['tbm_standard_label'])
    sh = sum(1 for r in pass_results if r['is_stop_hunt'])
    
    return {
        'n_pass': n,
        'observer_win_rate': obs_win / n,
        'tbm_standard_win_rate': tbm_win / n,
        'mismatch_count': mismatch,
        'mismatch_rate': mismatch / n,
        'stop_hunt_count': sh,
        'stop_hunt_rate': sh / n,
    }


def get_post_label_dist(obs_df):
    """observer.csv의 사후 라벨 분포 (R_Observer 폴백 데이터)."""
    if obs_df is None or 'label_class' not in obs_df.columns:
        return None
    valid = obs_df['label_class'].dropna()
    if len(valid) == 0:
        return None
    
    dist = valid.value_counts().to_dict()
    n = len(valid)
    return {
        'n_valid': n,
        'distribution': {k: int(v) for k, v in dist.items()},
        'pct': {k: float(v/n*100) for k, v in dist.items()},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--observer-dir', required=True, help='Observer CSV 폴더')
    parser.add_argument('--output', default='V80k_Verify_3_S15b_consistency.json')
    args = parser.parse_args()
    
    print("=" * 78)
    print("V80k_Verify_3_S15b — TBM/OB 정합성 분석")
    print("=" * 78)
    
    bot_df, obs_df = load_observer_data(args.observer_dir)
    
    if bot_df is None or len(bot_df) == 0:
        print("⚠ Bot Observer 데이터 없음")
        return 1
    
    print(f"\nBot 봉수: {len(bot_df):,}")
    print(f"기간: {bot_df['bar_ts_dt'].iloc[0]} ~ {bot_df['bar_ts_dt'].iloc[-1]}")
    
    # PASS 분석
    pass_results = analyze_pass_signals(bot_df)
    print(f"PASS 봉수: {len(pass_results)}")
    
    consistency = compute_consistency_metrics(pass_results)
    print(f"\n정합성 지표:")
    if consistency.get('n_pass', 0) > 0:
        print(f"  Observer WIN rate: {consistency['observer_win_rate']*100:.1f}%")
        print(f"  TBM 표준 WIN rate: {consistency['tbm_standard_win_rate']*100:.1f}%")
        print(f"  평가 미스매치 비율: {consistency['mismatch_rate']*100:.1f}%")
        print(f"  ★ 휩쏘 (stop hunt) 비율: {consistency['stop_hunt_rate']*100:.1f}%")
    
    # 사후 라벨 분포
    post_dist = get_post_label_dist(obs_df)
    print(f"\n사후 라벨 분포 (observer.csv):")
    if post_dist:
        print(f"  유효 봉: {post_dist['n_valid']:,}")
        for lbl, pct in post_dist['pct'].items():
            print(f"    {lbl:12s}: {post_dist['distribution'][lbl]:>5,} ({pct:5.2f}%)")
    
    # 가설 판정
    if post_dist and post_dist['n_valid'] > 100:
        np_pct = post_dist['pct'].get('NO_PROFIT', 0)
        if np_pct >= 90:
            verdict = f"가설 A 강력 지지 (사후 NO_PROFIT {np_pct:.1f}%)"
        elif np_pct >= 80:
            verdict = f"가설 A 지지 (사후 NO_PROFIT {np_pct:.1f}%)"
        elif np_pct >= 70:
            verdict = f"혼재 (사후 NO_PROFIT {np_pct:.1f}%)"
        else:
            verdict = f"⚠ 가설 B Distribution Shift 의심 (사후 NO_PROFIT {np_pct:.1f}%)"
    else:
        verdict = "사후 라벨 데이터 부족"
    print(f"\n판정: {verdict}")
    
    # 게이트 분포
    gate_dist = bot_df['block_gate'].value_counts().to_dict()
    
    output = {
        'analysis_version': 'V80k_Verify_3_S15b',
        'data_summary': {
            'n_bars': int(len(bot_df)),
            'duration_hours': float((bot_df['bar_ts_dt'].iloc[-1] - bot_df['bar_ts_dt'].iloc[0]).total_seconds()/3600),
            'price_start': float(bot_df['price'].iloc[0]),
            'price_end': float(bot_df['price'].iloc[-1]),
            'price_change_pct': float((bot_df['price'].iloc[-1] - bot_df['price'].iloc[0]) / bot_df['price'].iloc[0] * 100),
        },
        'gate_distribution': {str(k): int(v) for k, v in gate_dist.items()},
        'pass_analysis': pass_results,
        'consistency_metrics': consistency,
        'post_label_distribution': post_dist,
        'verdict': verdict,
    }
    
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n[저장] {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
