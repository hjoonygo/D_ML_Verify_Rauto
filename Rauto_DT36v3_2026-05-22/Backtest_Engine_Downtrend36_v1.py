# -*- coding: utf-8 -*-
# [파일명] Backtest_Engine_Downtrend36_v1.py
# 코드길이: 약 180줄, 내부버전명: DT36_v1, 로직 축약/생략 없이 전체 출력
#
# [목적]
#   36개월 1분봉(라벨포함)에서, '하락장 라벨 구간'에만 기계적 SHORT를 순차 진입시켜
#   검증 청산엔진(혁신1 ON)이 하락장 전반에서 엣지를 내는지 측정.
#   진입 방향은 동전던지기 전제 -> 청산엔진 엣지만 본다.
#
# [미래참조(Lookahead) 안전]
#   - 하락장 정의 = feat_struct_8 (실시간 안전 라벨: 스윙 확정지연 shift 반영). label_smc(사후) 아님.
#   - 진입은 봉마감 시점, 청산은 4틱 인트라바, OB 스캔 진입 1회. 미래봉 미참조.
#
# [속도 최적화]
#   (1) 순차 1포지션: 거래 비겹침 -> 한 봉을 두 번 시뮬 안 함.
#   (2) 포지션 없을 때 '다음 하락장 봉'으로 즉시 점프(searchsorted) -> 비하락 73% 구간 안 훑음.
#   (3) 윈도우(60봉)는 진입당 1회 생성, 봉마다 복사 안 함.
#
# [함수 In/Out]
#   __init__(exec_instance, params, df, regime_col)
#       df: 1m OHLC + regime_col(문자열 라벨) 포함 DataFrame(index=timestamp)
#   run() : 순차 시뮬 -> self.trades(list[dict]) 채움, 청산봉 인덱스로 진행
#   get_trades() -> list[dict]
# ==============================================================================

import numpy as np
import pandas as pd

WINDOW = 60
MAX_HOLD_BARS = 60 * 24 * 90   # 90일 안전판


class Backtest_Engine_Downtrend36_v1:
    def __init__(self, exec_instance, params, df, regime_col='feat_struct_8', down_value='downtrend'):
        self.exec = exec_instance
        self.params = params
        self.leverage = params['leverage']
        self.fee_rate = params.get('fee_rate', 0.0004)
        self.funding_rate_daily = params.get('funding_rate_daily', 0.0001)
        self.split_ratio = params.get('split_ratio', 0.5)
        self.df = df
        self.o = df['open'].values; self.h = df['high'].values
        self.l = df['low'].values;  self.c = df['close'].values
        self.idx = df.index
        reg = df[regime_col].astype(str).values
        self.is_down = (reg == down_value)
        self.down_idx = np.where(self.is_down)[0]   # 하락장 봉 위치(점프용)
        self.trades = []

    def _ticks(self, i):
        o, h, l, c = self.o[i], self.h[i], self.l[i], self.c[i]
        return (o, h, l, c) if c < o else (o, l, h, c)

    def _next_down_after(self, idx):
        """idx 이상에서 첫 하락장 봉 위치. 없으면 None."""
        p = np.searchsorted(self.down_idx, idx, side='left')
        return int(self.down_idx[p]) if p < len(self.down_idx) else None

    def run(self):
        n = len(self.c)
        cur = WINDOW + 1                       # 워밍업 확보 후 시작
        while True:
            e_idx = self._next_down_after(cur)  # 다음 하락장 봉으로 점프
            if e_idx is None or e_idx >= n - 1:
                break
            exit_idx = self._sim_short(e_idx)
            cur = max(exit_idx + 1, e_idx + 1)  # 청산 다음 봉부터 재탐색

    def _sim_short(self, e_idx):
        """e_idx 종가에 SHORT 진입 -> 청산까지 4틱 시뮬. 청산 봉 인덱스 반환."""
        entry_price = self.c[e_idx]
        position_size = 10000.0 * self.leverage
        bs = {'position': 'SHORT', 'entry_price': entry_price, 'remaining_pct': 1.0,
              'target_idx': 0, 'ob_initialized': False, 'fib_wave_start': entry_price,
              'fib_extreme': entry_price, 'pulled_back': False, 'fib_stop': None,
              'bullish_obs': [], 'bearish_obs': [], 'entry_regime': 'downtrend',
              'entry_reason': '하락장 기계적 SHORT'}
        first_i = e_idx + 1
        w0 = max(0, first_i - WINDOW + 1)
        bs['df_1m'] = self.df.iloc[w0:first_i + 1]   # 윈도우 1회
        reduced = False
        n = len(self.c)
        end_idx = min(n, e_idx + 1 + MAX_HOLD_BARS)
        for i in range(e_idx + 1, end_idx):
            for price in self._ticks(i):
                sig = self.exec.check_exit(price, bs, self.params)
                act = sig.get('action') if sig else None
                if act == "REDUCE_SHORT" and not reduced:
                    self._rec(bs, e_idx, i, price, position_size, sig['reason'], 'REDUCE')
                    position_size *= (1.0 - self.split_ratio)
                    reduced = True; bs['remaining_pct'] = 1.0 - self.split_ratio
                elif act == "CLOSE_SHORT":
                    self._rec(bs, e_idx, i, price, position_size, sig['reason'], 'CLOSE', reduced)
                    return i
        self._rec(bs, e_idx, end_idx - 1, self.c[end_idx - 1], position_size, 'max_hold_force', 'CLOSE', reduced)
        return end_idx - 1

    def _rec(self, bs, e_idx, x_idx, price, position_size, reason, kind, reduced=False):
        et = self.idx[e_idx]; xt = self.idx[x_idx]; entry = bs['entry_price']
        if kind == 'REDUCE':
            amt = position_size * self.split_ratio
            pnl_pct = (entry - price) / entry
            gross = amt * pnl_pct; fee = amt * self.fee_rate * 2; net = gross - fee
            size = amt; tag = f"SHORT ({int(round(self.split_ratio*100))}% 익절)"
        else:
            pnl_pct = (entry - price) / entry
            gross = position_size * pnl_pct; fee = position_size * self.fee_rate * 2
            dur = (xt - et).total_seconds() / 86400
            funding = position_size * self.funding_rate_daily * dur
            net = gross - fee - funding
            size = position_size
            tag = f"SHORT (잔량 {int(round((1-self.split_ratio)*100))}%)" if reduced else "SHORT (전량)"
        self.trades.append({
            "진입시간": et.strftime('%Y-%m-%d %H:%M:%S'), "청산시간": xt.strftime('%Y-%m-%d %H:%M:%S'),
            "연도": et.year, "포지션": tag, "진입수량($)": round(size, 2),
            "청산사유(Exec)": reason, "진입가": round(entry, 2), "청산가": round(price, 2),
            "순수익금($)": round(net, 2), "구분": kind
        })

    def get_trades(self):
        return self.trades
