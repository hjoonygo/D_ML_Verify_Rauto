# -*- coding: utf-8 -*-
# [champion_safety.py] ★챔피언 비상 안전장치 가산점 — 독립 공용모듈 (캡틴 지시2, 2026-06-29 세션 260628_02).
#   목적: 챔피언 선발 시 '비상시 안전장치'를 더 갖춘 봇에 가산점. 1차기준(수익/레짐) 동점이면 가산점 높은 봇을 챔피언.
#   ★무리없는 적용(캡틴): 봇 메타(BOT_REGISTRY 항목)의 '이미 있는 필드'만으로 점수화 → 봇 등록부 수정 불필요.
#   ★무손상: 이 모듈은 '선정 우선순위'만 바꾼다. per_trade pnl·앵커(+1851.6%)엔 절대 손 안 댐.
#   사용: score, items = safety_score(bot_meta); 챔피언 타이브레이커 key=(primary, score).
#
#   판정 근거(이 세션 260628_02 검증):
#     · 강제청산방어: lev≤17 = REVoi 최악역행 -5.10%(Stg4)서 격리마진 강제청산 0.
#     · 급변동흡수 : lev≤14 = 36mo 순간급변동 최악 6.27%(Stg6) < 청산문턱 = 갭관통(청산조차 못함) 0.
#     · 조기익절/DD컷/추세역행차단/레짐적응/저MDD = 봇이 장착한 비상 방어로직.

# (이름, 판정함수(bot_meta), 점수, 설명)  — bot_meta = BOT_REGISTRY 항목 dict
SAFETY_RULES = [
    ("강제청산방어", lambda b: float(b.get("lev", 99)) <= 17.0, 2, "저레버 = 검증 강제청산 0 (REVoi 최악역행 -5.10% < 청산문턱, Stg4)"),
    ("급변동흡수",   lambda b: float(b.get("lev", 99)) <= 14.0, 1, "lev≤14 = 36mo 순간급변동 최악 6.27% 흡수(갭관통 0, Stg6)"),
    ("조기익절",     lambda b: float(b.get("early_tp_pct", 0) or 0) > 0, 1, "조기익절(early_tp) = 이익 빨리 확보·되돌림 방어"),
    ("드로다운컷",   lambda b: bool(b.get("dd_cut")), 1, "자기자본 드로다운 컷(dd_cut) = 누적손실 자동 축소"),
    ("추세역행차단", lambda b: bool(b.get("gate")), 1, "추세역행 진입게이트(gate) = 지속추세 반대 진입 차단"),
    ("레짐적응",     lambda b: float(b.get("regime_factor", 1.0) or 1.0) > 1.0, 1, "레짐 적응(regime_factor) = 저변동봉 스텝 타이트"),
    ("저MDD방어",    lambda b: float(b.get("mdd", -99)) >= -15.0, 1, "검증 MDD ≥ -15% = 드로다운 자체가 얕음"),
]
MAX_SCORE = sum(r[2] for r in SAFETY_RULES)


def safety_score(bot_meta):
    """봇 메타(BOT_REGISTRY 항목) → (총점, 항목리스트). 항목 = {name, got(bool), pts, why}.
       got=True 항목만 가산. 어떤 메타든 안전하게(필드 없으면 미충족)."""
    b = bot_meta or {}
    items = []
    total = 0
    for name, test, pts, why in SAFETY_RULES:
        try:
            got = bool(test(b))
        except Exception:
            got = False
        if got:
            total += pts
        items.append({"name": name, "got": got, "pts": pts, "why": why})
    return total, items


def label(bot_meta):
    """대시보드용 한 줄 요약: '안전점수 4/8 [강제청산방어·조기익절·저MDD방어]'."""
    total, items = safety_score(bot_meta)
    got = [it["name"] for it in items if it["got"]]
    return f"안전점수 {total}/{MAX_SCORE} [{'·'.join(got) if got else '없음'}]"


if __name__ == "__main__":
    # 자가테스트: BOT_REGISTRY 예시
    tests = [
        {"name": "RevoiSafe@ETF", "lev": 15.0, "early_tp_pct": 0.01, "mdd": -14.8},
        {"name": "REVoi@ETF", "lev": 3.0, "early_tp_pct": 0.01, "mdd": -11.2},
        {"name": "M0천장", "lev": 16.0, "regime_factor": 1.4, "mdd": -70.1},
        {"name": "결합R+P80", "lev": 6.0, "gate": True, "dd_cut": [-0.08, 0.5], "mdd": -18.6},
    ]
    for t in tests:
        s, _ = safety_score(t)
        print(f"{t['name']:>16}: {label(t)}")
