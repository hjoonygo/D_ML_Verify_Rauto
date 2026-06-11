# [check_LiqLimitDecision.py]
# 코드길이: 175줄, 내부버전명: LiqCheck_v1.0, 로직 축약/생략 없이 전체 출력
# 목적: test_LiqLimitDecision.py 결과물의 (1)오염검사 (2)분석txt 저장 (3)INDEX 한 줄 기록.
#       결과는 전량 파일로만 출력하며 사용자에게 복붙을 요청하지 않는다.
# ---------------------------------------------------------------------------
# [사용 파일]
#   IN : .\result_8scenarios.csv, .\result_crashstress.csv, .\result_kelly.csv, .\result_meta.json
#        (test 가 만든 결과 4종, 같은 하위폴더)
#   OUT: ..\00WorkHstr\<YYYYMMDD_HHMM>.txt          (이번 작업 분석 보고서)
#        ..\00WorkHstr\00WorkHstr_INDEX.txt         (기존 파일에 한 줄 append)
# ---------------------------------------------------------------------------
# [함수 목록 / In-Out]
#   sha256_of(path)        IN 파일경로 / OUT 해당 파일 sha256 (없으면 'MISSING')
#   check_contamination()  IN 없음 / OUT (ok:bool, 검사항목 dict 리스트) — 파일명/해시/중복누락
#   write_analysis(meta,...) IN 검사결과·결과DF들 / OUT 분석txt 경로
#   append_index(meta,...) IN 메타·최적시나리오 / OUT INDEX 갱신 (한 줄 추가)
#   main()                 IN 없음 / OUT 위 파일들 디스크 기록 + 콘솔 통과/실패만
# ---------------------------------------------------------------------------
# [전역 변수 / 의미]
#   SCRIPT_DIR   : 하위폴더 절대경로
#   HSTR_DIR     : ..\00WorkHstr (= D:\ML\verify\00WorkHstr)
#   INDEX_PATH   : 00WorkHstr_INDEX.txt 경로
#   WORK_NAME    : 이번 작업명 (zip/폴더명과 동일)
#   EXPECTED     : 하위폴더에 있어야 할 파일명 목록 (오염/누락 검사 기준)
# ---------------------------------------------------------------------------

import os
import sys
import json
import hashlib
import datetime
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HSTR_DIR = os.path.join(SCRIPT_DIR, '..', '00WorkHstr')
INDEX_PATH = os.path.join(HSTR_DIR, '00WorkHstr_INDEX.txt')
WORK_NAME = '07Prj_Ch1_Slippage_stg3_LiqLimitDecision'

EXPECTED = [
    'test_LiqLimitDecision.py', 'check_LiqLimitDecision.py', 'run.bat',
    'result_8scenarios.csv', 'result_crashstress.csv', 'result_kelly.csv', 'result_meta.json',
]


def sha256_of(path):
    """IN 파일경로 / OUT sha256 16자리 (없으면 'MISSING')"""
    if not os.path.exists(path):
        return 'MISSING'
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def check_contamination():
    """IN 없음 / OUT (ok:bool, checks:list[dict]). 파일명 일치·해시·중복/누락 검사."""
    checks = []
    ok = True

    # (1) 파일명 일치 / 누락 탐지
    for fn in EXPECTED:
        p = os.path.join(SCRIPT_DIR, fn)
        exists = os.path.exists(p)
        if not exists:
            ok = False
        checks.append({'item': 'file_exists:%s' % fn,
                       'result': 'OK' if exists else 'MISSING',
                       'hash': sha256_of(p)[:16]})

    # (2) 결과 CSV 무결성 (읽기 가능 + 행 수)
    try:
        s = pd.read_csv(os.path.join(SCRIPT_DIR, 'result_8scenarios.csv'), encoding='utf-8-sig')
        n_scen = len(s)
        dup = s['scenario'].duplicated().any()
        # (3) 중복/누락: 8 시나리오 S1~S8 정확히 있는지
        expected_set = {'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8'}
        got_set = set(s['scenario'].tolist())
        missing = expected_set - got_set
        extra = got_set - expected_set
        if n_scen != 8 or dup or missing or extra:
            ok = False
        checks.append({'item': 'scenario_count', 'result': 'OK(8)' if n_scen == 8 else 'BAD(%d)' % n_scen, 'hash': ''})
        checks.append({'item': 'scenario_duplicate', 'result': 'NONE' if not dup else 'FOUND', 'hash': ''})
        checks.append({'item': 'scenario_missing', 'result': 'NONE' if not missing else str(sorted(missing)), 'hash': ''})
    except Exception as e:
        ok = False
        checks.append({'item': 'result_csv_read', 'result': 'ERROR:%s' % str(e)[:40], 'hash': ''})

    return ok, checks


def write_analysis(ok, checks, meta, s_df, c_df, k_df):
    """IN 검사결과·메타·결과DF들 / OUT 분석txt 경로. 분단위 시간명으로 저장."""
    os.makedirs(HSTR_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M')
    out_path = os.path.join(HSTR_DIR, '%s.txt' % stamp)

    within = s_df[s_df['within_limit'] == 'Y']
    best = within.loc[within['end_balance'].idxmax()] if len(within) else None

    lines = []
    lines.append('=' * 70)
    lines.append('작업: %s' % WORK_NAME)
    lines.append('버전: %s   실행: %s' % (meta.get('version', '?'), meta.get('run_time', '?')))
    lines.append('데이터: %s' % meta.get('data_path', '?'))
    lines.append('데이터 sha256: %s' % meta.get('data_sha256', '?'))
    lines.append('거래수: %d   최초자본: $%s (복리)' % (meta.get('n_trades', 0), format(int(meta.get('start_capital', 0)), ',')))
    lines.append('MMR=%.4f  청산수수료=%.4f' % (meta.get('MMR', 0), meta.get('FEE', 0)))
    lines.append('=' * 70)
    lines.append('')
    lines.append('[오염검사] 종합: %s' % ('PASS' if ok else 'FAIL'))
    for c in checks:
        lines.append('  - %-28s %-12s %s' % (c['item'], c['result'], c['hash']))
    lines.append('')
    lines.append('[Kelly] 최적 EXPOSURE=%.2f, Half=%.2f (현재 0.975는 Kelly의 %.0f%%)'
                 % (meta.get('kelly_optimal', 0), meta.get('half_kelly', 0),
                    0.975 / meta.get('kelly_optimal', 1) * 100 if meta.get('kelly_optimal') else 0))
    lines.append('')
    lines.append('[8 시나리오] (격리튕김 ON, 잔고=복리, MDD=누적자본곡선)')
    lines.append('%-4s %-3s %7s %5s %8s %9s %9s %12s %8s %4s %5s'
                 % ('#', 'grp', 'entry%', 'lev', 'EXP', 'single%', 'liqDist', 'balance', 'MDD%', 'liq', 'lim'))
    for _, r in s_df.iterrows():
        lines.append('%-4s %-3s %6.2f%% %4dx %8.3f %8.2f%% %8.2f%% %12s %7.2f%% %4d %5s'
                     % (r['scenario'], r['group'], r['entry_pct'], r['leverage'], r['exposure'],
                        r['single_loss_pct'], r['liq_distance_pct'],
                        '$%s' % format(int(r['end_balance']), ','), r['mdd_pct'],
                        r['n_liquidation'], r['within_limit']))
    lines.append('')
    lines.append('[폭락 주입 스트레스] (자본 peak 직후 단일 폭락 주입 시 MDD%)')
    lines.append(c_df.to_string(index=False))
    lines.append('')
    if best is not None:
        lines.append('[권장] MDD -15%% 안 최고 수익 시나리오 = %s' % best['scenario'])
        lines.append('  진입 %.2f%% x %d배 = EXPOSURE %.3f, 단일손실 %.2f%%, 청산거리 %.2f%%'
                     % (best['entry_pct'], best['leverage'], best['exposure'],
                        best['single_loss_pct'], best['liq_distance_pct']))
        lines.append('  잔고 $%s, MDD %.2f%%, 청산 %d건'
                     % (format(int(best['end_balance']), ','), best['mdd_pct'], best['n_liquidation']))
    else:
        lines.append('[권장] MDD -15%% 안 통과 시나리오 없음 — 진입수량/레버리지 추가 하향 필요')
    lines.append('')
    lines.append('[주의] 폭락 주입은 "봇이 그 타이밍에 물렸다는 가정" 하의 스트레스 테스트.')
    lines.append('       실제 stg4 봇은 2025-10-11 폭락을 회피했음(원장 R 최악 -7.4%).')
    lines.append('=' * 70)

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return out_path


def append_index(ok, meta, s_df, analysis_name):
    """IN 검사결과·메타·시나리오DF·분석파일명 / OUT INDEX 한 줄 append."""
    os.makedirs(HSTR_DIR, exist_ok=True)
    within = s_df[s_df['within_limit'] == 'Y']
    best = within.loc[within['end_balance'].idxmax()] if len(within) else None
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

    if best is not None:
        summary = 'best=%s(%.2f%%x%dx EXP%.3f) bal=$%s MDD%.2f%% liq=%d' % (
            best['scenario'], best['entry_pct'], best['leverage'], best['exposure'],
            format(int(best['end_balance']), ','), best['mdd_pct'], best['n_liquidation'])
    else:
        summary = 'no scenario within MDD -15%'

    line = '%s | %s | LiqLimit 8scenario | %s | check=%s | report=%s\n' % (
        stamp, WORK_NAME, summary, 'PASS' if ok else 'FAIL', analysis_name)

    # 기존 INDEX 없으면 헤더 생성
    if not os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, 'w', encoding='utf-8') as f:
            f.write('# 00WorkHstr_INDEX — 작업 이력 (한 줄 = 한 작업)\n')
    with open(INDEX_PATH, 'a', encoding='utf-8') as f:
        f.write(line)


def main():
    """IN 없음 / OUT 오염검사·분석txt·INDEX 디스크 기록 + 콘솔에 PASS/FAIL만."""
    # test 가 결과를 안 만들었으면(원장 경로 오류 등) 여기서 깔끔히 안내하고 종료
    need = ['result_8scenarios.csv', 'result_crashstress.csv', 'result_kelly.csv', 'result_meta.json']
    missing = [fn for fn in need if not os.path.exists(os.path.join(SCRIPT_DIR, fn))]
    if missing:
        sys.stderr.write('[check] 결과 파일이 없습니다: %s\n' % ', '.join(missing))
        sys.stderr.write('[check] test_LiqLimitDecision.py 가 먼저 정상 실행돼야 합니다.\n')
        sys.stderr.write('[check] 원장 경로를 확인하세요:\n')
        sys.stderr.write('        D:\\ML\\verify\\06Prj_Ch7_stg4_GreedShortGuard_v2_best55fixed\\stg4_best_ledger.csv\n')
        sys.exit(1)

    ok, checks = check_contamination()
    try:
        with open(os.path.join(SCRIPT_DIR, 'result_meta.json'), 'r', encoding='utf-8') as f:
            meta = json.load(f)
    except Exception:
        meta = {}
    s_df = pd.read_csv(os.path.join(SCRIPT_DIR, 'result_8scenarios.csv'), encoding='utf-8-sig')
    c_df = pd.read_csv(os.path.join(SCRIPT_DIR, 'result_crashstress.csv'), encoding='utf-8-sig')
    k_df = pd.read_csv(os.path.join(SCRIPT_DIR, 'result_kelly.csv'), encoding='utf-8-sig')

    analysis_path = write_analysis(ok, checks, meta, s_df, c_df, k_df)
    append_index(ok, meta, s_df, os.path.basename(analysis_path))

    print('[check_LiqLimitDecision.py] 오염검사 %s' % ('PASS' if ok else 'FAIL'))
    print('  분석 보고서: %s' % analysis_path)
    print('  INDEX 갱신 : %s' % INDEX_PATH)


if __name__ == '__main__':
    main()
