# -*- coding: utf-8 -*-
# [ret_guard.py] 수익률 출력 강제 라벨 — 백테/보고가 '라벨 없이는 수익률을 못 뱉게' 강제.
#   배경: 캡틴 격노 2026-06-28(260628_02) — in-sample 천장 수치를 기간·기준 라벨 없이 노출(§19·memory#6 위반).
#   원칙(memory#6): 모든 수익률에 (기간, in-sample 상한 / OOS) 라벨 의무. 헤드라인은 OOS만.
#   ★코드 레벨 강제: fmt_ret()는 period·basis 없이는 ValueError. 백테 출력은 이 함수로만 수익률 문자열화.
#   ★hook과 단일로직: scan_unlabeled는 .claude/hooks/ret_label_guard.py와 동일 규칙(자가검문·테스트용).
import re

BASIS_OK = {"OOS", "in-sample 상한", "천장", "현실-OOS"}   # 허용 기준값(이외엔 raise)
BIG_RET = re.compile(r'[+\-]?\d{1,3}(?:,\d{3})+\s*%|(?<![\d.])[+\-]?\d{4,}\s*%|(?<![\d.])\d+(?:\.\d+)?\s*[만억조]\s*%')
BASIS_RE = re.compile(r'OOS|held[\s\-]?out|heldout|in[\s\-]?sample|insample|상한|천장|실전\s*아님|실전아님|ceiling|미산출'
                      r'|무손상|앵커|anchor|기준값|재현', re.IGNORECASE)
CMP_PRE = re.compile(r'[≥≤<>~±]\s*$')
CMP_POST = re.compile(r'^\s*(?:이상|이하|초과|미만|넘|까지|이내|배\b|p\b|bp)')


def fmt_ret(value_pct, period, basis, slip_bp=None, mdd_pct=None):
    """수익률을 '라벨 강제 박힌' 문자열로. period·basis 없으면 ValueError(=깜빡 방지).
       basis ∈ {'OOS','in-sample 상한','천장','현실-OOS'}. 예: fmt_ret(2121,'post-2024 28mo','OOS',slip_bp=10,mdd_pct=-5.5)
         → '+2,121% (post-2024 28mo · OOS · 슬립10bp · MDD-5.5%)'"""
    if not period or not str(period).strip():
        raise ValueError("fmt_ret: period(기간) 필수 — 라벨 없는 수익률 금지(memory#6)")
    if basis not in BASIS_OK:
        raise ValueError(f"fmt_ret: basis는 {BASIS_OK} 중 하나 — 받은값 {basis!r}. 헤드라인은 'OOS'만(memory#6)")
    tag = f"{period} · {basis}"
    if slip_bp is not None:
        tag += f" · 슬립{slip_bp:g}bp"
    if mdd_pct is not None:
        tag += f" · MDD{mdd_pct:+.1f}%"
    return f"{value_pct:+,.0f}% ({tag})"


def scan_unlabeled(text):
    """텍스트에서 라벨 없는 '진짜 수익률' 토큰 반환(없으면 None). hook(ret_label_guard.py)과 동일 규칙.
       오탐 예외: 기준라벨 문단 통과 · %p·임계어(이상/이하/배)·비교기호(≥~±)·인라인코드(` `) 제외."""
    if not text:
        return None
    for blk in re.split(r'\n\s*\n', text):
        if BASIS_RE.search(blk):
            continue
        for m in BIG_RET.finditer(blk):
            s, e = m.start(), m.end()
            if CMP_POST.match(blk[e:e + 8]):
                continue
            if CMP_PRE.search(blk[max(0, s - 4):s]):
                continue
            if blk[:s].count('`') % 2 == 1:
                continue
            return m.group(0).strip()
    return None


def assert_labeled(text):
    """보고 텍스트 자가검문 — 라벨 없는 큰 수익률 있으면 AssertionError."""
    bad = scan_unlabeled(text)
    assert bad is None, f"라벨 없는 수익률 '{bad}' — (기간 + OOS/in-sample 상한) 명시 필요(memory#6)"
    return True


if __name__ == "__main__":
    # 자가테스트
    print(fmt_ret(2121, "post-2024 28mo", "OOS", slip_bp=10, mdd_pct=-5.5))
    print(fmt_ret(3229453, "36mo", "in-sample 상한", slip_bp=0))
    assert scan_unlabeled("결과 +55,664% 입니다") == "+55,664%"           # 라벨없음 → 검출
    assert scan_unlabeled("held-out OOS +2,121% (28mo)") is None          # 라벨있음 → 통과
    try:
        fmt_ret(100, "36mo", "헤드라인천장")  # 잘못된 basis
        raise SystemExit("FAIL: basis 검증 안됨")
    except ValueError:
        pass
    print("[ret_guard] 자가테스트 PASS")
