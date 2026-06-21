# [test_LiqLimitDecision.py]
# 코드길이: 215줄, 내부버전명: LiqLimit_v1.0, 로직 축약/생략 없이 전체 출력
# 목적: 격리튕김 손실한도(진입수량 x 레버리지) 8 시나리오를 stg4 원장으로 검증.
#       수익금(선물 잔고, 복리) 기준 + MDD -15% 절대선 + 폭락 방어력 동시 평가.
# ---------------------------------------------------------------------------
# [사용 파일]
#   IN : ..\06Prj_Ch7_stg4_GreedShortGuard_v2_best55fixed\stg4_best_ledger.csv
#        (상위 D:\ML\verify 의 stg4 챔피언 원장, greed55_smult0 264거래, v2 best55fixed)
#        컬럼 = entry_t, exit_t, ym, year, side, R, reason, regime, fng
#   OUT: .\result_8scenarios.csv  (8 시나리오 잔고/MDD/청산수/청산거리/단일손실)
#        .\result_crashstress.csv (각 시나리오 폭락 -20/-30/-50% 주입 시 MDD)
#        .\result_kelly.csv       (Kelly 최적 EXPOSURE + 성장곡선)
#        .\result_meta.json       (실행 메타: 거래수, 데이터 해시, 시각)
# ---------------------------------------------------------------------------
# [함수 목록 / In-Out]
#   load_ledger(path)            IN 원장경로 / OUT 정렬된 DataFrame, R배열, 데이터해시
#   liq_distance(lev)            IN 레버리지 / OUT 청산거리(음수, 1/L-MMR-FEE)
#   sim_scenario(R,entry,lev)    IN R배열·진입%·레버 / OUT (EXP,최종잔고,MDD%,청산수,청산거리%)
#   kelly_optimal(R)             IN R배열 / OUT (Kelly최적f, fs배열, 로그성장배열)
#   sim_crash(R,entry,lev,pk,cr) IN R·진입%·레버·peak위치·폭락크기 / OUT 폭락주입후 MDD%
#   main()                       IN 없음 / OUT 4개 결과파일 디스크 기록 + 콘솔요약
# ---------------------------------------------------------------------------
# [전역 변수 / 의미]
#   SCRIPT_DIR : 이 스크립트가 있는 하위폴더 절대경로
#   DATA_PATH  : 원장 경로 (상위 D:\ML\verify\stg4_best_ledger.csv)
#   START      : 최초 자본금 $10,000 (복리 기준)
#   MMR        : 유지증거금률 0.5% (보수 가정, BTCUSDT Tier 명목구간별 변동 가능)
#   FEE        : 청산수수료 1.25% (Binance Futures Liquidation Clearance Fee)
#   SCENARIOS  : 8 시나리오 (이름, 진입%, 레버리지, 그룹) — 그룹 A=EXP0.94고정·레버변화 / B=13배고정·EXP변화
# ---------------------------------------------------------------------------

import os
import sys
import json
import hashlib
import datetime
import numpy as np
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 원장 실제 위치: D:\ML\verify\06Prj_Ch7_stg4_GreedShortGuard_v2_best55fixed\stg4_best_ledger.csv
# (greed55_smult0 챔피언 264거래, v2 best55fixed). 하위폴더에서 상위 verify로 올라가 그 폴더를 가리킨다.
DATA_PATH = os.path.join(SCRIPT_DIR, '..', '06Prj_Ch7_stg4_GreedShortGuard_v2_best55fixed', 'stg4_best_ledger.csv')
START = 10000.0
MMR = 0.005
FEE = 0.0125

# 8 시나리오: (이름, 진입수량비율, 레버리지, 그룹)
# 그룹 A = EXPOSURE 0.94 고정, 레버리지만 변화 (어느 레버리지가 폭락방어 최적인가)
# 그룹 B = 레버리지 13배 고정, EXPOSURE 변화 (진입수량별 수익 vs MDD)
SCENARIOS = [
    ('S1', 0.0940, 10, 'A'),
    ('S2', 0.0723, 13, 'A'),
    ('S3', 0.0627, 15, 'A'),
    ('S4', 0.0470, 20, 'A'),
    ('S5', 0.0700, 13, 'B'),
    ('S6', 0.0750, 13, 'B'),
    ('S7', 0.0650, 13, 'B'),
    ('S8', 0.0800, 13, 'B'),
]


def load_ledger(path):
    """IN 원장경로 / OUT (DataFrame, R(np.float64 배열), 데이터 sha256 해시)"""
    if not os.path.exists(path):
        sys.stderr.write('[ERROR] 원장 파일 없음: %s\n' % path)
        sys.stderr.write('        D:\\ML\\verify\\stg4_best_ledger.csv 위치를 확인하세요.\n')
        sys.exit(1)
    with open(path, 'rb') as f:
        raw = f.read()
    data_hash = hashlib.sha256(raw).hexdigest()
    df = pd.read_csv(path, encoding='utf-8-sig')
    if 'R' not in df.columns or 'exit_t' not in df.columns:
        sys.stderr.write('[ERROR] 원장 컬럼 비정상 (R, exit_t 필요): %s\n' % list(df.columns))
        sys.exit(1)
    df = df.sort_values('exit_t').reset_index(drop=True)
    R = df['R'].astype(float).values
    return df, R, data_hash


def liq_distance(lev):
    """IN 레버리지 / OUT 청산거리(음수). 1/L - MMR - FEE."""
    return -(1.0 / lev - MMR - FEE)


def sim_scenario(R, entry_pct, lev):
    """IN R배열·진입%·레버 / OUT (EXP, 최종잔고, MDD%, 청산수, 청산거리%).
    격리튕김 ON: 거래수익률 R이 청산거리 이하면 단일손실=-진입%로 하드락(테일컷),
                그렇지 않으면 R*EXPOSURE 적용. 복리 누적은 numpy 벡터화."""
    exposure = entry_pct * lev
    liq = liq_distance(lev)
    tail = -entry_pct
    dW = np.where(R <= liq, tail, R * exposure)
    cap_curve = START * np.cumprod(1.0 + dW)
    running_peak = np.maximum.accumulate(cap_curve)
    mdd = ((cap_curve - running_peak) / running_peak).min()
    n_liq = int((R <= liq).sum())
    return exposure, float(cap_curve[-1]), mdd * 100.0, n_liq, liq * 100.0


def kelly_optimal(R):
    """IN R배열 / OUT (Kelly최적f, fs배열, 로그성장배열). 로그성장률 최대화하는 f."""
    fs = np.arange(0.05, 3.01, 0.05)
    growth = np.array([np.mean(np.log1p(f * R)) for f in fs])
    kelly_f = float(fs[int(np.argmax(growth))])
    return kelly_f, fs, growth


def sim_crash(R, entry_pct, lev, peak_idx, crash):
    """IN R·진입%·레버·peak위치·폭락크기 / OUT 폭락 주입 후 MDD%.
    자본곡선 최고점(peak_idx) 직후에 crash(예 -0.30) 거래 1건을 합성 주입한 스트레스 테스트.
    격리튕김 ON이므로 crash<=청산거리면 -진입%로 잠긴다."""
    exposure = entry_pct * lev
    liq = liq_distance(lev)
    tail = -entry_pct
    R2 = np.concatenate([R[:peak_idx + 1], np.array([crash]), R[peak_idx + 1:]])
    dW = np.where(R2 <= liq, tail, R2 * exposure)
    cap_curve = START * np.cumprod(1.0 + dW)
    running_peak = np.maximum.accumulate(cap_curve)
    mdd = ((cap_curve - running_peak) / running_peak).min()
    return mdd * 100.0


def main():
    """IN 없음 / OUT 4개 결과파일 디스크 기록 + 콘솔 요약."""
    df, R, data_hash = load_ledger(DATA_PATH)
    n_trades = len(R)

    # 자본곡선 peak 위치 (폭락 주입 최악 타이밍용, EXPOSURE 0.94 기준)
    base_curve = START * np.cumprod(1.0 + R * 0.94)
    peak_idx = int(np.argmax(base_curve))

    # --- 1) 8 시나리오 ---
    rows = []
    for name, entry, lev, grp in SCENARIOS:
        exp, end_cap, mdd, n_liq, liq = sim_scenario(R, entry, lev)
        rows.append({
            'scenario': name, 'group': grp,
            'entry_pct': round(entry * 100, 2), 'leverage': lev,
            'exposure': round(exp, 4),
            'single_loss_pct': round(-entry * 100, 2),
            'liq_distance_pct': round(liq, 2),
            'end_balance': round(end_cap, 2),
            'mdd_pct': round(mdd, 2),
            'n_liquidation': n_liq,
            'within_limit': 'Y' if mdd >= -15.0 else 'N',
        })
    res = pd.DataFrame(rows)
    res.to_csv(os.path.join(SCRIPT_DIR, 'result_8scenarios.csv'), index=False, encoding='utf-8-sig')

    # --- 2) 폭락 주입 스트레스 ---
    crash_rows = []
    for name, entry, lev, grp in SCENARIOS:
        row = {'scenario': name, 'entry_pct': round(entry * 100, 2), 'leverage': lev}
        for cr in (-0.20, -0.30, -0.50):
            row['crash_%d_mdd' % int(abs(cr) * 100)] = round(sim_crash(R, entry, lev, peak_idx, cr), 2)
        crash_rows.append(row)
    crash_df = pd.DataFrame(crash_rows)
    crash_df.to_csv(os.path.join(SCRIPT_DIR, 'result_crashstress.csv'), index=False, encoding='utf-8-sig')

    # --- 3) Kelly ---
    kelly_f, fs, growth = kelly_optimal(R)
    kelly_df = pd.DataFrame({'exposure_f': np.round(fs, 2), 'log_growth_x1000': np.round(growth * 1000, 4)})
    kelly_df.to_csv(os.path.join(SCRIPT_DIR, 'result_kelly.csv'), index=False, encoding='utf-8-sig')

    # --- 4) 메타 ---
    meta = {
        'version': 'LiqLimit_v1.0',
        'run_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'data_path': os.path.abspath(DATA_PATH),
        'data_sha256': data_hash,
        'n_trades': n_trades,
        'start_capital': START,
        'MMR': MMR, 'FEE': FEE,
        'kelly_optimal': kelly_f, 'half_kelly': round(kelly_f / 2, 3),
        'peak_idx': peak_idx,
    }
    with open(os.path.join(SCRIPT_DIR, 'result_meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # --- 콘솔 요약 (참고용, 정식 기록은 check.py가 파일로) ---
    print('=' * 78)
    print('[test_LiqLimitDecision.py] LiqLimit_v1.0  거래수=%d  데이터해시=%s' % (n_trades, data_hash[:12]))
    print('=' * 78)
    print('Kelly 최적 EXPOSURE = %.2f, Half = %.2f (현재 0.975는 Kelly의 %.0f%%)'
          % (kelly_f, kelly_f / 2, 0.975 / kelly_f * 100))
    print('-' * 78)
    print('%-4s %-3s %7s %7s %9s %9s %12s %9s %5s %6s'
          % ('#', 'grp', 'entry%', 'lev', 'EXP', 'liqDist', 'balance', 'MDD%', 'liq', 'limit'))
    for _, r in res.iterrows():
        print('%-4s %-3s %6.2f%% %6dx %9.3f %8.2f%% %12s %8.2f%% %5d %6s'
              % (r['scenario'], r['group'], r['entry_pct'], r['leverage'], r['exposure'],
                 r['liq_distance_pct'], '$%s' % format(int(r['end_balance']), ','),
                 r['mdd_pct'], r['n_liquidation'], r['within_limit']))
    print('-' * 78)
    within = res[res['within_limit'] == 'Y']
    if len(within):
        best = within.loc[within['end_balance'].idxmax()]
        print('MDD -15%% 안 최고 수익: %s (%.2f%%x%d, EXP %.3f) 잔고 $%s, MDD %.2f%%'
              % (best['scenario'], best['entry_pct'], best['leverage'], best['exposure'],
                 format(int(best['end_balance']), ','), best['mdd_pct']))
    print('결과 4파일 기록 완료. check.py 실행하세요.')


if __name__ == '__main__':
    main()
