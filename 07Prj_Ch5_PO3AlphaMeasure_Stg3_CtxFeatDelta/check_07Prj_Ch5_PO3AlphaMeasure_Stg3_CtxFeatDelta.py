# -*- coding: utf-8 -*-
# [check_07Prj_Ch5_PO3AlphaMeasure_Stg3_CtxFeatDelta.py]
# 3역할(§4): ① 오염검사(파일명·SHA256·중복/누락) ② 분석 존재확인(분석txt는 Code가 00WorkHstr에 직접 작성)
#            ③ 00WorkHstr_INDEX.txt에 완료 한 줄 추가(중복방지).
import os, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.dirname(HERE)                         # D:\ML\verify
WH = os.path.join(DATA, "00WorkHstr")
INDEX = os.path.join(WH, "00WorkHstr_INDEX.txt")
ANALYSIS = os.path.join(WH, "202606141138.txt")
STAMP = "202606141138"
NAME = "07Prj_Ch5_PO3AlphaMeasure_Stg3_CtxFeatDelta"

EXPECT = [
    f"test_{NAME}.py",
    f"check_{NAME}.py",
    "run.bat",
    "devledger.csv",                                 # 근간(동봉)
    "best.csv",                                      # 근간(동봉)
    f"{NAME}_stage1_buckets.csv",                    # 산출
]

INDEX_LINE = (
    f"{STAMP} | {NAME} | POC 컨텍스트피처 증분검증 Stage0동결+Stage1델타 (검증엔진 무수정, §9 무변동) "
    "| Stage0=OPVnN best 동결(OPV0.25/n0.6/N1.0/EXP1.75/+900.0%/MDD-19.74%/CPCVp25 2.72; OPV·n·N=§9일치) "
    "| Stage1 델타=meanR(oppo>=2ATR)-meanR(oppo0.5~2ATR)=-0.00729 부트95%CI[-0.0272,+0.0091] B5000=0포함 "
    "→ ★증분신호 노이즈수준(신뢰95), PO3-H1 거리비대칭이 7h추세봇 R로 전이안됨 "
    "| 지침의 'Stage1없으면중단' 발동 → Stage2~3(CPCV·8시나리오) 진행안함=게이트 정상작동(대형연산 회피) "
    "| 컨텍스트피처 가치 15→0(현형태 탈락, 폐기아님: 진입게이트형 재정의만 저비용 잔여) | 채택0건 "
    "| 산출:202606141138.txt+stage1_buckets.csv | src=캡틴 일괄진행 지시 2026-06-14"
)


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    print(f"[check {NAME}]")
    # ── ① 오염검사 ──
    miss = [n for n in EXPECT if not os.path.exists(os.path.join(HERE, n))]
    dup = len(EXPECT) - len(set(EXPECT))
    print("\n[① 오염검사] SHA256:")
    for n in EXPECT:
        p = os.path.join(HERE, n)
        if os.path.exists(p):
            print(f"  {sha256(p)}  {n}")
    print(f"  누락 {len(miss)}건 {miss if miss else ''} · 파일명중복 {dup}건")
    ok1 = (not miss) and (dup == 0)

    # ── ② 분석 존재확인 ──
    ok2 = os.path.exists(ANALYSIS)
    print(f"\n[② 분석txt] {os.path.basename(ANALYSIS)} 존재={ok2}")

    # ── ③ INDEX 한 줄 추가(중복방지) ──
    existing = ""
    if os.path.exists(INDEX):
        with open(INDEX, "r", encoding="utf-8") as f:
            existing = f.read()
    if STAMP + " | " + NAME in existing:
        print(f"\n[③ INDEX] 이미 기록됨({STAMP} {NAME}) — 중복추가 생략")
        ok3 = True
    else:
        with open(INDEX, "a", encoding="utf-8") as f:
            f.write("\r\n" + INDEX_LINE)
        print(f"\n[③ INDEX] 1줄 추가 완료 → {INDEX}")
        ok3 = True

    print(f"\n[VERDICT] 오염검사={ok1} 분석존재={ok2} INDEX={ok3} → "
          f"{'ALL PASS' if (ok1 and ok2 and ok3) else 'CHECK 실패'}")


if __name__ == "__main__":
    main()
