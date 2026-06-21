# [check_07Prj_Ch4_RunAWS_Stg3_NMultSweep.py]
# 코드길이: 약 125줄 / 내부버전: ch4_stg3_nmult_check_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 오염검사 + 작업분석 저장 + INDEX 기록. (복붙 요청 없이 결과 전량 파일로)
#   (1) 오염검사 : 근간 데이터(devledger)·원본 로직(bot·poc)·고정파일 SHA256 무수정 + 중복/누락.
#   (2) 분석저장 : ..\00WorkHstr\(YYYYMMDDHHMM).txt — NMULT 스윕·CPCV 트레이드오프.
#   (3) INDEX    : ..\00WorkHstr\00WorkHstr_INDEX.txt 한 줄 추가.
# [경로] 하위폴더 실행 → 결과/INDEX는 ..\00WorkHstr 로 출력.
# ── 함수 ── sha256(path) / main()
# ─────────────────────────────────────────────────────────────────────────
import os
import csv
import sys
import hashlib
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "07Prj_Ch4_RunAWS_Stg3_NMultSweep"
WH = os.path.normpath(os.path.join(HERE, "..", "00WorkHstr"))
RESULTS = os.path.join(HERE, f"{NAME}_results.csv")

EXPECTED = {
    "07Prj_Ch2_Stg2_TrendStack_OPVnNSweep_devledger.csv": "a786876e1b56561707f4cc8dcc11f97c19208ae3f629c8b5e828af060a794b44",
    "bot_trendstack_signal.py": "040da0d277d166cae1456c9c2ea340fd8b8d6c1ae9d079713cef22dc30ffb08a",
    "trendstack_poc.py":        "3065230c60756bace4e2c3f6278742fcacc1dbe01235e112c37fea2463319963",
}
FIXED = [f"test_{NAME}.py", f"check_{NAME}.py", "run.bat"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    os.makedirs(WH, exist_ok=True)
    lines = []; ok_all = True

    lines.append("[1] 오염검사 — 근간 데이터·원본 로직 SHA256 무수정 대조")
    for fn, exp in EXPECTED.items():
        p = os.path.join(HERE, fn)
        if not os.path.exists(p):
            lines.append(f"  [누락] {fn}"); ok_all = False; continue
        got = sha256(p); good = (got == exp); ok_all = ok_all and good
        lines.append(f"  [{'OK' if good else '변조!'}] {fn}  {got[:16]}…")

    lines.append("[1b] 필수 파일 존재")
    for fn in FIXED + [f"{NAME}_results.csv"]:
        good = os.path.exists(os.path.join(HERE, fn)); ok_all = ok_all and good
        lines.append(f"  [{'OK' if good else '누락!'}] {fn}")

    pys = [f for f in os.listdir(HERE) if f.endswith(".py")]
    dups = [f for f in EXPECTED if f.endswith('.py') and pys.count(f) > 1]
    lines.append(f"[1c] 중복 .py: {'없음' if not dups else dups}")
    ok_all = ok_all and (not dups)

    rows = []
    if os.path.exists(RESULTS):
        with open(RESULTS, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    else:
        lines.append("  [누락!] results.csv 없음 → 테스트 미실행"); ok_all = False

    detail = []
    for r in rows:
        detail.append(f"  NMULT={r['NMULT']}  full {r['full_ret']}%/MDD{r['full_mdd']}% Calmar{r['calmar']}  "
                      f"CPCV최악MDD {r['cpcv_worst_mdd']}% 한도위반 {r['cpcv_breach']}")
    base = next((r for r in rows if r['NMULT'] == '0.6'), None)
    zero = [r for r in rows if r['cpcv_breach'] == '0']
    robust = max(zero, key=lambda r: float(r['full_ret'])) if zero else None
    best_cal = max(rows, key=lambda r: float(r['calmar'])) if rows else None
    if base and robust and best_cal:
        verdict_txt = (f"트레이드오프: 기준0.6(CPCV1위반,실경로-15.4%안전) / "
                       f"견고쿠션 NMULT={robust['NMULT']}(0위반,{robust['full_ret']}%) / "
                       f"Calmar최고 NMULT={best_cal['NMULT']}(Calmar{best_cal['calmar']}) → 사장님 결정사안")
    else:
        verdict_txt = "결과 파싱 실패"

    stamp = datetime.now().strftime("%Y%m%d%H%M")
    txt_path = os.path.join(WH, f"{stamp}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"작업분석 — {NAME}\n초기자본 $10,000 복리 · devledger 264 실거래 재구성(절대수치 근사, NMULT 상대비교)\n\n")
        f.write("\n".join(lines) + "\n\n[2] NMULT 스윕 · CPCV 견고성\n" + "\n".join(detail) + "\n\n")
        f.write(f"[판정] 오염검사 {'OK' if ok_all else 'FAIL'} · {verdict_txt}\n")

    idx_path = os.path.join(WH, "00WorkHstr_INDEX.txt")
    line = (f"{stamp} | {NAME} | CHECK NMULT0.4~0.8 CPCV | {verdict_txt} | "
            f"오염검사 {'OK' if ok_all else 'FAIL'} | $10k복리 | devledger264")
    with open(idx_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")

    print("\n".join(lines)); print("\n".join(detail))
    print(f"[저장] 분석={txt_path}")
    print(f"[INDEX] {line}")
    print(f"[판정] 오염검사 {'OK' if ok_all else 'FAIL'} · {verdict_txt}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
