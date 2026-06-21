# -*- coding: utf-8 -*-
# [bot_trendstack_fastfail.py] 비대칭 Fast-Fail 플러그인 (레버1 검증용)
# ─────────────────────────────────────────────────────────────────────────
# [목적] 챗GPT 5.5/제미나이 토론의 "비대칭 전이필터(상승은 신중, 하락은 Fast-Fail)"를
#        우리 검증엔진 위에서 실제로 백테 검증하기 위한 상속 래퍼.
#   ① 롱 보유 중 4H SMC regime(self._feat)이 'downtrend'로 N봉 확정 → 조기청산(중력=빠르게)
#   ② 숏 보유 중 'uptrend' → 더 인내(비대칭: 다른/큰 임계 또는 비활성)
#   ③ 역행 regime 방향 진입은 veto(Halt-entry, 휩쏘 재진입 churn 방지)
# [무수정 원칙 §1/§15] §8 해시락 엔진/봇 한 글자도 안 건드림. King을 상속해 _step만 래핑:
#   super()._step()이 검증된 진입·trend_flip·SL·피보트레일·인트라바가드 전부 그대로 수행하고,
#   본 클래스는 그 결과(ev) 위에 (a)역행진입 veto (b)조기청산만 덧댐.
#   → 모든 파라미터 OFF(None/False)면 King과 100% 동일(동치 자가검증, §15 관문2).
# [feat 수명주기] self._feat = 4H _close_4h에서 RG.feat_struct_of(shift=swing_len=8) 지연확정.
#   라이브/ledger(1m on_bar) 경로에서만 갱신됨(replay_7h엔 4H누적 없음). ledger 생성은 on_bar라 OK.
# [R 산식] 조기청산 R = side*(close[i]-entry)/entry*E.LEVERAGE - E.COST - fund  (trend_flip와 동일식).
#   체결가=7H마감 close(시장결정 청산이라 trend_flip과 동일 취급) → 5bp 스톱슬립 미적용(sl 전용).
# ─────────────────────────────────────────────────────────────────────────
import numpy as np
import pandas as pd
import trendstack_signal_engine as E
from bot_trendstack_impatient_king import TrendStackImpatientKingBot


class TrendStackFastFailBot(TrendStackImpatientKingBot):
    META = {"name": "TrendStack_FASTFAIL", "version": "ff-v1",
            "timeframe": "7h + 1m SL guard + 4H regime fast-fail",
            "engine": "SpTrd_Fib_V1_Champion(1:1)",
            "fork": "king + asymmetric regime early-exit & halt-entry"}

    # 파라미터(기본 OFF = King 동치). 러너가 인스턴스에 직접 세팅.
    FF_LONG = None     # 롱 조기청산: 'downtrend' 연속 N봉 확정 시 청산. None=비활성
    FF_SHORT = None    # 숏 조기청산: 'uptrend' 연속 N봉 확정 시 청산. None=비활성
    HALT_ENTRY = False # 역행 regime 방향 진입 veto

    def on_init(self, ctx=None):
        super().on_init(ctx)
        self._ff_long = self.FF_LONG
        self._ff_short = self.FF_SHORT
        self._ff_halt = self.HALT_ENTRY
        self._ff_cnt = 0   # 현 포지션의 연속 역행(4H adverse) 7H봉 수

    def _adverse(self, side):
        # 보유 방향에 불리한 4H regime인가? 롱↔downtrend, 숏↔uptrend
        if side == 1:
            return self._feat == "downtrend"
        if side == -1:
            return self._feat == "uptrend"
        return False

    def _ff_thr(self, side):
        return self._ff_long if side == 1 else self._ff_short

    def _step(self, i, arr, sig, dz_oi, eh):
        held_side = self.pos
        ev = super()._step(i, arr, sig, dz_oi, eh)

        # ── (a) 역행 regime 방향 진입 veto (Halt) ──
        if ev is not None and ev[0] == 'ENTER':
            d = ev[1]
            if self._ff_halt and self._adverse(d):
                # super()가 막 세팅한 진입 취소(원장 미기록 — _step ENTER는 아직 _trades에 안 들어감)
                self.pos = 0; self.entry_price = np.nan; self.entry_i = -1
                self.sl = np.nan; self.pb = 0
                self._ff_cnt = 0
                return None
            self._ff_cnt = 0   # 새 진입 → 카운터 리셋
            return ev

        # super()가 청산했거나(EXIT) 진입중(ENTER 위에서 처리) 외의 경우만 조기청산 검토
        if ev is not None:
            # EXIT 등은 그대로 통과(이미 청산됨 → 카운터 리셋)
            self._ff_cnt = 0
            return ev

        # ── (b) 보유 지속(ev is None) 중 비대칭 조기청산 ──
        if self.pos != 0:
            thr = self._ff_thr(self.pos)
            if self._adverse(self.pos):
                self._ff_cnt += 1
            else:
                self._ff_cnt = 0
            if thr is not None and self._ff_cnt >= thr:
                close = arr['c']; idx = arr['idx']
                px = close[i]
                R = self.pos * (px - self.entry_price) / self.entry_price * E.LEVERAGE
                held8 = int(np.floor(eh[i] / 8.0) - np.floor(eh[self.entry_i] / 8.0))
                fp = E.FUND_8H * max(0, held8)
                R = R - E.COST - fp
                self._trades.append({'entry_t': idx[self.entry_i], 'exit_t': idx[i], 'side': self.pos,
                                     'entry': self.entry_price, 'exit': px, 'R': R, 'reason': 'ff',
                                     'bars': i - self.entry_i, 'fund': fp, 'year': idx[i].year})
                self.pos = 0; self.sl = np.nan; self.pb = 0; self._entry_bucket = None
                self._ff_cnt = 0
                return 'EXIT', 'ff'
        return None
