# [파일명] bot_trendstack_impatient_king.py
# 코드길이: 약 75줄 / 내부버전: impatient-king-v1 ("성급왕" = 성급 + 1분 인트라바 손절가드)
# ─────────────────────────────────────────────────────────────────────────
# [목적] 성급TS(TrendStackImpatientBot)에 '1분 인트라바 손절 가드'를 더한 변종.
#   ★유일 차이 = 손절 시점: 기존/성급은 1% 손절을 7H봉 마감에만 판정 → 손절선을 뚫고도
#     그 봉 종가(추세전환 청산)까지 끌려가 -3~7% 큰 손실이 나는 26건(36mo)이 있었다.
#     성급왕은 보유 중 매 1분 on_bar에서 현재 SL을 검사해, 터치 즉시 손절(추세전환보다 우선).
#   그 외(진입=피벗대기 제거, 피보 트레일, OI무덤·ER0.45 게이트, OPVnN 사이징, 업트렌드숏컷)
#   전부 성급과 1:1 동일.
# [무수정 원칙] §8 해시락 엔진/봇은 한 글자도 안 건드린다. TrendStackImpatientBot을 상속해
#   on_bar만 확장(가드 추가). _step/_close_7h/_compute_size/replay_7h는 부모 것 그대로.
# [검증] 36개월 A/B(paper_engine, 단독k1.0·lev22·스톱슬립5bp 공정비교):
#   성급 +5791%/MDD-19.6% → 성급왕 +7087%/MDD-19.4% (복리 +22%, 상승장 +12%p·롱 +13%p 개선).
#   ★라이브 채택은 CPCV 표준6 + 워크포워드 OOS 통과 후(§5.7/§9).
# [정직 공지] SL 체결가는 SL 레벨로 기록(슬리피지는 실행/페이퍼엔진 담당). 가드는 진입봉 다음
#   7H버킷부터 작동(백테 i>entry_i와 동일). 인트라바 청산 분(分)은 7H봉 누적서 1분 누락(무시가능).
# ─────────────────────────────────────────────────────────────────────────
import numpy as np
import pandas as pd
import trendstack_signal_engine as E
from bot_trendstack_signal import BUCKET_7H
from bot_trendstack_impatient import TrendStackImpatientBot
from rauto_contract import Signal, Action, Side


class TrendStackImpatientKingBot(TrendStackImpatientBot):
    META = {"name": "TrendStack_KING", "version": "impatient-king-v1",
            "timeframe": "7h + 1m SL guard", "needs": ["oi", "volume"],
            "engine": "SpTrd_Fib_V1_Champion(1:1)",
            "sizing": "POC/dev(OPVnN)+feat_struct8, self-contained",
            "fork": "impatient entry + 1m intrabar SL guard"}

    def on_init(self, ctx=None):
        super().on_init(ctx)
        self._entry_bucket = None     # 진입 시점 7H 버킷(가드는 그 봉 이후부터)
        self._entry_ms = None         # 진입 분(分) 에포크(펀딩 계산용)
        self._cooldown_bucket = None  # 인트라바 손절난 7H 버킷 → 그 봉 마감엔 재진입 금지(난타 방지)

    # ── 쿨다운: 인트라바 손절난 봉의 마감에서 재진입 취소(같은봉 난타 제거) ──
    #    replay(batch)엔 인트라바 청산이 없어 _cooldown_bucket=None → 영향 없음(동치 보존).
    def _step(self, i, arr, sig, dz_oi, eh):
        ev = super()._step(i, arr, sig, dz_oi, eh)
        if ev is not None and ev[0] == 'ENTER' and self._cooldown_bucket is not None:
            bucket = int(pd.Timestamp(arr['idx'][i]).value // 60_000_000_000) // BUCKET_7H
            if bucket == self._cooldown_bucket:
                self.pos = 0; self.entry_price = np.nan; self.entry_i = -1
                self.sl = np.nan; self.pb = 0
                return None
        return ev

    def on_bar(self, market):
        # ── 1분 인트라바 손절 가드 (보유 중·SL설정·진입봉 다음 버킷부터) ──
        if self.pos != 0 and not np.isnan(self.sl) and self._entry_bucket is not None:
            cur_b7 = self._bucket(market.ts, BUCKET_7H)
            touched = (self.pos == 1 and market.l <= self.sl) or (self.pos == -1 and market.h >= self.sl)
            if cur_b7 >= self._entry_bucket and touched:
                ms = int(pd.Timestamp(market.ts).value // 60_000_000_000)   # 분 단위 에포크
                held8 = max(0, (ms - self._entry_ms) // 480) if self._entry_ms else 0
                fp = E.FUND_8H * held8
                R = self.pos * (self.sl - self.entry_price) / self.entry_price * E.LEVERAGE - E.COST - fp
                et = self._h7[self.entry_i][0] if (0 <= self.entry_i < len(self._h7)) else pd.Timestamp(market.ts)
                self._trades.append({'entry_t': et, 'exit_t': pd.Timestamp(market.ts), 'side': self.pos,
                                     'entry': self.entry_price, 'exit': float(self.sl), 'R': R,
                                     'reason': 'sl_intrabar', 'bars': 0, 'fund': fp,
                                     'year': pd.Timestamp(market.ts).year})
                self.pos = 0; self.sl = np.nan; self.pb = 0; self._entry_bucket = None
                self._cooldown_bucket = cur_b7   # 이 봉 마감엔 재진입 금지(난타 방지)
                return Signal(Action.EXIT, side=Side.FLAT, reason='sl_intrabar')
        # ── 평소: 부모(성급) on_bar = 7H/4H 누적 + 7H마감 _step ──
        sig = super().on_bar(market)
        if sig is not None and sig.action == Action.ENTER:
            self._entry_bucket = self._bucket(market.ts, BUCKET_7H)
            self._entry_ms = int(pd.Timestamp(market.ts).value // 60_000_000_000)
        return sig
