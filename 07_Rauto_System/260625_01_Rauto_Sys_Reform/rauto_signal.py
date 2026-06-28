# -*- coding: utf-8 -*-
# [rauto_signal.py] ★[1] 매매신호 모듈 v0 — 검증된 신호함수를 '감싸기만'(§8 무수정·§15.1 재구현 금지) (세션 260625_01_Rauto_Sys_Reform).
#   책임 = 진입방향 신호 스트림만 생성. 비용·체결은 모름(RautoCEX 소관). 사이징도 모름(결정모듈 소관).
#   v0는 research 폴더의 검증 신호함수(rev_side)에 의존 → deps 정리 후 engines로 승급.
import sys
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
from dataclasses import dataclass
from blend_opt import rev_side   # 검증된 REV 역추세 방향함수 (재구현 아님)


@dataclass
class SignalStream:
    """봇이 내는 신호 = 봉별 진입방향(+1롱/-1숏/0무) + TF + 메타. 비용·수량 정보 없음(경계)."""
    side: object      # np.ndarray, sig_tf 봉격자 길이
    tf: int
    params: dict


class SignalModule:
    """[1] 매매신호. 1m을 받아 검증 신호함수로 진입방향만 낸다. (장세판별·진입신호 = 여기, 청산·사이징·비용 = 밖)"""

    def __init__(self, rev_tf, q, qwin):
        self.rev_tf, self.q, self.qwin = int(rev_tf), float(q), int(qwin)

    def generate(self, d1m):
        _, side = rev_side(d1m, self.rev_tf, self.q, self.qwin)   # 검증함수 호출
        return SignalStream(side=side, tf=self.rev_tf, params=dict(q=self.q, qwin=self.qwin))
