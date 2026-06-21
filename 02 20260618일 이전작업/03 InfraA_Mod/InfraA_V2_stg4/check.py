# -*- coding: utf-8 -*-
# [FILE] check.py  (InfraA_V2_stg4 - contamination 8-check + separability verdict + INDEX)
# CODE LENGTH: approx 185 lines | INTERNAL VER: check_sepdiag_v1 | full output, no omission
#
# [PURPOSE] test.py 직후. (1)오염검사 8항목 (2)분석txt(진입전 지문 있나 판정) (3)INDEX 1줄.
#   출력 -> 상위 D:\ML\verify\00WorkHstr\ . 전량 파일.
#
# [8 SCENARIOS]
#   1 결과파일존재 : sep_features / sep_summary ?
#   2 잔존섞임없음 : mtime > .run_start ?
#   3 파일명일치   : sep_*.csv 허용패턴만?
#   4 데이터정상   : 상위데이터 행수/기간/해시 +36mo경고
#   5 중복없음     : sep_features 진입시간 중복 0?
#   6 빔/NaN없음   : features 행>0 & 라벨 NaN 0?
#   7 INDEX이중기록: zip+stamp 중복차단
#   8 출력경로     : ..\00WorkHstr ?
# ==============================================================================

import os, sys, glob, time, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
ZIP_NAME = os.path.basename(HERE)
HSTR = os.path.join(PARENT, "00WorkHstr")
INDEX = os.path.join(HSTR, "00WorkHstr_INDEX.txt")
FEATURES = "sep_features.csv"; SUMMARY = "sep_summary.csv"
EXPECTED = [FEATURES, SUMMARY]
START_MARK = os.path.join(HERE, ".run_start")


def sha8(path):
    hh = hashlib.sha256()
    with open(path, 'rb') as f:
        hh.update(f.read(1 << 20))
    return hh.hexdigest()[:8]


def find_parent_data():
    p = os.path.join(PARENT, "Merged_Data_with_Regime_Features.csv")
    return p if os.path.exists(p) else None


def run_checks(start_ts):
    checks = []; analysis = {'zip': ZIP_NAME, 'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}
    paths = {n: os.path.join(HERE, n) for n in EXPECTED}

    ok1 = all(os.path.exists(p) for p in paths.values())
    checks.append(("1.결과파일존재", ok1, ", ".join(f"{n.replace('.csv','')}={'O' if os.path.exists(p) else 'X'}" for n, p in paths.items())))

    stale = [n for n, p in paths.items() if os.path.exists(p) and os.path.getmtime(p) < start_ts]
    ok2 = (len(stale) == 0) and ok1
    checks.append(("2.잔존섞임없음", ok2, "stale=" + (",".join(stale) if stale else "없음")))

    found = [os.path.basename(f) for f in glob.glob(os.path.join(HERE, "sep_*.csv"))]
    bad = [f for f in found if f not in EXPECTED]
    ok3 = (len(bad) == 0) and ok1
    checks.append(("3.파일명일치", ok3, "위반=" + (",".join(bad) if bad else "없음")))

    data = find_parent_data()
    if data:
        try:
            dd = pd.read_csv(data, usecols=['timestamp'])
            span = (pd.to_datetime(dd['timestamp'].iloc[-1]) - pd.to_datetime(dd['timestamp'].iloc[0])).days
            analysis.update(data_rows=len(dd), data_hash=sha8(data), span_days=span, data_path=data)
            ok4 = (os.path.dirname(data) == PARENT)
            warn = "" if span >= 900 else f" ★{span}일(36mo미만)"
            checks.append(("4.데이터정상(36mo)", ok4, f"{len(dd)}행 {span}일 hash={analysis['data_hash']}{warn}"))
        except Exception as e:
            checks.append(("4.데이터정상(36mo)", False, f"읽기실패:{e}"))
    else:
        checks.append(("4.데이터정상(36mo)", False, "상위폴더 데이터 없음"))

    dup = 0; nrows = 0; nan = 0
    if os.path.exists(paths[FEATURES]):
        try:
            ff = pd.read_csv(paths[FEATURES]); nrows = len(ff)
            if '진입시간' in ff.columns:
                dup = int(ff.duplicated(subset=['진입시간']).sum())
            if '라벨' in ff.columns:
                nan += int(ff['라벨'].isna().sum())
            analysis['n_dis'] = int((ff['라벨'] == 'disaster').sum()) if '라벨' in ff.columns else 0
            analysis['n_win'] = int((ff['라벨'] == 'winner').sum()) if '라벨' in ff.columns else 0
            analysis['oi_match'] = round(ff['oi_zscore_24h'].notna().mean() * 100, 1) if 'oi_zscore_24h' in ff.columns else 0.0
            analysis['dis_train'] = int(((ff['라벨'] == 'disaster') & (ff['연도'].isin([2023, 2024]))).sum()) if '연도' in ff.columns else 0
            analysis['dis_test'] = int(((ff['라벨'] == 'disaster') & (ff['연도'].isin([2025, 2026]))).sum()) if '연도' in ff.columns else 0
        except Exception:
            pass
    if os.path.exists(paths[SUMMARY]):
        try:
            analysis['summary'] = pd.read_csv(paths[SUMMARY]).to_dict('records')
        except Exception:
            analysis['summary'] = []
    ok5 = (dup == 0)
    ok6 = (nrows > 0) and (nan == 0) and ok1
    checks.append(("5.중복없음", ok5, f"진입시간 중복 {dup}"))
    checks.append(("6.빔/NaN없음", ok6, f"features {nrows}행, 라벨 NaN {nan}"))

    try:
        os.makedirs(HSTR, exist_ok=True)
        w = os.path.join(HSTR, ".w"); open(w, 'w').close(); os.remove(w); ok8 = True
    except Exception:
        ok8 = False
    checks.append(("8.출력경로(..\\00WorkHstr)", ok8, HSTR))
    return checks, analysis


def build_lines(analysis, checks):
    L = [f"[작업분석] {analysis['zip']}  {analysis['time']}", "=" * 72, "[오염검사 8항목]"]
    for name, ok, memo in checks:
        L.append(f"  {'PASS' if ok else 'FAIL'} | {name} | {memo}")
    all_pass = all(ok for _, ok, _ in checks)
    L.append(f"  => 종합: {'ALL PASS' if all_pass else '★FAIL 있음 — 결과 신뢰 불가'}")
    L += ["", "[입력데이터]", f"  {analysis.get('data_path','?')} | {analysis.get('data_rows','?')}행 "
          f"{analysis.get('span_days','?')}일 hash {analysis.get('data_hash','?')}",
          f"  사고(liq) {analysis.get('n_dis','?')}건(학습{analysis.get('dis_train','?')}/검증{analysis.get('dis_test','?')}) | "
          f"승자(Fibonacci) {analysis.get('n_win','?')}건 | OI매칭률 {analysis.get('oi_match','?')}%", ""]

    L.append("[진입전 피처별 분리도 — 사고 vs 승자]")
    L.append("  (J=Youden 분리점수. 1=완벽분리, 0=무작위. 사고적중↑·승자오제거↓ 가 좋음)")
    summ = analysis.get('summary', [])
    best = None
    for r in summ:
        J = r.get('분리점수J')
        L.append(f"  [{r.get('피처'):16s}] 사고{r.get('사고평균')} vs 승자{r.get('승자평균')} "
                 f"(사고{r.get('사고범위')} 승자{r.get('승자범위')}) | 임계 {r.get('최선임계')} "
                 f"J={J} 사고적중{r.get('사고적중')} 승자오제거{r.get('승자오제거')} 검증기적중{r.get('검증기사고적중')}")
        if isinstance(J, (int, float)) and (best is None or J > best.get('분리점수J', -1)):
            best = r

    L += ["", "[★판정 — 진입전 '사고 지문'이 존재하는가]"]
    if best is None or not isinstance(best.get('분리점수J'), (int, float)):
        L.append("  측정불가(OI NaN과다 등). 데이터 확인 필요.")
    else:
        J = best['분리점수J']; hit = best.get('사고적중'); fp = best.get('승자오제거'); gen = best.get('검증기사고적중')
        L.append(f"  최고분리 피처: {best['피처']} (J={J}, 사고적중{hit}/승자오제거{fp}, 검증기적중{gen})")
        # 판정 기준: J>=0.6 & 검증기적중>=0.5 면 지문있음 / J<0.35면 지문없음 / 사이면 약함
        if J >= 0.6 and (gen is not None and gen >= 0.5):
            L.append("  ★지문 있음(in-sample 강함 + 검증기 일반화). 진입필터 ML 제작 가치 있음.")
            L.append("    => 다음: 이 피처(들) 기반 단순필터를 학습/검증 엄격분리로 제작.")
        elif J < 0.35:
            L.append("  ★지문 없음. 진입전 사고와 승자가 거의 겹침 -> 어떤 ML도 진입에서 못 가름(확정).")
            L.append("    => 사고차단(진입필터 포함) 길 종료. 갈래B(진입로직 교체) 권고.")
        else:
            L.append("  ★지문 약함(J 애매 or 검증기 일반화 실패). in-sample만 맞고 미래 일반화 의심 -> 과적합위험.")
            L.append(f"     검증기적중 {gen} (학습기 사고로 정한 임계가 검증기 사고를 못 잡으면 = 과적합).")
            L.append("    => 단순필터 한정으로 1회 검증 가능하나 기대 낮음. 또는 갈래B.")
    L += ["", f"  ※ 사고 표본 {analysis.get('n_dis','?')}건(검증기 {analysis.get('dis_test','?')}건)은 통계적으로 매우 작음 — ",
          "    in-sample 분리가 보여도 과적합 의심이 기본. 검증기 일반화가 핵심 잣대.",
          "    진입 시점 정보만 사용(미래참조 없음). 라벨은 현행엔진 자연청산 결과."]
    return L, all_pass


def write_outputs(checks, analysis):
    os.makedirs(HSTR, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M')
    txt_path = os.path.join(HSTR, f"{stamp}.txt")
    if os.path.exists(txt_path):
        txt_path = os.path.join(HSTR, f"{stamp}{datetime.datetime.now().strftime('%S')}.txt")
    dup = False
    if os.path.exists(INDEX):
        with open(INDEX, encoding='utf-8') as f:
            if any((ZIP_NAME in ln and stamp in ln) for ln in f):
                dup = True
    checks.append(("7.INDEX이중기록없음", not dup, "이미있음" if dup else "신규"))
    lines, all_pass = build_lines(analysis, checks)
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    write_header = not os.path.exists(INDEX)
    with open(INDEX, 'a', encoding='utf-8') as f:
        if write_header:
            f.write("# Rauto 작업이력 INDEX | 시각|작업|분석txt|테스트py|결과|데이터해시|메모|check\n")
        if all_pass:
            f.write(f"{analysis['time']} | {ZIP_NAME} | 분석:{os.path.basename(txt_path)} | 테스트:test.py | "
                    f"결과:sep_summary.csv | 데이터해시:{analysis.get('data_hash','?')} | 메모:진입전사고지문진단 | check:PASS\n")
        else:
            f.write(f"{analysis['time']} | {ZIP_NAME} | [FAIL — 분석:{os.path.basename(txt_path)} 확인] | check:FAIL\n")
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
