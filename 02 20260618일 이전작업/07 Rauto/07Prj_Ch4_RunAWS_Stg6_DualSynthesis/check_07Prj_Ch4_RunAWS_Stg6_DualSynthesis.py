# [check_07Prj_Ch4_RunAWS_Stg6_DualSynthesis.py]
# 코드길이: 약 105줄 / 내부버전: ch4_stg6_dualsynth_check_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 오염검사 + 작업분석 저장 + INDEX 기록. (복붙 요청 없이 결과 전량 파일로)
#   (1) 오염검사 : 근간 원장3종·엔진 SHA256 무수정 + 고정파일 + 중복/누락.
#   (2) 분석저장 : ..\00WorkHstr\(YYYYMMDDHHMM).txt — 듀얼합성·노출배분 결론.
#   (3) INDEX    : ..\00WorkHstr\00WorkHstr_INDEX.txt 한 줄 추가.
# ── 함수 ── sha256(path) / main()
# ─────────────────────────────────────────────────────────────────────────
import os
import csv
import sys
import hashlib
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "07Prj_Ch4_RunAWS_Stg6_DualSynthesis"
WH = os.path.normpath(os.path.join(HERE, "..", "00WorkHstr"))
RESULTS = os.path.join(HERE, f"{NAME}_results.csv")

EXPECTED = {
    "07Prj_Ch2_Stg2_TrendStack_OPVnNSweep_devledger.csv": "a786876e1b56561707f4cc8dcc11f97c19208ae3f629c8b5e828af060a794b44",
    "stg6_levsweep_ledger.csv": "c6e8e12cfb80b4a514aacdc2fbe158a43a563babb2abb3b5348d2bf8d1c87589",
    "07Prj_Ch2_SidewayDCARebuild_Stg1_ExpCutLiqSweep_ledger.csv": "382177289d08eb64bbe5bd73e49dbc823dedcbd7064214fa1369cd2d6d69a652",
    "SidewayDCA_Stg7_engine.py": "dfdfac4394cd780939d4b368d3ccabfbfab8d599ff1236b11f7f0d80f0823086",
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
    lines.append("[1] 오염검사 — 근간 원장3종·엔진 SHA256 무수정 대조")
    for fn, exp in EXPECTED.items():
        p = os.path.join(HERE, fn)
        if not os.path.exists(p):
            lines.append(f"  [누락] {fn}"); ok_all = False; continue
        got = sha256(p); good = (got == exp); ok_all = ok_all and good
        lines.append(f"  [{'OK' if good else '변조!'}] {fn[:46]}  {got[:14]}…")
    lines.append("[1b] 필수 파일 존재")
    for fn in FIXED + [f"{NAME}_results.csv"]:
        good = os.path.exists(os.path.join(HERE, fn)); ok_all = ok_all and good
        lines.append(f"  [{'OK' if good else '누락!'}] {fn}")
    pys = [f for f in os.listdir(HERE) if f.endswith(".py")]
    dups = [f for f in EXPECTED if f.endswith('.py') and pys.count(f) > 1]
    lines.append(f"[1c] 중복 .py: {'없음' if not dups else dups}"); ok_all = ok_all and (not dups)

    detail = []; verdict = "결과 없음"
    if os.path.exists(RESULTS):
        with open(RESULTS, encoding="utf-8") as f:
            for row in csv.reader(f):
                if not row:
                    continue
                if row[0] == 'recommend':
                    verdict = f"권장 k={row[1]} → {row[2]}% / MDD {row[3]}% (한도내 최대)"
                detail.append("  " + ",".join(row))
    else:
        lines.append("  [누락!] results.csv 없음"); ok_all = False

    stamp = datetime.now().strftime("%Y%m%d%H%M")
    txt_path = os.path.join(WH, f"{stamp}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"작업분석 — {NAME}\n초기자본 $10,000 · 두 봇 거래단위 합성(사후 원장 스윕 아키텍처 프로토타입)\n\n")
        f.write("\n".join(lines) + "\n\n[2] 노출배분 스윕\n" + "\n".join(detail) + "\n\n")
        f.write(f"[결론] 듀얼 GO·노출배분 필수. {verdict}\n")
        f.write("[미해결] 라이브 스트리밍 배선은 ADR9 결정 + PC 698MB 데이터 필요(엔진은 배치).\n")

    idx_path = os.path.join(WH, "00WorkHstr_INDEX.txt")
    line = (f"{stamp} | {NAME} | CHECK 듀얼봇 거래단위합성 | 듀얼GO·노출배분필수 {verdict} · "
            f"풀노출 MDD-23.5%위반 | 오염검사 {'OK' if ok_all else 'FAIL'} | $10k복리 | 원장3종+엔진")
    with open(idx_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")

    print("\n".join(lines)); print("\n".join(detail))
    print(f"[저장] 분석={txt_path}")
    print(f"[INDEX] {line}")
    print(f"[판정] 오염검사 {'OK' if ok_all else 'FAIL'} · {verdict}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
