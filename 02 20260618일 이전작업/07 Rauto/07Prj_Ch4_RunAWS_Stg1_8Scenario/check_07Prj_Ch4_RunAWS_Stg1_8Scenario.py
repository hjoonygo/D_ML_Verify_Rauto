# [check_07Prj_Ch4_RunAWS_Stg1_8Scenario.py]
# 코드길이: 약 130줄 / 내부버전: ch4_stg1_8scenario_check_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 산출물 오염검사 + 작업분석 저장 + INDEX 기록. (복붙 요청 없이 결과 전량 파일로)
#   (1) 오염검사 : 필수 파일 존재 + 검증모듈 SHA256 무수정 대조 + 중복/누락 탐지.
#   (2) 분석저장 : ..\00WorkHstr\(YYYYMMDDHHMM).txt 로 8시나리오 결과 저장.
#   (3) INDEX    : ..\00WorkHstr\00WorkHstr_INDEX.txt 에 이번 작업 한 줄 추가.
# [경로] 이 스크립트는 하위폴더에서 실행 → 결과/INDEX는 한 단계 위 ..\00WorkHstr 로 출력.
# ── 사용 파일 ── (검사대상) 검증모듈 6종 + test/check/run.bat + results.csv
# ── 함수 In/Out ──
#   sha256(path) In: 파일 Out: 해시문자열
#   main()       In: - Out: 검사결과 출력 + 분석txt + INDEX 한 줄
# ─────────────────────────────────────────────────────────────────────────
import os
import csv
import sys
import hashlib
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "07Prj_Ch4_RunAWS_Stg1_8Scenario"
WH = os.path.normpath(os.path.join(HERE, "..", "00WorkHstr"))   # D:\ML\verify\00WorkHstr
RESULTS = os.path.join(HERE, f"{NAME}_results.csv")

# 검증모듈 '무수정' 기대 해시(빌드시 확정). 신호엔진=SpTrd_Fib 1:1 추출본.
EXPECTED = {
    "bot_trendstack_signal.py":   "040da0d277d166cae1456c9c2ea340fd8b8d6c1ae9d079713cef22dc30ffb08a",
    "trendstack_signal_engine.py":"c9d784bfd81e8ed4ffccbc07fd3725ee99738c5b42c71102d59ab616a1c8fa2d",
    "trendstack_poc.py":          "3065230c60756bace4e2c3f6278742fcacc1dbe01235e112c37fea2463319963",
    "trendstack_regime.py":       "d573d7d522455fc01a6b5a1070da26dda70b9841142a909d8abf6958e0ebe996",
    "rauto_contract.py":          "40b974ac7859a95fe19b31aa8d7fd503a4dee00726da75c8bd06082b6576791b",
    "rauto_paper_engine.py":      "f3ff3e652c2d60338ae238807aff322dd5fe632a811348d50607b1e3969c90a3",
    "mock_candles.py":            "bcddc841e0395123c33896d0b4848642a218162f8528ba310131c48eedfa0d6c",
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
    lines = []
    contam_ok = True

    # (1) 오염검사 — 검증모듈 해시 무수정 대조
    lines.append("[1] 오염검사 — 검증모듈 SHA256 무수정 대조")
    for fn, exp in EXPECTED.items():
        p = os.path.join(HERE, fn)
        if not os.path.exists(p):
            lines.append(f"  [누락] {fn}"); contam_ok = False; continue
        got = sha256(p)
        ok = (got == exp)
        contam_ok = contam_ok and ok
        lines.append(f"  [{'OK' if ok else '변조!'}] {fn}  {got[:16]}…")

    # 필수 고정파일 + 결과파일 존재
    lines.append("[1b] 필수 파일 존재")
    for fn in FIXED + [f"{NAME}_results.csv"]:
        p = os.path.join(HERE, fn)
        ok = os.path.exists(p)
        contam_ok = contam_ok and ok
        lines.append(f"  [{'OK' if ok else '누락!'}] {fn}")

    # 중복(같은 모듈명 .py가 둘 이상) 탐지
    pys = [f for f in os.listdir(HERE) if f.endswith(".py")]
    dups = [f for f in EXPECTED if pys.count(f) > 1]
    lines.append(f"[1c] 중복 .py: {'없음' if not dups else dups}")
    contam_ok = contam_ok and (not dups)

    # (2) 결과 파싱
    n_pass = n_total = 0
    detail = []
    if os.path.exists(RESULTS):
        with open(RESULTS, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                n_total += 1
                if row["verdict"] == "PASS":
                    n_pass += 1
                detail.append(f"  {row['scenario']:<16} {row['verdict']:<4} "
                              f"ent={row['enter']} liq={row['n_liq']} match={row['match']} "
                              f"ret={row['ret_pct']}% mdd={row['mdd_pct']}%")
    else:
        lines.append("  [누락!] results.csv 없음 → 테스트 미실행"); contam_ok = False

    verdict = (contam_ok and n_total > 0 and n_pass == n_total)
    stamp = datetime.now().strftime("%Y%m%d%H%M")

    # (2) 분석 txt 저장 (..\00WorkHstr\(분단위).txt)
    txt_path = os.path.join(WH, f"{stamp}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"작업분석 — {NAME}\n초기자본 $10,000 복리 · 합성데이터(배선 강건성, 숫자 트랙 아님)\n\n")
        f.write("\n".join(lines) + "\n\n[2] 8시나리오 결과\n" + "\n".join(detail) + "\n\n")
        f.write(f"[판정] 오염검사 {'OK' if contam_ok else 'FAIL'} · 시나리오 {n_pass}/{n_total} · "
                f"전체 {'PASS' if verdict else 'FAIL'}\n")

    # (3) INDEX 한 줄 추가
    idx_path = os.path.join(WH, "00WorkHstr_INDEX.txt")
    line = (f"{stamp} | {NAME} | CHECK {n_pass}/{n_total} | "
            f"라이브 페이퍼 배선 강건성(끊김없이·동일거래·MAE보유구간) | "
            f"검증모듈 무수정해시 {'OK' if contam_ok else 'FAIL'} | $10k복리 | 합성데이터")
    with open(idx_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")

    print("\n".join(lines))
    print("\n".join(detail))
    print(f"[저장] 분석={txt_path}")
    print(f"[INDEX] {line}")
    print(f"[판정] 전체 {'PASS' if verdict else 'FAIL'}")
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
