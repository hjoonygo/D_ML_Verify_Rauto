# ==============================================================================
# 파일명: PautoV80k_BacktestAdapter.py
# 코드길이: 약 240줄 / 내부버전: V8.0k
# 작성일: 2026-04-29
# ==============================================================================
# [정체성]
#   Rauto와 같은 R/P/E 외부 전략 모듈을 Pauto(과거 데이터 백테)에서 호출하는 어댑터.
#   같은 모듈로 실시간 vs 과거 결과 비교 가능 → 챔피언 시스템 핵심 가치.
#
# [사용법]
#   python PautoV80k_BacktestAdapter.py <CSV파일> [R모듈] [P모듈] [E모듈]
#
#   예: python PautoV80k_BacktestAdapter.py Merged_21mo.csv \
#         R_ML_V80k_3balancedTBM_R001 P_ML_V80k_3balancedTBM_R001 E_ML_V80k_3balancedTBM_R001
#
# [Rauto와의 차이점]
#   - 데이터: WebSocket 실시간 → CSV 한 번에 로드
#   - 시간: 실제 1분 → 가속 (즉시 처리)
#   - 청산: 실시간 틱 → 다음 봉 OHLC 검사 (봉 단위 시뮬)
#   - 외부 R/P/E 모듈: 동일 ★
# ==============================================================================
import os
import sys
import time
import json
import importlib
import argparse
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ['PAUTO_BASE_DIR'] = BASE_DIR
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def calc_leverage_from_signal(signal):
    """signal에 leverage 있으면 사용, 없으면 1."""
    return signal.get('leverage', 1)


class PautoV80k_PaperBroker:
    """가상 브로커 — Rauto BotManager와 동일 인터페이스."""
    
    def __init__(self, bot_id='Pauto_Bot', initial_capital=10000.0, cost_pct=0.11):
        self.bot_id = bot_id
        self.capital = initial_capital
        self.wallet_balance = 0.0
        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.cost_pct = cost_pct / 100.0
        
        self.position = {
            "side": "WAIT", "entry_price": 0.0, "amount": 0.0,
            "sl_price": 0.0, "tp_price": 0.0, "one_r_dist": 0.0,
            "is_breakeven_on": False, "is_half_taken": False,
            "highest_price": 0.0, "lowest_price": float('inf'),
            "leverage": 1
        }
        self.trade_history = []

    def on_bar(self, bar_idx, bar, signal=None, exit_signal=None):
        """매 봉마다 호출. 진입/청산 처리."""
        side = self.position.get("side", "WAIT")
        
        # 1. 청산 처리 (포지션 보유 중)
        if side != "WAIT" and exit_signal:
            action = exit_signal.get('action', 'HOLD')
            if 'update_sl' in exit_signal:
                self.position['sl_price'] = exit_signal['update_sl']
                self.position['is_breakeven_on'] = True
            
            if action == 'CLOSE_ALL':
                self._close(bar_idx, bar['close'], exit_signal.get('reason', '일괄청산'))
            elif action == 'CLOSE_HALF':
                self._close_half(bar_idx, bar['close'], exit_signal.get('reason', '반익절'))
        
        # 2. 진입 처리 (포지션 없을 때만)
        elif side == "WAIT" and signal:
            action = signal.get('action', 'WAIT')
            if action in ('OPEN_LONG', 'OPEN_SHORT'):
                self._open(bar_idx, bar, signal)
        
        # 3. 미실현 PnL 갱신 (보유 중이면)
        if self.position['side'] != "WAIT":
            entry = self.position['entry_price']
            if self.position['side'] == 'LONG':
                self.unrealized_pnl = (bar['close'] - entry) * self.position['amount']
                self.position['highest_price'] = max(self.position['highest_price'], bar['high'])
            else:
                self.unrealized_pnl = (entry - bar['close']) * self.position['amount']
                self.position['lowest_price'] = min(self.position['lowest_price'], bar['low'])

    def _open(self, bar_idx, bar, signal):
        side = 'LONG' if signal['action'] == 'OPEN_LONG' else 'SHORT'
        entry = signal.get('entry_price', bar['close'])
        sl = signal.get('sl_price', 0)
        tp = signal.get('tp_price', 0)
        lev = calc_leverage_from_signal(signal)
        notional = self.capital * lev
        amount = notional / entry
        
        self.position = {
            "side": side, "entry_price": entry, "amount": amount,
            "sl_price": sl, "tp_price": tp,
            "one_r_dist": abs(entry - sl),
            "is_breakeven_on": False, "is_half_taken": False,
            "highest_price": bar['high'] if side == 'LONG' else 0,
            "lowest_price": bar['low'] if side == 'SHORT' else float('inf'),
            "leverage": lev
        }
        
        self.trade_history.append({
            'bar_idx': bar_idx,
            'time': bar.get('timestamp', bar_idx),
            'action': signal['action'],
            'price': entry, 'sl': sl, 'tp': tp,
            'leverage': lev, 'env': signal.get('env', '-'),
            'reason': signal.get('reason', ''),
        })

    def _close(self, bar_idx, exit_price, reason):
        # 거래비용 (왕복은 진입+청산이지만 단순화: 청산에만 적용)
        cost = self.position['amount'] * exit_price * self.cost_pct
        pnl = self.unrealized_pnl - cost
        self.realized_pnl += pnl
        self.capital += pnl
        self.unrealized_pnl = 0
        
        # 스윕
        if self.capital > 10000:
            self.wallet_balance += (self.capital - 10000)
            self.capital = 10000
        
        self.trade_history.append({
            'bar_idx': bar_idx, 'time': None,
            'action': 'CLOSE_ALL', 'price': exit_price,
            'pnl': pnl, 'reason': reason,
        })
        
        self.position = {
            "side": "WAIT", "entry_price": 0.0, "amount": 0.0,
            "sl_price": 0.0, "tp_price": 0.0, "one_r_dist": 0.0,
            "is_breakeven_on": False, "is_half_taken": False,
            "highest_price": 0.0, "lowest_price": float('inf'),
            "leverage": 1
        }

    def _close_half(self, bar_idx, exit_price, reason):
        half_amount = self.position['amount'] * 0.5
        cost = half_amount * exit_price * self.cost_pct
        pnl = self.unrealized_pnl * 0.5 - cost
        self.realized_pnl += pnl
        self.capital += pnl
        self.position['amount'] -= half_amount
        self.position['is_half_taken'] = True
        
        if self.capital > 10000:
            self.wallet_balance += (self.capital - 10000)
            self.capital = 10000
        
        self.trade_history.append({
            'bar_idx': bar_idx, 'time': None,
            'action': 'CLOSE_HALF', 'price': exit_price,
            'pnl': pnl, 'reason': reason,
        })


def run_backtest(csv_path, r_module, p_module, e_module,
                 warmup_bars=4500, log_every=10000):
    """동일 R/P/E 모듈로 Pauto 백테."""
    
    # 데이터 로드 (V75 형식: timestamp ms 컬럼)
    print(f"[PautoV80k] 📊 데이터 로드: {csv_path}")
    df = pd.read_csv(csv_path)
    if 'timestamp' in df.columns and not pd.api.types.is_integer_dtype(df['timestamp']):
        df['timestamp'] = pd.to_datetime(df['timestamp']).astype('int64') // 1_000_000
    
    n = len(df)
    print(f"[PautoV80k]    {n:,}봉 / 워밍업: {warmup_bars}")
    
    # 모듈 import
    print(f"[PautoV80k] 🧠 모듈 로드: R={r_module}, P={p_module}, E={e_module}")
    R = importlib.import_module(r_module)
    P = importlib.import_module(p_module)
    E = importlib.import_module(e_module)
    
    # 봇 + 어댑터
    broker = PautoV80k_PaperBroker('Pauto_Bot', initial_capital=10000.0)
    params = {'risk_per_trade_pct': 0.02, 'estimated_leverage': 7}
    
    print(f"[PautoV80k] ▶ 백테 시작 (워밍업 {warmup_bars}봉 후)")
    t0 = time.time()
    
    for i in range(warmup_bars, n):
        sub = df.iloc[max(0, i-warmup_bars):i+1].reset_index(drop=True)
        bar = df.iloc[i]
        
        # 캐시 초기화 (Pauto는 매 봉이 새 시점)
        if hasattr(R, 'reset_cache'): R.reset_cache()
        if hasattr(P, 'reset_cache'): P.reset_cache()
        
        # 1. 환경 판단
        regime = R.determine_regime_kinematics(sub, params)
        
        # 2. 진입 시그널 (포지션 없을 때만)
        signal = None
        if broker.position['side'] == 'WAIT':
            signal = P.get_signal(sub, regime, params)
        
        # 3. 청산 시그널 (포지션 있을 때만)
        exit_signal = None
        if broker.position['side'] != 'WAIT':
            bot_state = {
                "bot_id": broker.bot_id,
                "position": broker.position['side'],
                "entry_price": broker.position['entry_price'],
                "sl_price": broker.position['sl_price'],
                "tp_price": broker.position['tp_price'],
                "one_r_dist": broker.position['one_r_dist'],
                "is_breakeven_on": broker.position['is_breakeven_on'],
                "is_half_taken": broker.position['is_half_taken'],
                "peak_price": (broker.position['highest_price']
                              if broker.position['side'] == 'LONG'
                              else broker.position['lowest_price'])
            }
            # 봉의 high/low로 SL/TP 터치 검사 (틱 시뮬레이션)
            check_prices = [bar['high'], bar['low'], bar['close']]
            for cp in check_prices:
                if broker.position['side'] == 'WAIT': break
                bot_state['peak_price'] = (max(bot_state['peak_price'], cp)
                                           if broker.position['side'] == 'LONG'
                                           else min(bot_state['peak_price'], cp))
                bot_params = dict(params)
                bot_params['estimated_leverage'] = broker.position['leverage']
                exit_signal = E.evaluate_exit(cp, bot_state, bot_params)
                if exit_signal['action'] != 'HOLD':
                    bar_at_exit = dict(bar)
                    bar_at_exit['close'] = cp
                    broker.on_bar(i, bar_at_exit, signal=None, exit_signal=exit_signal)
                    if 'update_sl' in exit_signal:
                        bot_state['sl_price'] = exit_signal['update_sl']
                    if exit_signal['action'] == 'CLOSE_ALL':
                        break
        
        # 진입
        if signal is not None:
            broker.on_bar(i, bar, signal=signal, exit_signal=None)
        
        # 진행 로그
        if i % log_every == 0:
            print(f"[PautoV80k]   봉 {i:,}/{n:,} ({i/n*100:.1f}%) | "
                  f"capital ${broker.capital:.2f} | wallet ${broker.wallet_balance:.2f} | "
                  f"realized ${broker.realized_pnl:+.2f}")
    
    print(f"[PautoV80k] ✅ 완료 ({time.time()-t0:.1f}초)")
    
    # 결과
    total_equity = broker.capital + broker.wallet_balance
    total_pnl = total_equity - 10000
    
    trades = [t for t in broker.trade_history if t['action'].startswith('OPEN')]
    closes = [t for t in broker.trade_history if t['action'].startswith('CLOSE')]
    
    print(f"\n[결과 요약]")
    print(f"  진입: {len(trades)}건 / 청산: {len(closes)}건")
    print(f"  최종 자본: ${broker.capital:,.2f}")
    print(f"  현물 지갑: ${broker.wallet_balance:,.2f}")
    print(f"  총 equity: ${total_equity:,.2f}")
    print(f"  실현 PnL: ${broker.realized_pnl:+,.2f} ({broker.realized_pnl/10000*100:+.2f}%)")
    
    # 거래 로그 저장
    out_csv = os.path.join(BASE_DIR, f"PautoV80k_trades_{r_module}.csv")
    pd.DataFrame(broker.trade_history).to_csv(out_csv, index=False)
    print(f"  거래 로그: {out_csv}")
    
    return broker


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('csv', help='과거 1m 봉 CSV (timestamp/OHLCV/taker_buy_volume)')
    parser.add_argument('--r', default='R_ML_V80k_3balancedTBM_R001')
    parser.add_argument('--p', default='P_ML_V80k_3balancedTBM_R001')
    parser.add_argument('--e', default='E_ML_V80k_3balancedTBM_R001')
    parser.add_argument('--warmup', type=int, default=4500)
    args = parser.parse_args()
    
    if not os.path.exists(args.csv):
        print(f"❌ CSV 파일 없음: {args.csv}")
        sys.exit(1)
    
    run_backtest(args.csv, args.r, args.p, args.e, warmup_bars=args.warmup)
