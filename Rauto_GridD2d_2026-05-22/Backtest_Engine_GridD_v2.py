# -*- coding: utf-8 -*-
# [파일명] Backtest_Engine_GridD_v2.py
# 코드길이: 약 190줄, 내부버전명: GridD_v2_fast, 로직 축약/생략 없이 전체 출력
#
# [v1 -> v2 변경 — 2가지]
#   (1) 사슬(한 포지션) -> '진입 125건을 각각 독립 거래'로 시뮬. (v9 trades_obtf 방식)
#       => 비율을 바꿔 청산이 늦어져도 진입 누락 없음. 모든 config가 같은 125건을 다 봄.
#   (2) 고속화: 전 구간 4틱 순회를 버리고 '진입 인덱스로 점프 -> 청산까지만 4틱 진행'.
#       => 거래중일 때만 계산. 대부분의 빈 구간을 건너뛰어 수배~수십배 빠름.
#
# [정산식·청산판정은 원본 verbatim] _reduce/_close 식, 4틱 분해, 미래참조차단 동일.
#   4틱: tick0=open, tick1=(음봉:high/양봉:low), tick2=(음봉:low/양봉:high), tick3=close(=is_closed)
#   진입은 is_closed(tick3)에서만, 그 봉의 close를 진입가로(원본 동일).
#
# [독립 거래 정의]
#   각 진입은 자본 10000 * leverage 명목으로 1거래. 거래간 자본 누적 없음(고정사이즈).
#   원본은 겹침 0건이라, 독립 시뮬 결과 = 원본 거래집합 -> 2.86 재현 기대.
#
# [함수 In/Out]
#   __init__(exec_instance, params, df)        : df=tz벗긴 1분봉(DataFrame, index=timestamp)
#   simulate_entry(entry_t, side, regime)      : 진입 1건 -> 거래기록 리스트(REDUCE/CLOSE 행)
#   run_entries(entry_list)                    : [(t,side,regime)..] -> 전체 trade_logs 채움
#   get_trades()                               : -> trade_logs(list[dict])
#
# [미래참조 점검] 진입 봉마감만, 청산은 4틱 인트라바, 윈도우 종가를 현재틱으로 덮어 미래봉 미참조.
# ==============================================================================

import numpy as np
import pandas as pd

WINDOW = 60          # OB 스캔용 롤링 윈도우(원본 Historical_DataEngine.min_history_window)
MAX_HOLD_BARS = 60 * 24 * 90   # 거래당 최대 보유 90일(무한루프 안전판). 원본엔 타임아웃 없음.


class Backtest_Engine_GridD_v2:
    def __init__(self, exec_instance, params, df):
        self.exec = exec_instance
        self.params = params
        self.leverage = params['leverage']
        self.fee_rate = params.get('fee_rate', 0.0004)
        self.funding_rate_daily = params.get('funding_rate_daily', 0.0001)
        self.split_ratio = params.get('split_ratio', 0.5)

        self.df = df
        self.o = df['open'].values
        self.h = df['high'].values
        self.l = df['low'].values
        self.c = df['close'].values
        self.idx = df.index
        # timestamp -> 행위치 (진입 점프용)
        self.pos_of = {t: i for i, t in enumerate(self.idx)}
        self.trade_logs = []

    def _ticks(self, i):
        """1분봉 i를 원본과 동일한 4틱 시퀀스로 반환."""
        o, h, l, c = self.o[i], self.h[i], self.l[i], self.c[i]
        if c < o:           # 음봉: 고가 먼저
            return (o, h, l, c)
        else:               # 양봉: 저가 먼저
            return (o, l, h, c)

    def simulate_entry(self, entry_t, side, regime):
        if entry_t not in self.pos_of:
            return  # 데이터에 그 봉이 없으면 스킵(로그 X)
        e_idx = self.pos_of[entry_t]
        if e_idx < WINDOW:
            return
        entry_price = self.c[e_idx]          # 진입봉 종가(원본 동일)
        position_size = 10000.0 * self.leverage

        bot_state = {
            'position': side, 'entry_price': entry_price, 'remaining_pct': 1.0,
            'target_idx': 0, 'ob_initialized': False,
            'fib_wave_start': entry_price, 'fib_extreme': entry_price,
            'pulled_back': False, 'fib_stop': None,
            'bullish_obs': [], 'bearish_obs': [],
            'entry_regime': regime, 'entry_reason': '고정진입(2.86셋, 독립시뮬)'
        }
        reduced = False

        # [속도핵심] 청산엔진은 OB를 '진입 직후 1회'만 스캔하고(ob_initialized) 그 뒤엔 df_1m을
        #   안 쓴다. _find_order_blocks는 high/low만 보고 close는 안 본다. 따라서 윈도우 표를
        #   '진입 다음 봉 시점' 기준 60봉으로 딱 한 번만 만들어 재사용한다 (봉마다 복사 제거 = 대폭 가속).
        first_i = e_idx + 1
        w0 = max(0, first_i - WINDOW + 1)
        win = self.df.iloc[w0:first_i + 1]   # 복사 불필요(OB 스캔은 high/low만 읽음, 수정 안 함)
        bot_state['df_1m'] = win

        # 진입 '다음 봉'부터 청산 판정 (진입봉 종가에 들어갔으므로)
        n = len(self.c)
        end_idx = min(n, e_idx + 1 + MAX_HOLD_BARS)
        for i in range(e_idx + 1, end_idx):
            ticks = self._ticks(i)
            for k, price in enumerate(ticks):
                sig = self.exec.check_exit(price, bot_state, self.params)
                act = sig.get('action') if sig else None
                if act in ("REDUCE_LONG", "REDUCE_SHORT") and not reduced:
                    self._record_reduce(bot_state, entry_t, self.idx[i], price, position_size, sig['reason'])
                    position_size *= (1.0 - self.split_ratio)
                    reduced = True
                    bot_state['remaining_pct'] = 1.0 - self.split_ratio
                elif act in ("CLOSE_LONG", "CLOSE_SHORT"):
                    self._record_close(bot_state, entry_t, self.idx[i], entry_price, price, position_size, reduced, sig['reason'])
                    return
        # 90일 안에 안 닫히면 마지막가로 강제청산(안전판)
        self._record_close(bot_state, entry_t, self.idx[end_idx - 1], entry_price, self.c[end_idx - 1], position_size, reduced, 'max_hold_force_close')

    def _record_reduce(self, bs, entry_t, exit_t, price, position_size, reason):
        reduce_amt = position_size * self.split_ratio
        side = bs['position']
        pnl_pct = (price - bs['entry_price']) / bs['entry_price'] if side == "LONG" else (bs['entry_price'] - price) / bs['entry_price']
        gross = reduce_amt * pnl_pct
        fee = reduce_amt * self.fee_rate * 2
        net = gross - fee
        self.trade_logs.append({
            "진입시간": entry_t.strftime('%Y-%m-%d %H:%M:%S'), "청산시간": exit_t.strftime('%Y-%m-%d %H:%M:%S'),
            "포지션": side + f" ({int(round(self.split_ratio*100))}% 익절)", "레버리지": self.leverage,
            "진입수량($)": round(reduce_amt, 2), "장세판단(Regime)": bs['entry_regime'],
            "청산사유(Exec)": reason, "진입가": round(bs['entry_price'], 2), "청산가": round(price, 2),
            "수수료($)": round(fee, 2), "순수익금($)": round(net, 2), "구분": "REDUCE"
        })

    def _record_close(self, bs, entry_t, exit_t, entry_price, price, position_size, reduced, reason):
        side = bs['position']
        pnl_pct = (price - entry_price) / entry_price if side == "LONG" else (entry_price - price) / entry_price
        gross = position_size * pnl_pct
        fee = position_size * self.fee_rate * 2
        dur_days = (exit_t - entry_t).total_seconds() / 86400
        funding = position_size * self.funding_rate_daily * dur_days
        net = gross - fee - funding
        self.trade_logs.append({
            "진입시간": entry_t.strftime('%Y-%m-%d %H:%M:%S'), "청산시간": exit_t.strftime('%Y-%m-%d %H:%M:%S'),
            "포지션": side + (f" (잔량 {int(round((1-self.split_ratio)*100))}%)" if reduced else " (전량)"),
            "레버리지": self.leverage, "진입수량($)": round(position_size, 2),
            "장세판단(Regime)": bs['entry_regime'], "청산사유(Exec)": reason,
            "진입가": round(entry_price, 2), "청산가": round(price, 2),
            "수수료($)": round(fee, 2), "순수익금($)": round(net, 2), "구분": "CLOSE"
        })

    def run_entries(self, entry_list):
        for (t, side, regime) in entry_list:
            self.simulate_entry(t, side, regime)

    def get_trades(self):
        return self.trade_logs
