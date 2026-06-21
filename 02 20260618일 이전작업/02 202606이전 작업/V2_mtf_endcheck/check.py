# -*- coding: utf-8 -*-
# [파일명] check.py  (범용 오염검사, V2 끝검증판 대응)
# 코드길이: 약 210줄, 내부버전명: check_v2, 로직 축약/생략 없이 전체 출력
#
# [목적] test.py 실행 직후 호출되어 (1)결과물 오염검사 8항목 (2)작업분석 txt 저장
#        (3)INDEX 한 줄 기록. 모든 출력은 하위폴더가 아니라 상위 D:\ML\verify\00WorkHstr\ 로.
#        사용자에게 화면 복붙을 요구하지 않는다 — 전부 파일로 남긴다.
#
# [8개 오염 시나리오]
#   1 결과파일 존재(크래시)        : V2_trades_*.csv + V2_summary.csv 존재?
#   2 이전 사이클 잔존 섞임         : 결과 CSV mtime 이 이번 실행시작 이후?
#   3 파일명 불일치                 : 고정 패턴 V2_trades_*.csv ?
#   4 엉뚱한 데이터                 : 입력 데이터 행수·기간·해시 기록(+상위폴더 파일인지)
#   5 거래 중복 기록               : (진입시간,구분,청산시간) 중복행 0?
#   6 거래 빔/깨짐(NaN/inf)         : 거래있는 config>0 & 순익 NaN/inf 0?
#   7 INDEX 이중기록               : 같은 zip명+stamp 이미 있나 확인 후 1줄 추가
#   8 출력 경로 오배치              : 결과 txt/INDEX 가 ..\00WorkHstr\ 로 가는지 검증
#
# [경로규칙] 이 파일은 D:\ML\verify\<zip명>\ 에서 실행. 출력은 ..\00WorkHstr\.
#
# [함수 In/Out]
#   sha8(path)            -> 파일 앞 1MB 해시 8자리
#   find_parent_data()    -> 상위 데이터 경로
#   run_checks(start_ts)  -> (checks: list[(이름,통과,메모)], analysis: dict)
#   write_outputs(...)    -> 00WorkHstr\(초단위).txt + INDEX 한 줄
# ==============================================================================

import os, sys, glob, time, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
ZIP_NAME = os.path.basename(HERE)                    # 하위폴더명 = zip명
HSTR = os.path.join(PARENT, "00WorkHstr")            # ★출력 폴더(상위)
INDEX = os.path.join(HSTR, "00WorkHstr_INDEX.txt")
TRADES_GLOB = "V2_trades_*.csv"
SUMMARY = "V2_summary.csv"
START_MARK = os.path.join(HERE, ".run_start")        # run.bat 시작시각(없으면 현재-1h)


def sha8(path):
    hh = hashlib.sha256()
    with open(path, 'rb') as f:
        hh.update(f.read(1 << 20))
    return hh.hexdigest()[:8]


def find_parent_data():
    for n in ["Merged_Data_with_Regime_Features.csv", "Merged_Data.csv"]:
        p = os.path.join(PARENT, n)
        if os.path.exists(p):
            return p
    return None


def run_checks(start_ts):
    checks = []
    analysis = {'zip': ZIP_NAME, 'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}

    trade_files = sorted(glob.glob(os.path.join(HERE, TRADES_GLOB)))
    summary_path = os.path.join(HERE, SUMMARY)

    # [1] 결과파일 존재
    ok1 = len(trade_files) > 0 and os.path.exists(summary_path)
    checks.append(("1.결과파일존재", ok1, f"trades {len(trade_files)}개, summary={'O' if os.path.exists(summary_path) else 'X'}"))

    # [2] 이전 사이클 잔존(mtime이 실행시작 이전이면 잔존)
    stale = [os.path.basename(f) for f in trade_files if os.path.getmtime(f) < start_ts]
    ok2 = (len(stale) == 0) and ok1
    checks.append(("2.잔존섞임없음", ok2, "stale=" + (",".join(stale) if stale else "없음")))

    # [3] 파일명 패턴
    bad = [os.path.basename(f) for f in trade_files if not os.path.basename(f).startswith("V2_trades_")]
    ok3 = (len(bad) == 0) and ok1
    checks.append(("3.파일명일치", ok3, "위반=" + (",".join(bad) if bad else "없음")))

    # [4] 데이터 행수/기간/해시 + 상위폴더인지
    data = find_parent_data()
    if data:
        try:
            dd = pd.read_csv(data, usecols=['timestamp'])
            analysis['data_path'] = data
            analysis['data_rows'] = len(dd)
            analysis['data_span'] = f"{dd['timestamp'].iloc[0]}~{dd['timestamp'].iloc[-1]}"
            analysis['data_hash'] = sha8(data)
            ok4 = os.path.dirname(data) == PARENT
            checks.append(("4.데이터정상(상위)", ok4, f"{analysis['data_rows']}행 hash={analysis['data_hash']}"))
        except Exception as e:
            checks.append(("4.데이터정상(상위)", False, f"읽기실패:{e}"))
    else:
        checks.append(("4.데이터정상(상위)", False, "상위폴더 데이터 없음"))

    # [5][6] 중복 + NaN/0건 (빈 config = 진입0 정상. 단 전부 비면 FAIL)
    dup_total = 0; nan_total = 0; nonempty = 0; per_cfg = []
    for f in trade_files:
        try:
            t = pd.read_csv(f)
        except Exception:
            per_cfg.append((os.path.basename(f), 0, 0.0, 0)); continue
        if len(t) == 0:
            per_cfg.append((os.path.basename(f), 0, 0.0, 0)); continue
        nonempty += 1
        key = ['진입시간', '구분', '청산시간']
        if all(k in t.columns for k in key):
            dup_total += int(t.duplicated(subset=key).sum())
        if '순수익' in t.columns:
            v = pd.to_numeric(t['순수익'], errors='coerce')
            nan_total += int((~np.isfinite(v)).sum())
            g = v.groupby(t['진입시간']).sum()
            net = g.values; finite = net[np.isfinite(net)]
            if len(finite) and (finite < 0).any():
                pf = round(finite[finite > 0].sum() / abs(finite[finite < 0].sum()), 3)
            else:
                pf = 9.99
            per_cfg.append((os.path.basename(f), int(len(g)), pf, int(round(finite.sum())) if len(finite) else 0))
    ok5 = (dup_total == 0)
    ok6 = (nonempty > 0) and (nan_total == 0) and ok1
    checks.append(("5.중복없음", ok5, f"중복행 {dup_total}"))
    checks.append(("6.빔/NaN없음", ok6, f"거래있는config {nonempty}/{len(trade_files)}, NaN={nan_total}"))
    analysis['per_config'] = per_cfg

    # [8] 출력경로 쓰기 가능?
    try:
        os.makedirs(HSTR, exist_ok=True)
        testp = os.path.join(HSTR, ".w"); open(testp, 'w').close(); os.remove(testp)
        ok8 = True
    except Exception:
        ok8 = False
    checks.append(("8.출력경로(..\\00WorkHstr)", ok8, HSTR))
    return checks, analysis


def write_outputs(checks, analysis):
    os.makedirs(HSTR, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    txt_path = os.path.join(HSTR, f"{stamp}.txt")

    # [7] INDEX 이중기록 확인
    dup_in_index = False
    if os.path.exists(INDEX):
        with open(INDEX, encoding='utf-8') as f:
            if any((ZIP_NAME in line and stamp in line) for line in f):
                dup_in_index = True
    checks.append(("7.INDEX 이중기록없음", not dup_in_index, "이미있음" if dup_in_index else "신규"))
    all_pass = all(ok for _, ok, _ in checks)

    lines = []
    lines.append(f"[작업분석] {analysis['zip']}  {analysis['time']}")
    lines.append("=" * 60)
    lines.append("[오염검사 8+1]")
    for name, ok, memo in checks:
        lines.append(f"  {'PASS' if ok else 'FAIL'} | {name} | {memo}")
    lines.append(f"  => 종합: {'ALL PASS' if all_pass else '★FAIL 있음 — 결과 신뢰 불가'}")
    lines.append("")
    lines.append("[입력 데이터]")
    lines.append(f"  {analysis.get('data_path','?')}")
    lines.append(f"  행수 {analysis.get('data_rows','?')} | 기간 {analysis.get('data_span','?')} | 해시 {analysis.get('data_hash','?')}")
    lines.append("")
    lines.append("[config별 성과]")
    for name, nentry, pf, net in analysis.get('per_config', []):
        lines.append(f"  {name}: 진입 {nentry} | PF {pf} | 순익 {net:,}$")
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))

    best = max(analysis.get('per_config', [('', 0, 0, 0)]), key=lambda x: x[3]) if analysis.get('per_config') else ('', 0, 0, 0)
    write_header = not os.path.exists(INDEX)
    with open(INDEX, 'a', encoding='utf-8') as f:
        if write_header:
            f.write("# Rauto 작업이력 INDEX | 시각|작업|분석txt|테스트py|결과|데이터해시|best|check\n")
        if all_pass:
            f.write(f"{analysis['time']} | {ZIP_NAME} | 분석:{stamp}.txt | 테스트:test.py | "
                    f"결과:V2_summary.csv | 데이터해시:{analysis.get('data_hash','?')} | "
                    f"best:{best[0]}(PF{best[2]},{best[3]:,}$) | check:PASS\n")
        else:
            f.write(f"{analysis['time']} | {ZIP_NAME} | [FAIL — 분석:{stamp}.txt 확인, 정식기록 보류] | check:FAIL\n")
    return txt_path, all_pass


def main():
    start_ts = (os.path.getmtime(START_MARK) if os.path.exists(START_MARK) else time.time() - 3600)
    checks, analysis = run_checks(start_ts)
    txt_path, all_pass = write_outputs(checks, analysis)
    print(f"[check] 분석결과 저장: {txt_path}")
    print(f"[check] INDEX 갱신: {INDEX}")
    print(f"[check] 종합판정: {'ALL PASS' if all_pass else '★FAIL — txt 확인'}")


if __name__ == "__main__":
    main()
