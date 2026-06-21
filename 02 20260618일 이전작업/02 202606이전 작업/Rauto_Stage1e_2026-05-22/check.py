# -*- coding: utf-8 -*-
# [파일명] check.py  (Stage1 동봉, 범용)
# 코드길이: 약 230줄, 내부버전명: check_v1, 로직 축약/생략 없이 전체 출력
#
# [목적] 테스트코드.py 실행 직후 호출되어 (1)결과물 오염검사 (2)작업분석 txt 저장
#        (3)INDEX 한 줄 기록. 모든 출력은 하위폴더가 아니라 상위 D:\ML\verify\00WorkHstr\ 로.
#        사용자에게 화면 복붙을 요구하지 않는다 — 전부 파일로 남긴다.
#
# [8개 오염 시나리오 — 사용자 승인]
#   1 결과파일 없음(크래시)        : 기대 출력 CSV 존재?
#   2 이전 사이클 잔존 섞임         : 결과 CSV mtime 이 이번 실행시작 이후?
#   3 파일명 불일치(오타/버전)      : 고정 패턴 S1e_trades_*.csv / S1e_summary.csv ?
#   4 엉뚱한 데이터 사용            : 입력 데이터 행수·기간·해시 기록(+상위폴더 파일인지)
#   5 거래 중복 기록               : (진입시간,구분,청산시간) 중복행 0?
#   6 거래 빔/깨짐(NaN/inf/0건)     : 행수>0 & 순익 NaN/inf 0?
#   7 INDEX 이중기록/누락           : 같은 zip명 이미 있나 확인 후 1줄 추가
#   8 출력 경로 오배치              : 결과 txt/INDEX 가 ..\00WorkHstr\ 로 가는지 검증
#
# [경로규칙] 이 파일은 D:\ML\verify\<zip명>\ 에서 실행. 출력은 ..\00WorkHstr\.
#
# [함수 In/Out]
#   sha8(path)            -> 파일 앞부분 해시 8자리
#   find_parent_data()    -> 상위 데이터 경로(테스트코드와 동일 규칙)
#   run_checks(start_ts)  -> (checks: list[(이름,통과,메모)], analysis: dict)
#   write_outputs(...)    -> 00WorkHstr\(분단위).txt + INDEX 한 줄
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
TRADES_GLOB = "S1e_trades_*.csv"
SUMMARY = "S1e_summary.csv"
START_MARK = os.path.join(HERE, ".run_start")        # run.bat 시작시각 기록(없으면 현재-1h)


def sha8(path):
    hh = hashlib.sha256()
    with open(path, 'rb') as f:
        hh.update(f.read(1 << 20))   # 앞 1MB
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

    # [2] 이전 사이클 잔존(mtime이 실행시작 이후?)
    stale = [os.path.basename(f) for f in trade_files if os.path.getmtime(f) < start_ts]
    ok2 = (len(stale) == 0) and ok1
    checks.append(("2.잔존섞임없음", ok2, "stale=" + (",".join(stale) if stale else "없음")))

    # [3] 파일명 패턴
    bad = [os.path.basename(f) for f in trade_files if not os.path.basename(f).startswith("S1e_trades_")]
    ok3 = (len(bad) == 0) and ok1
    checks.append(("3.파일명일치", ok3, "위반=" + (",".join(bad) if bad else "없음")))

    # [4] 데이터 행수/기간/해시
    data = find_parent_data()
    if data:
        try:
            dd = pd.read_csv(data, usecols=['timestamp'])
            analysis['data_path'] = data
            analysis['data_rows'] = len(dd)
            analysis['data_span'] = f"{dd['timestamp'].iloc[0]}~{dd['timestamp'].iloc[-1]}"
            analysis['data_hash'] = sha8(data)
            ok4 = os.path.dirname(data) == PARENT     # 상위폴더 데이터인지
            checks.append(("4.데이터정상(상위)", ok4, f"{analysis['data_rows']}행 hash={analysis['data_hash']}"))
        except Exception as e:
            checks.append(("4.데이터정상(상위)", False, f"읽기실패:{e}")); ok4 = False
    else:
        checks.append(("4.데이터정상(상위)", False, "상위폴더 데이터 없음")); ok4 = False

    # [5][6] 거래 중복 + NaN/0건  (빈 파일 = 그 config 진입0, 오염 아님. 단 전부 비면 FAIL)
    dup_total = 0; empty_files = []; nan_total = 0; per_cfg = []; nonempty = 0
    for f in trade_files:
        try:
            t = pd.read_csv(f)
        except Exception:
            empty_files.append(os.path.basename(f)); continue
        if len(t) == 0:
            # 헤더만 있고 거래 0 = 그 config 진입 0건(정상 가능). 집계만 0으로.
            per_cfg.append((os.path.basename(f), 0, 0.0, 0)); continue
        nonempty += 1
        key = ['진입시간', '구분', '청산시간']
        if all(k in t.columns for k in key):
            dup_total += int(t.duplicated(subset=key).sum())
        if '순수익' in t.columns:
            v = pd.to_numeric(t['순수익'], errors='coerce')
            nan_total += int((~np.isfinite(v)).sum())
        # 진입당 집계 (inf-safe: 검사용이므로 inf가 있어도 죽지 않게)
        if '순수익' in t.columns and '진입시간' in t.columns:
            vv = pd.to_numeric(t['순수익'], errors='coerce')
            g = vv.groupby(t['진입시간']).sum()
            net = g.values
            finite = net[np.isfinite(net)]
            if len(finite) and (finite < 0).any():
                pf = round(finite[finite > 0].sum() / abs(finite[finite < 0].sum()), 3)
            else:
                pf = 9.99
            net_sum = int(round(finite.sum())) if len(finite) else 0
            per_cfg.append((os.path.basename(f), int(len(g)), pf, net_sum))
    ok5 = (dup_total == 0)
    ok6 = (nonempty > 0) and (nan_total == 0) and ok1   # 최소 1개 config는 거래 있어야
    checks.append(("5.중복없음", ok5, f"중복행 {dup_total}"))
    checks.append(("6.빔/NaN없음", ok6, f"거래있는config {nonempty}/{len(trade_files)}, NaN={nan_total}"))
    analysis['per_config'] = per_cfg

    # [8] 출력경로 — HSTR 폴더 쓰기 가능?
    try:
        os.makedirs(HSTR, exist_ok=True)
        testp = os.path.join(HSTR, ".w")
        open(testp, 'w').close(); os.remove(testp)
        ok8 = True
    except Exception as e:
        ok8 = False
    checks.append(("8.출력경로(..\\00WorkHstr)", ok8, HSTR))

    # [7]은 write 단계에서 INDEX 중복확인하며 처리
    return checks, analysis


def write_outputs(checks, analysis):
    os.makedirs(HSTR, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')   # 초단위(덮어쓰기 방지)
    txt_path = os.path.join(HSTR, f"{stamp}.txt")

    # [7] INDEX 이중기록 확인 (zip명 + 분석txt stamp 기준)
    dup_in_index = False
    if os.path.exists(INDEX):
        with open(INDEX, encoding='utf-8') as f:
            if any((ZIP_NAME in line and stamp in line) for line in f):
                dup_in_index = True
    checks.append(("7.INDEX 이중기록없음", not dup_in_index, "이미있음" if dup_in_index else "신규"))
    all_pass = all(ok for _, ok, _ in checks)

    # 분석 txt 저장(★전량 파일 — 검사 FAIL이어도 진단 위해 항상 남김)
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

    # INDEX 한 줄 추가 — ★ALL PASS일 때만 정식 기록. FAIL이면 이력 오염 방지 위해 [FAIL]표식만.
    best = max(analysis.get('per_config', [('', 0, 0, 0)]), key=lambda x: x[3]) if analysis.get('per_config') else ('', 0, 0, 0)
    write_header = not os.path.exists(INDEX)
    with open(INDEX, 'a', encoding='utf-8') as f:
        if write_header:
            f.write("# Rauto 작업이력 INDEX | 시각|작업|분석txt|테스트py|결과|데이터해시|best|check\n")
        if all_pass:
            f.write(f"{analysis['time']} | {ZIP_NAME} | 분석:{stamp}.txt | "
                    f"테스트:test.py | 결과:S1e_summary.csv | "
                    f"데이터해시:{analysis.get('data_hash','?')} | "
                    f"best:{best[0]}(PF{best[2]},{best[3]:,}$) | check:PASS\n")
        else:
            f.write(f"{analysis['time']} | {ZIP_NAME} | [FAIL — 분석:{stamp}.txt 확인, 정식기록 보류] | check:FAIL\n")

    return txt_path, all_pass


def main():
    start_ts = (os.path.getmtime(START_MARK) if os.path.exists(START_MARK)
                else time.time() - 3600)
    checks, analysis = run_checks(start_ts)
    txt_path, all_pass = write_outputs(checks, analysis)
    # 콘솔엔 '어디에 저장됐는지'만 (복붙 요구 아님)
    print(f"[check] 분석결과 저장: {txt_path}")
    print(f"[check] INDEX 갱신: {INDEX}")
    print(f"[check] 종합판정: {'ALL PASS' if all_pass else '★FAIL — txt 확인'}")


if __name__ == "__main__":
    main()
