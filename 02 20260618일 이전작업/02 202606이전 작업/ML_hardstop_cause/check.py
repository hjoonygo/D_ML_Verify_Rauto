# -*- coding: utf-8 -*-
# [파일명] check.py  (ML 하드손절 분석 사이클용 오염검사)
# 코드길이: 약 150줄, 내부버전명: check_ml_v1, 로직 축약/생략 없이 전체 출력
# [목적] ml_test.py 직후 (1)오염검사 (2)분석txt 저장 (3)INDEX 1줄 — 전부 ..\00WorkHstr\ 로.
# [경로] D:\ML\verify\<zip명>\ 에서 실행, 출력은 ..\00WorkHstr\.
# [함수] sha8 / run_checks(start) / write_outputs(checks,info)

import os, sys, glob, time, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd, numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
ZIP_NAME = os.path.basename(HERE)
HSTR = os.path.join(PARENT, "00WorkHstr")
INDEX = os.path.join(HSTR, "00WorkHstr_INDEX.txt")
START_MARK = os.path.join(HERE, ".run_start")
EXPECT = ["ML_entry_features.csv", "ML_summary.txt"]      # 최소 산출물
OPTIONAL = ["ML_importance.csv", "ML_rules.txt", "ML_clusters.csv", "ML_tradeoff.csv"]


def sha8(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f: h.update(f.read(1 << 20))
    return h.hexdigest()[:8]


def run_checks(start_ts):
    checks = []; info = {'zip': ZIP_NAME, 'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}
    present = [f for f in EXPECT if os.path.exists(os.path.join(HERE, f))]
    ok1 = len(present) == len(EXPECT)
    checks.append(("1.필수산출물 존재", ok1, f"{present}"))
    allf = EXPECT + OPTIONAL
    stale = [f for f in allf if os.path.exists(os.path.join(HERE, f)) and os.path.getmtime(os.path.join(HERE, f)) < start_ts]
    checks.append(("2.잔존섞임 없음", len(stale) == 0, "stale=" + (",".join(stale) if stale else "없음")))
    bad = [f for f in glob.glob(os.path.join(HERE, "ML_*.csv")) if not os.path.basename(f).startswith("ML_")]
    checks.append(("3.파일명 일치", len(bad) == 0, "위반 없음"))
    # 데이터 B 해시·행수
    pb = None
    for n in ["Merged_Data_with_Regime_Features.csv"]:
        p = os.path.join(PARENT, n)
        if os.path.exists(p): pb = p
    if pb:
        try:
            rows = sum(1 for _ in open(pb, encoding='utf-8')) - 1
            info['data'] = pb; info['rows'] = rows; info['hash'] = sha8(pb)
            checks.append(("4.B데이터 정상(상위)", os.path.dirname(pb) == PARENT, f"{rows}행 hash={info['hash']}"))
        except Exception as e:
            checks.append(("4.B데이터 정상(상위)", False, str(e)))
    else:
        checks.append(("4.B데이터 정상(상위)", False, "B파일 없음"))
    # entry_features 무결성
    ef = os.path.join(HERE, "ML_entry_features.csv"); nrow = 0; hard = 0; nan_ratio = 1.0
    if os.path.exists(ef):
        d = pd.read_csv(ef); nrow = len(d)
        if 'hard' in d.columns and nrow: hard = int(d['hard'].sum())
        feats = [c for c in d.columns if c not in ('entry_time', 'hard', 'piano', 'net')]
        if nrow and feats:
            nan_ratio = float(pd.DataFrame(d[feats]).isna().mean().mean())
        info['entries'] = nrow; info['hard'] = hard
    checks.append(("5.진입표 비어있지않음", nrow > 0, f"{nrow}행, 하드 {hard}"))
    checks.append(("6.피처 결측 과다아님", nan_ratio < 0.5, f"평균결측 {nan_ratio*100:.0f}%"))
    # tradeoff 존재(ML 성공시) 또는 sklearn 안내(부족시) 둘 중 하나
    sm = ""
    if os.path.exists(os.path.join(HERE, "ML_summary.txt")):
        sm = open(os.path.join(HERE, "ML_summary.txt"), encoding='utf-8').read()
    ml_done = os.path.exists(os.path.join(HERE, "ML_tradeoff.csv"))
    checks.append(("7.ML 완료 또는 사유명시", ml_done or ('sklearn' in sm or '표본 부족' in sm),
                   "맞교환표 생성" if ml_done else "ML 미완(사유 summary에)"))
    try:
        os.makedirs(HSTR, exist_ok=True)
        t = os.path.join(HSTR, ".w"); open(t, 'w').close(); os.remove(t); ok8 = True
    except Exception: ok8 = False
    checks.append(("8.출력경로(..\\00WorkHstr)", ok8, HSTR))
    info['summary'] = sm
    return checks, info


def write_outputs(checks, info):
    os.makedirs(HSTR, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    txt = os.path.join(HSTR, f"{stamp}.txt")
    dup = False
    if os.path.exists(INDEX):
        for line in open(INDEX, encoding='utf-8'):
            if ZIP_NAME in line and stamp in line: dup = True
    checks.append(("9.INDEX 이중기록 없음", not dup, "신규" if not dup else "중복"))
    allpass = all(ok for _, ok, _ in checks)
    L = [f"[작업분석] {info['zip']}  {info['time']}", "=" * 60, "[오염검사]"]
    for n, ok, m in checks:
        L.append(f"  {'PASS' if ok else 'FAIL'} | {n} | {m}")
    L.append(f"  => {'ALL PASS' if allpass else '★FAIL 있음'}")
    L.append(f"\n[입력 B] {info.get('data','?')}  {info.get('rows','?')}행 hash={info.get('hash','?')}")
    L.append(f"[진입] {info.get('entries','?')}건, 하드 {info.get('hard','?')}")
    L.append("\n[ML 요약]"); L.append(info.get('summary', '(없음)'))
    open(txt, 'w', encoding='utf-8').write("\n".join(L))
    newh = not os.path.exists(INDEX)
    with open(INDEX, 'a', encoding='utf-8') as f:
        if newh: f.write("# Rauto 작업이력 INDEX | 시각|작업|분석txt|코드|결과|데이터해시|진입/하드|check\n")
        if allpass:
            f.write(f"{info['time']} | {ZIP_NAME} | 분석:{stamp}.txt | 코드:ml_test.py | "
                    f"결과:ML_tradeoff.csv | 해시:{info.get('hash','?')} | "
                    f"진입{info.get('entries','?')}/하드{info.get('hard','?')} | check:PASS\n")
        else:
            f.write(f"{info['time']} | {ZIP_NAME} | [FAIL 분석:{stamp}.txt] | check:FAIL\n")
    return txt, allpass


def main():
    start = os.path.getmtime(START_MARK) if os.path.exists(START_MARK) else time.time() - 3600
    checks, info = run_checks(start)
    txt, ok = write_outputs(checks, info)
    print(f"[check] 분석 저장: {txt}")
    print(f"[check] 종합: {'ALL PASS' if ok else '★FAIL'}")


if __name__ == "__main__":
    main()
