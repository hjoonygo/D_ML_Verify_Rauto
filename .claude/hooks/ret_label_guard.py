#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# [ret_label_guard.py] Stop hook — 라벨 없는 '큰 수익률' 헤드라인을 응답 송출 전에 차단.
#   배경: 캡틴 격노 2026-06-28(260628_02) — Claude가 in-sample 천장(+55,664%·+6,829% 등)을
#         기간·기준 라벨 없이 헤드라인으로 노출(§19·memory#6 위반·재범). 메모리만으론 못 막음 → 강제장치.
#   동작: 마지막 assistant 턴의 text에서 ≥1000%(또는 만/억/조%) 수익률 토큰을 찾고,
#         같은 문단에 기준 라벨(OOS/held-out/in-sample 상한/천장/실전 아님/미산출)이 없으면 차단(decision=block).
#   ★철칙: 어떤 예외도 세션을 깨면 안 됨 → 모든 오류는 exit 0(통과). 무한루프 = stop_hook_active로 차단.
import sys, json, re

# 큰 수익률 토큰: 쉼표그룹(1,000+), 4자리+(1000+), 한글 만/억/조 %
BIG_RET = re.compile(r'[+\-]?\d{1,3}(?:,\d{3})+\s*%|(?<![\d.])[+\-]?\d{4,}\s*%|(?<![\d.])\d+(?:\.\d+)?\s*[만억조]\s*%')
# 기준 라벨(같은 문단에 있으면 통과). 검증맥락(무손상·앵커·재현)도 라벨로 인정.
BASIS = re.compile(r'OOS|held[\s\-]?out|heldout|in[\s\-]?sample|insample|상한|천장|실전\s*아님|실전아님|ceiling|미산출'
                   r'|무손상|앵커|anchor|기준값|재현', re.IGNORECASE)
CMP_PRE = re.compile(r'[≥≤<>~±]\s*$')                         # 토큰 앞 비교기호(임계·범위 설명)
CMP_POST = re.compile(r'^\s*(?:이상|이하|초과|미만|넘|까지|이내|배\b|p\b|bp)')  # 토큰 뒤 임계/배수/퍼센트포인트


def scan_unlabeled(text):
    """라벨 없는 '진짜 수익률' 토큰을 반환(없으면 None). 문단(빈 줄 구분) 단위.
       ★오탐 예외: 같은 문단에 기준라벨 있으면 통과 · %p(차이값)·임계어(이상/이하/배)·비교기호(≥~±)·인라인코드(` `) 토큰 제외."""
    if not text:
        return None
    for blk in re.split(r'\n\s*\n', text):
        if BASIS.search(blk):                          # 문단에 기준 라벨 있으면 통과
            continue
        for m in BIG_RET.finditer(blk):
            s, e = m.start(), m.end()
            if CMP_POST.match(blk[e:e + 8]):           # 뒤가 '이상/이하/배/p/bp' = 임계·차이값 설명
                continue
            if CMP_PRE.search(blk[max(0, s - 4):s]):   # 앞이 ≥ ≤ ~ ± = 임계·범위 설명
                continue
            if blk[:s].count('`') % 2 == 1:            # 인라인코드 ` ` 안 = 코드/식 인용
                continue
            return m.group(0).strip()
    return None


def last_turn_assistant_text(path):
    """마지막 '진짜 사용자 메시지' 이후의 모든 assistant text 블록을 모아 반환(이번 턴 발화 전체)."""
    try:
        with open(path, encoding='utf-8') as f:
            lines = f.readlines()
    except Exception:
        return None
    out = []
    for ln in reversed(lines):
        ln = ln.strip()
        if not ln:
            continue
        try:
            e = json.loads(ln)
        except Exception:
            continue
        t = e.get('type')
        msg = e.get('message', {}) if isinstance(e.get('message'), dict) else {}
        c = msg.get('content')
        if t == 'user':
            # tool_result(=type user)면 이번 턴의 일부 → 계속. 진짜 사람 메시지면 경계 → 중단.
            is_tool_result = isinstance(c, list) and any(
                isinstance(b, dict) and b.get('type') == 'tool_result' for b in c)
            if is_tool_result:
                continue
            break
        if t == 'assistant':
            got = []
            if isinstance(c, list):
                for b in c:
                    if isinstance(b, dict) and b.get('type') == 'text':
                        got.append(b.get('text', ''))
            elif isinstance(c, str):
                got.append(c)
            if got:
                out.insert(0, '\n'.join(got))
    return '\n\n'.join(out) if out else None


def main():
    try:
        data = json.loads(sys.stdin.read() or '{}')
    except Exception:
        sys.exit(0)
    if data.get('stop_hook_active') is True:   # 무한루프 방지: 이미 차단해 재응답 중이면 통과
        sys.exit(0)
    tp = data.get('transcript_path')
    if not tp:
        sys.exit(0)
    bad = scan_unlabeled(last_turn_assistant_text(tp))
    if bad:
        reason = (
            "수익률 라벨 누락(CLAUDE.md §19 · memory#6 위반): 큰 수익률 토큰 '" + bad + "'에 기준 라벨이 없습니다. "
            "같은 문단에 ⓐ기준(OOS(held-out) / in-sample 상한 / 천장 / 실전 아님) + ⓑ기간(예: 36mo · post-2024 28mo)을 "
            "반드시 명시하세요. 헤드라인 수익률은 OOS만. 천장·레버최적·in-sample 수치를 헤드라인으로 쓰지 말 것. "
            "응답을 고쳐 다시 보내세요.")
        print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=True))
        sys.exit(0)
    sys.exit(0)


if __name__ == '__main__':
    main()
