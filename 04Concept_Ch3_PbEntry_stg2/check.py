# -*- coding: utf-8 -*-
# [FILE] check.py  (04FromAll_IDEA4Concept_Ch3_PullbackEntryDist - 8-check + INDEX)
# CODE LENGTH: approx 150 lines | INTERNAL VER: check_entrydist_v1 | full output, no omission
# [PURPOSE] test.py 직후. (1)오염검사 8항목 (2)분석txt (3)INDEX 1줄. 출력 -> ..\00WorkHstr
# [8 SCENARIOS] 1결과존재 2잔존없음 3파일명일치 4데이터정상 5중복없음 6빔/NaN없음 7INDEX중복 8출력경로
import os, sys, glob, time, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); PARENT = os.path.dirname(HERE)
ZIP_NAME = os.path.basename(HERE); HSTR = os.path.join(PARENT, "00WorkHstr")
INDEX = os.path.join(HSTR, "00WorkHstr_INDEX.txt")
SUMMARY = "entrydist_summary.csv"; TRADES = "entrydist_trades.csv"; EXPECTED = [SUMMARY, TRADES]
START = os.path.join(HERE, ".run_start")

def sha8(p):
    hh = hashlib.sha256()
    with open(p, 'rb') as f: hh.update(f.read(1 << 20))
    return hh.hexdigest()[:8]

def find_data():
    p = os.path.join(PARENT, "Merged_Data_with_Regime_Features.csv")
    return p if os.path.exists(p) else None

def run_checks(start_ts):
    checks = []; an = {'zip': ZIP_NAME, 'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}
    paths = {n: os.path.join(HERE, n) for n in EXPECTED}
    ok1 = all(os.path.exists(p) for p in paths.values())
    checks.append(("1.결과파일존재", ok1, ",".join(f"{n}={'O' if os.path.exists(p) else 'X'}" for n,p in paths.items())))
    stale = [n for n,p in paths.items() if os.path.exists(p) and os.path.getmtime(p) < start_ts]
    checks.append(("2.잔존섞임없음", (not stale) and ok1, "stale="+(",".join(stale) if stale else "없음")))
    found = [os.path.basename(f) for f in glob.glob(os.path.join(HERE, "entrydist_*.csv"))]
    bad = [f for f in found if f not in EXPECTED]
    checks.append(("3.파일명일치", (not bad) and ok1, "위반="+(",".join(bad) if bad else "없음")))
    data = find_data()
    if data:
        try:
            dd = pd.read_csv(data, usecols=['timestamp'])
            span = (pd.to_datetime(dd['timestamp'].iloc[-1]) - pd.to_datetime(dd['timestamp'].iloc[0])).days
            an.update(rows=len(dd), hash=sha8(data), span=span)
            warn = "" if span >= 900 else f" ★{span}일(36mo미만)"
            checks.append(("4.데이터정상", os.path.dirname(data) == PARENT, f"{len(dd)}행 {span}일 hash={an['hash']}{warn}"))
        except Exception as e:
            checks.append(("4.데이터정상", False, f"읽기실패:{e}"))
    else:
        checks.append(("4.데이터정상", False, "상위데이터 없음"))
    dup = nrows = nan = 0
    if os.path.exists(paths[TRADES]):
        try:
            tt = pd.read_csv(paths[TRADES])
            if {'mode','dir','진입시간'}.issubset(tt.columns):
                dup = int(tt.duplicated(subset=['mode','dir','진입시간']).sum())
        except Exception: pass
    if os.path.exists(paths[SUMMARY]):
        try:
            ss = pd.read_csv(paths[SUMMARY]); nrows = len(ss)
            if '누적R_pct' in ss.columns: nan = int(ss['누적R_pct'].isna().sum())
            an['summary'] = ss.to_dict('records')
        except Exception: an['summary'] = []
    checks.append(("5.중복없음", dup == 0, f"중복 {dup}"))
    checks.append(("6.빔/NaN없음", (nrows > 0 and nan == 0 and ok1), f"summary {nrows}행 NaN {nan}"))
    try:
        os.makedirs(HSTR, exist_ok=True); w = os.path.join(HSTR, ".w"); open(w,'w').close(); os.remove(w); ok8 = True
    except Exception: ok8 = False
    checks.append(("8.출력경로", ok8, HSTR))
    return checks, an

def build_lines(an, checks):
    L = [f"[작업분석] {an['zip']}  {an['time']}", "="*72, "[오염검사 8항목]"]
    for nm, ok, m in checks: L.append(f"  {'PASS' if ok else 'FAIL'} | {nm} | {m}")
    allp = all(ok for _, ok, _ in checks)
    L.append(f"  => 종합: {'ALL PASS' if allp else '★FAIL 있음'}")
    L += ["", "[입력데이터]", f"  {an.get('rows','?')}행 {an.get('span','?')}일 hash {an.get('hash','?')}", ""]
    summ = an.get('summary', [])
    L.append("[진입게이트 4칸 × 임계 비교 — BOTH/ALL 기준 누적R 상위]")
    both = [r for r in summ if r.get('방향')=='BOTH' and r.get('구간')=='ALL']
    both.sort(key=lambda r: -(r.get('누적R_pct') or -1e9))
    for r in both[:12]:
        L.append(f"  [{r.get('설정'):22s}] 거래{r.get('거래수')} 승률{r.get('승률_pct')}% "
                 f"누적R{r.get('누적R_pct')}% PF{r.get('PF')} 평균R{r.get('평균R_pct')}% 최악{r.get('최악R_pct')}%")
    L += ["", "[★판정 — 거리확보/대기가 즉시진입보다 나은가, 롱/숏 분리]"]
    e0 = next((r for r in both if r.get('설정')=='E0_now'), None)
    if e0:
        base = e0.get('누적R_pct')
        L.append(f"  기준 E0_now(즉시): 누적R {base}% PF{e0.get('PF')} 거래{e0.get('거래수')}")
        better = [r for r in both if (r.get('누적R_pct') or -1e9) > (base or 0) and r.get('설정')!='E0_now']
        if better:
            top = better[0]
            L.append(f"  최선: {top.get('설정')} 누적R {top.get('누적R_pct')}% (E0 대비 {round((top.get('누적R_pct') or 0)-(base or 0),2):+}%p)")
        else:
            L.append("  거리확보/대기 어느 칸도 즉시진입을 못 넘음 → 눌림목 즉시진입이 최선(이번 데이터)")
    # 롱/숏 분리 요약
    for dlab in ['LONG','SHORT']:
        dd = [r for r in summ if r.get('방향')==dlab and r.get('구간')=='ALL']
        dd.sort(key=lambda r: -(r.get('누적R_pct') or -1e9))
        if dd:
            t = dd[0]
            L.append(f"  [{dlab}] 최선 {t.get('설정')} 누적R{t.get('누적R_pct')}% PF{t.get('PF')} 거래{t.get('거래수')}")
    L += ["", "  ※ 진입=양방향 눌림목, 청산=InfraA 엔진(고정). 진입시점 4칸×ATR·% 스윕. train/test 분리."]
    return L, allp

def main():
    start_ts = (os.path.getmtime(START) if os.path.exists(START) else time.time()-3600)
    checks, an = run_checks(start_ts)
    os.makedirs(HSTR, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M')
    txt = os.path.join(HSTR, f"{stamp}.txt")
    if os.path.exists(txt): txt = os.path.join(HSTR, f"{stamp}{datetime.datetime.now().strftime('%S')}.txt")
    dup = False
    if os.path.exists(INDEX):
        with open(INDEX, encoding='utf-8') as f:
            if any((ZIP_NAME in ln and stamp in ln) for ln in f): dup = True
    checks.append(("7.INDEX이중기록없음", not dup, "이미있음" if dup else "신규"))
    lines, allp = build_lines(an, checks)
    with open(txt, 'w', encoding='utf-8') as f: f.write("\n".join(lines))
    hdr = not os.path.exists(INDEX)
    with open(INDEX, 'a', encoding='utf-8') as f:
        if hdr: f.write("# Rauto 작업이력 INDEX\n")
        if allp:
            f.write(f"{an['time']} | {ZIP_NAME} | 분석:{os.path.basename(txt)} | 테스트:test.py | "
                    f"결과:entrydist_summary.csv | 데이터해시:{an.get('hash','?')} | 메모:양방향눌림목×진입게이트4칸 | check:PASS\n")
        else:
            f.write(f"{an['time']} | {ZIP_NAME} | [FAIL — 분석:{os.path.basename(txt)} 확인] | check:FAIL\n")
    print(f"[check] 저장:{txt}\n[check] INDEX:{INDEX}\n[check] 종합:{'ALL PASS' if allp else '★FAIL'}")

if __name__ == "__main__":
    main()
