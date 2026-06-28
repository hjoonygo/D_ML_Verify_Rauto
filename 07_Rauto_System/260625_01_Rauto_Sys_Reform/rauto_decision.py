# -*- coding: utf-8 -*-
# [rauto_decision.py] ★[2] 매매결정 모듈 v0 — 좁은범위(가) (세션 260625_01_Rauto_Sys_Reform).
#   책임(가, 좁게) = 신호 받아 진입/청산 결정 + 사이징(size_pct·lev) + SL/TP 파라미터. 챔피언선발·듀얼k배분 없음(나중).
#   ★검증엔진 gen_trades를 '호출'(재구현 금지 §15.1). 결정모듈은 '어떤 파라미터로 거래를 만들지'만 정함.
#   ★비용은 안 만진다(§7 2레이어): 거래원장을 RautoCEX로 넘기면 거기서 execution_cost 계산.
import sys
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import bt_full as B   # 검증된 거래생성(신호+눌림목+1m체결). 본문 무수정.


class DecisionModule:
    """[2] 매매결정(narrow): 신호 스트림 + 결정 파라미터 → 거래원장(진입/청산 결정). 사이징은 보관해 RautoCEX로 전달."""

    def __init__(self, piv, N, fib, iam, arm, size_pct, lev):
        self.piv, self.N, self.fib, self.iam, self.arm = int(piv), int(N), tuple(fib), float(iam), int(arm)
        self.size_pct, self.lev = float(size_pct), float(lev)   # 사이징(결정) → CEX로 전달

    def decide(self, d1m, fund, signal):
        """검증엔진으로 거래 생성. 청산=피보스텝업(fibstop), 익절·시간청산 off(좁은범위)."""
        T = B.gen_trades(d1m, fund, signal.tf, self.piv, self.N, self.fib, self.iam,
                         er_gate=0.0, ext_side=signal.side, align_pivot=True,
                         use_trend_flip=False, arm_bars=self.arm)   # tp_frac/fib_scale 미사용(가)
        return T
