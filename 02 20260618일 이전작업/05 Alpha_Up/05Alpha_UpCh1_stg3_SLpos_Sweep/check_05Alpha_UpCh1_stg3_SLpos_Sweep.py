# -*- coding: utf-8 -*-
# [FILE] check_05Alpha_UpCh1_stg3_SLpos_Sweep.py
# 코드길이: 약 175줄 | 내부버전명: 05Alpha_Up_Ch1_SLpos_stg3 | 전체 출력, 축약/생략 없음
# [역할] test 실행 후 (1)오염검사 8항목 (2)분석txt 상위 00WorkHstr 저장 (3)INDEX 1줄 추가.
# [8항목] 1.필수파일 2.CSV非공백 3.코드해시 4.거래중복 5.미래참조가드 6.거래비중첩
#         7.SL모드 8종 완전(A_STEP+FIX7) 8.VERDICT존재
# ==============================================================================
import os, sys, hashlib, datetime
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
WORKHSTR = os.path.join(PARENT, "00WorkHstr")
VER = "05Alpha_Up_Ch1_SLpos_stg3"
TEST_PY  = "test_05Alpha_UpCh1_stg3_SLpos_Sweep.py"
CHECK_PY = "check_05Alpha_UpCh1_stg3_SLpos_Sweep.py"
REQUIRED = [TEST_PY, CHECK_PY, "run.bat",
            "sl_summary.csv", "sl_position_sweep.csv", "sl_trades.csv", "sl_monthly.csv", "sl_scenarios.csv"]
EXPECT_MODES = {'A_STEP','FIX020','FIX030','FIX040','FIX050','FIX060','FIX070','FIX080'}


def sha256(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for c in iter(lambda:f.read(8192),b""): h.update(c)
    return h.hexdigest()


def parse_verdict():
    sp=os.path.join(HERE,"sl_summary.csv")
    if not os.path.exists(sp): return None
    with open(sp,encoding="utf-8-sig") as f:
        for line in f:
            if "VERDICT" in line: return line.strip().strip('"').rstrip(',')
    return None


def check_8():
    res=[]
    present={f:os.path.exists(os.path.join(HERE,f)) for f in REQUIRED}
    miss=[f for f,ok in present.items() if not ok]
    res.append(("1.필수파일존재", len(miss)==0, f"누락:{miss}" if miss else "all present"))

    csvs=["sl_summary.csv","sl_position_sweep.csv","sl_trades.csv","sl_monthly.csv","sl_scenarios.csv"]
    empties=[c for c in csvs if present.get(c) and os.path.getsize(os.path.join(HERE,c))<10]
    res.append(("2.결과CSV非공백", len(empties)==0, f"빈:{empties}" if empties else "ok"))

    hashes={f:sha256(os.path.join(HERE,f))[:16] for f in [TEST_PY,CHECK_PY] if present.get(f)}
    res.append(("3.코드해시기록", len(hashes)==2, str(hashes)))

    tp=os.path.join(HERE,"sl_trades.csv"); dup=0; t=None
    if present.get("sl_trades.csv"):
        try: t=pd.read_csv(tp); dup=int(t.duplicated().sum())
        except Exception: dup=-1
    res.append(("4.거래중복없음", dup==0, f"중복{dup}행"))

    look=True; memo="미래참조 패턴 미사용(체결 open_[i+1] 확인)"
    with open(os.path.join(HERE,TEST_PY),encoding="utf-8") as f: lines=f.readlines()
    bad=[]
    for ln,raw in enumerate(lines,1):
        c=raw.split("#",1)[0].replace(" ","")
        if (".shift(-" in c) or (".iloc[i+1]" in c): bad.append(ln)
        if ("[i+1]" in c) and ("open_[i+1]" not in c) and ("i+1<n" not in c): bad.append(ln)
    if bad: look=False; memo=f"의심 코드라인 {sorted(set(bad))} 수동확인"
    res.append(("5.미래참조가드", look, memo))

    overlap=0
    if t is not None and len(t) and 'entry_t' in t.columns:
        try:
            tt=t.copy(); tt['entry_t']=pd.to_datetime(tt['entry_t']); tt['exit_t']=pd.to_datetime(tt['exit_t'])
            for _,g in tt.groupby(['sl_mode','side']):
                g=g.sort_values('entry_t'); prev=None
                for _,r in g.iterrows():
                    if prev is not None and r['entry_t']<prev: overlap+=1
                    prev=r['exit_t']
        except Exception: overlap=-1
    res.append(("6.거래비중첩", overlap==0, f"중첩{overlap}건(모드x방향)"))

    # 7.SL모드 8종 완전 (summary에 A_STEP+FIX7 다 있나)
    ok7=False; memo7="검증불가"
    sp=os.path.join(HERE,"sl_summary.csv")
    if present.get("sl_summary.csv"):
        try:
            s=pd.read_csv(sp).iloc[1:]
            got=set(s['sl_mode'].unique())
            ok7 = EXPECT_MODES.issubset(got)
            memo7=f"모드 {len(got)}종 / 기대8종 {'충족' if ok7 else '누락:'+str(EXPECT_MODES-got)}"
        except Exception as e: memo7=f"err {e}"
    res.append(("7.SL모드8종완전", ok7, memo7))

    v=parse_verdict()
    res.append(("8.VERDICT존재", v is not None, (v[:50]+"...") if v else "없음"))

    passed=all(ok for _,ok,_ in res)
    return passed,res,hashes


def write_analysis(passed,res,hashes,verdict):
    os.makedirs(WORKHSTR,exist_ok=True)
    stamp=datetime.datetime.now().strftime("%Y%m%d_%H%M")
    path=os.path.join(WORKHSTR,f"{stamp}.txt")
    lines=[f"[작업분석] {VER}  ({datetime.datetime.now().isoformat(timespec='seconds')})",
           f"[오염검사 종합] {'PASS' if passed else 'FAIL'}","-"*60]
    for label,ok,memo in res: lines.append(f"  {'O' if ok else 'X'} {label}: {memo}")
    lines.append("-"*60); lines.append(f"[VERDICT] {verdict}"); lines.append(f"[코드해시] {hashes}")
    psp=os.path.join(HERE,"sl_position_sweep.csv")
    if os.path.exists(psp):
        try:
            ps=pd.read_csv(psp)
            lines.append("[SL위치 스윕 — 위치별 평균 test PF (롱/숏)]")
            for _,r in ps.iterrows():
                lines.append(f"  {r['sl_mode']} {r['side']}: 평균testPF {r['avg_test_PF']} cumR {r['avg_test_cumR']}% PF>1비율 {r['pf_gt1_pct']}%")
        except Exception: pass
    with open(path,"w",encoding="utf-8") as f: f.write("\n".join(lines))
    return path


def update_index(one_line):
    os.makedirs(WORKHSTR,exist_ok=True)
    idx=os.path.join(WORKHSTR,"00WorkHstr_INDEX.txt")
    hn=not os.path.exists(idx)
    with open(idx,"a",encoding="utf-8") as f:
        if hn: f.write("# 00WorkHstr INDEX | 시각 | 버전 | 검사 | 핵심성과\n")
        f.write(one_line+"\n")


def main():
    passed,res,hashes=check_8(); verdict=parse_verdict() or "N/A"
    apath=write_analysis(passed,res,hashes,verdict)
    stamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    update_index(f"{stamp} | {VER} | {'PASS' if passed else 'FAIL'} | {verdict[:120]}")
    print(f"[check] integrity={'PASS' if passed else 'FAIL'}")
    print(f"[check] analysis -> {apath}")
    print(f"[check] INDEX -> {os.path.join(WORKHSTR,'00WorkHstr_INDEX.txt')}")


if __name__ == "__main__":
    main()
