# [파일명] champion.py
# 코드길이: 약 110줄 / 내부버전: champion_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 챔피언시스템의 두 부품:
#        (1) Scorer  — 봇별·레짐별 실시간 성적(복리잔고로 Calmar) 집계
#        (2) ChampionSelector — 현재 레짐에서 최고 Calmar 봇을 챔피언으로 선택하되,
#            히스테리시스(마진 미달 시 교체 안 함) + ㉡(보유중 교체금지: flat일 때만 교체).
#        ※ 1봇만 로드되면 자동으로 그 봇이 챔피언(최소 챔피언).
# [Lookahead] 점수는 '이미 청산된' 거래 손익만 누적(미래참조 없음). 선택은 과거성적 기반.
# ── 사용 파일 ── 없음(표준 라이브러리만)
# ── 함수 In/Out ──
#  Scorer()                     In: -                → Out: 스코어러
#   .update(slot,regime,p)      In: 슬롯·레짐·1거래손익p → Out: 해당 (슬롯,레짐) 복리잔고/peak/MDD/n 갱신
#   .calmar(slot,regime)        In: 슬롯·레짐         → Out: Calmar(=수익%/|MDD%|), 표본부족시 None
#   .table()                    In: -                → Out: {(slot,regime): {ret,mdd,cal,n}}
#  ChampionSelector(margin,min_n) In: 히스테리시스마진·최소표본 → Out: 셀렉터
#   .select(cands,regime,scorer,current,flat) In: 후보슬롯들·레짐·스코어러·현챔피언·flat여부
#                                              → Out: 챔피언 슬롯 (교체조건 미충족/비flat시 현챔피언 유지)
# ── 상수 ── 기본 margin=0.15(15%) min_n=5
# ─────────────────────────────────────────────────────────────────────────
from typing import Optional, List, Dict, Tuple


class Scorer:
    """봇별·레짐별 복리잔고를 추적해 Calmar를 산출(START=100 정규화)."""
    START = 100.0

    def __init__(self):
        self.stat: Dict[Tuple[int, str], Dict[str, float]] = {}

    def _key(self, slot: int, regime: str):
        return (slot, regime if regime is not None else "NA")

    def update(self, slot: int, regime: str, p: float) -> None:
        k = self._key(slot, regime)
        s = self.stat.get(k)
        if s is None:
            s = {"bal": self.START, "peak": self.START, "mdd": 0.0, "n": 0}
            self.stat[k] = s
        s["bal"] *= (1.0 + p)
        if s["bal"] > s["peak"]:
            s["peak"] = s["bal"]
        dd = s["bal"] / s["peak"] - 1.0
        if dd < s["mdd"]:
            s["mdd"] = dd
        s["n"] += 1

    def calmar(self, slot: int, regime: str) -> Optional[float]:
        s = self.stat.get(self._key(slot, regime))
        if s is None or s["n"] == 0:
            return None
        ret = (s["bal"] / self.START - 1.0) * 100.0
        if s["mdd"] < 0:
            return ret / abs(s["mdd"] * 100.0)
        return float("inf") if ret > 0 else 0.0

    def table(self) -> Dict[Tuple[int, str], Dict[str, float]]:
        out = {}
        for k, s in self.stat.items():
            ret = (s["bal"] / self.START - 1.0) * 100.0
            mdd = s["mdd"] * 100.0
            cal = (ret / abs(mdd)) if s["mdd"] < 0 else float("nan")
            out[k] = {"ret": round(ret, 2), "mdd": round(mdd, 2),
                      "cal": round(cal, 2) if cal == cal else None, "n": s["n"]}
        return out


class ChampionSelector:
    """히스테리시스 + flat-only 교체. 1봇이면 자동 챔피언."""
    def __init__(self, margin: float = 0.15, min_n: int = 5):
        self.margin = margin      # 챌린저가 챔피언을 이만큼(상대%) 넘어야 교체
        self.min_n = min_n        # 교체 판단 최소 표본

    def select(self, cands: List[int], regime: str, scorer: Scorer,
               current: Optional[int], flat: bool) -> Optional[int]:
        if not cands:
            return current
        if current is None or current not in cands:
            return cands[0]                       # 최초/유실 → 첫 슬롯(1봇이면 자동챔피언)
        if not flat:
            return current                        # ㉡ 보유중엔 교체 금지
        cur_cal = scorer.calmar(current, regime)
        best, best_cal = current, (cur_cal if cur_cal is not None else -1e9)
        for c in cands:
            if c == current:
                continue
            cal = scorer.calmar(c, regime)
            s = scorer.stat.get(scorer._key(c, regime))
            if cal is None or s is None or s["n"] < self.min_n:
                continue
            need = (best_cal * (1.0 + self.margin)) if best_cal > 0 else self.margin
            if cal > need:                        # 히스테리시스 마진 초과시에만 교체
                best, best_cal = c, cal
        return best
