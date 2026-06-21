"""
[파일명] test_pauto_v76_compounding.py
코드길이: 약 200줄, 내부버전 v7.6
목적: 복리 변경(①③④) 검증 — 5개 시나리오로 capital/position_size 추적 확인
ML 모델 없이 mock 환경에서 핵심 로직만 격리 테스트

In: 없음
Out: 콘솔 출력 (5개 케이스 PASS/FAIL)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Mock — Backtest_Engine_PautoV75를 실제 데이터 없이 검증할 환경 구성
# 핵심 메서드만 격리 테스트 (run_simulation 전체는 ML 모델 필요)

class MockPautoEngine:
    """Backtest_Engine_PautoV75의 복리 관련 메서드만 추출 — 검증용"""
    def __init__(self):
        self.initial_capital = 10000.0
        self.capital = self.initial_capital
        self.spot_wallet = 0.0
        self.fee_rate = 0.0004
        self.funding_rate_daily = 0.0001
        self.position = "WAIT"
        self.entry_price = 0.0
        self.entry_time = None
        self.position_size = 0.0
        self.last_price = 0.0
        self.trade_logs = []
        self.bot_state = {}
        self.stats = {
            'LONG':  {'trades':0,'wins':0,'fees':0.0,'net_profit':0.0,'return_pct_sum':0.0},
            'SHORT': {'trades':0,'wins':0,'fees':0.0,'net_profit':0.0,'return_pct_sum':0.0}
        }
        self.params = {'leverage': 5}

    def open_position(self, side, price, time):
        """진입 — 현재 capital × lev로 명목가 결정 (복리 효과)"""
        self.position = side
        self.entry_price = price
        self.entry_time = time
        self.position_size = self.capital * self.params['leverage']
        self.bot_state = {
            'position': self.position, 'entry_price': price, 'remaining_pct': 1.0,
            'target_idx': 0, 'ob_initialized': False, 'fib_wave_start': price,
            'fib_extreme': price, 'pulled_back': False, 'fib_stop': None,
            'bullish_obs': [], 'bearish_obs': [],
            'entry_regime': 'TEST', 'entry_reason': 'TEST'
        }

    def _reduce_position(self, current_price, current_time, exit_reason):
        """50% 분할 익절 — 원본 코드 그대로"""
        reduce_amt = self.position_size * 0.5
        pnl_pct = (current_price - self.entry_price) / self.entry_price if self.position == "LONG" else (self.entry_price - current_price) / self.entry_price
        gross_pnl = reduce_amt * pnl_pct
        fee_cost = reduce_amt * self.fee_rate * 2
        net_pnl = gross_pnl - fee_cost
        self.trade_logs.append({"진입시간": self.entry_time, "청산시간": current_time, "포지션": self.position+" (50% 익절)",
            "레버리지": self.params['leverage'], "진입수량($)": round(reduce_amt,2),
            "진입가": self.entry_price, "청산가": current_price,
            "수수료($)": round(fee_cost,2), "순수익금($)": round(net_pnl,2)})
        self.capital += net_pnl
        self.position_size -= reduce_amt
        self.bot_state['remaining_pct'] = 0.5

    def _close_position(self, current_price, current_time, exit_reason):
        """[v7.6 변경 ①③] 전량 청산 — 복리 누적 + 강제청산 감지"""
        pnl_pct = (current_price - self.entry_price) / self.entry_price if self.position == "LONG" else (self.entry_price - current_price) / self.entry_price
        gross_pnl = self.position_size * pnl_pct
        fee_cost = self.position_size * self.fee_rate * 2
        duration_days = (current_time - self.entry_time).total_seconds() / 86400 if self.entry_time else 0
        funding_cost = self.position_size * self.funding_rate_daily * duration_days
        net_pnl = gross_pnl - fee_cost - funding_cost
        net_return_pct = (net_pnl / self.position_size) * 100 if self.position_size else 0

        self.trade_logs.append({"진입시간": self.entry_time, "청산시간": current_time,
            "포지션": self.position + (" (나머지 50%)" if self.bot_state.get('remaining_pct')==0.5 else " (전량)"),
            "레버리지": self.params['leverage'], "진입수량($)": round(self.position_size,2),
            "진입가": self.entry_price, "청산가": current_price,
            "수수료($)": round(fee_cost,2), "순수익금($)": round(net_pnl,2)})

        target_stat = self.stats[self.position]
        target_stat['trades'] += 1
        target_stat['fees'] += fee_cost
        target_stat['net_profit'] += net_pnl
        target_stat['return_pct_sum'] += net_return_pct
        if net_pnl > 0: target_stat['wins'] += 1

        self.capital += net_pnl
        # [v7.6 변경 ①] spot_wallet 인출 로직 제거
        # [v7.6 변경 ③] 강제청산 안전장치
        if self.capital <= 0:
            self.capital = 0
            self.position = "TERMINATED"
        else:
            self.position = "WAIT"


# === 테스트 케이스 ===
TOL = 0.01  # 부동소수점 허용 오차 (cent 단위)
results = []

def assert_close(actual, expected, msg):
    ok = abs(actual - expected) < TOL
    results.append((msg, actual, expected, ok))
    sym = "✓" if ok else "✗"
    print(f"  {sym} {msg}: actual={actual:.2f}, expected={expected:.2f}")

print("=" * 70)
print("[Pauto v7.6 복리 검증 — 5개 케이스]")
print("=" * 70)

# --- 케이스 1: 단순 수익 거래 → capital 누적 ---
# 자본 $10K, Lev 5, Long 진입가 $100, 청산가 $102 (가격 +2%)
# 명목 = $50K, gross_pnl = $50K × 0.02 = $1000
# fee = $50K × 0.0004 × 2 = $40
# funding = $50K × 0.0001 × 0.1일 = $0.5
# net_pnl = 1000 - 40 - 0.5 = $959.50
# new_capital = $10,000 + $959.50 = $10,959.50  (★ 점프 ① 정정 후)
print("\n[케이스 1] 단순 수익 거래 → capital 누적")
e = MockPautoEngine()
t0 = datetime(2026,1,1, 0, 0, 0)
t1 = t0 + timedelta(hours=2.4)  # 0.1일
e.open_position("LONG", 100.0, t0)
e._close_position(102.0, t1, "test")
assert_close(e.capital, 10959.50, "capital after profit")
assert_close(e.spot_wallet, 0.0, "spot_wallet = 0 (제거)")
assert e.position == "WAIT", "position WAIT"
print(f"  포지션 상태: {e.position}")

# --- 케이스 2: 손실 거래 → capital 감소 ---
# 자본 $10K, Lev 5, Long 진입 $100, 청산 $98 (가격 -2%)
# gross_pnl = -$1000, fee = $40, funding = $0.5 → net = -$1040.5
# new_capital = $10,000 - $1040.5 = $8,959.50
print("\n[케이스 2] 손실 거래 → capital 감소 (복리 효과 - 다음 거래 명목가 축소)")
e = MockPautoEngine()
e.open_position("LONG", 100.0, t0)
e._close_position(98.0, t1, "test")
assert_close(e.capital, 8959.50, "capital after loss")
# 다음 거래 진입 시 명목가는 작아져야 함
e.open_position("LONG", 100.0, t1)
assert_close(e.position_size, 8959.50 * 5, "next position_size = 8959.5 × 5")
print(f"  다음 거래 명목가: ${e.position_size:.2f} (자본축소로 복리 자동 작동)")

# --- 케이스 3: 연속 손실 → 강제청산 (margin call) 감지 ---
# Lev 5, sl_roe 5.73% → 가격 변동 1.15% (5.73/5)으로 SL 발동 = 자본 -5.73%
# 하지만 큰 가격 변동(-20%) 시 자본 -100% 시뮬
print("\n[케이스 3] 자본 -100% 도달 → 강제청산 안전장치 작동")
e = MockPautoEngine()
e.open_position("LONG", 100.0, t0)
# 가격 -20% (Lev 5 × 20% = 자본 -100%)
e._close_position(80.0, t1, "test")
# gross = $50K × -0.20 = -$10,000
# fee = $40, funding = $0.5
# net_pnl = -$10,040.5
# capital = 10000 - 10040.5 = -40.5 → 강제청산 트리거
assert e.capital == 0, f"강제청산 시 capital = 0 (실제 {e.capital})"
assert e.position == "TERMINATED", f"position TERMINATED (실제 {e.position})"
print(f"  강제청산 감지: capital={e.capital}, position={e.position}")

# --- 케이스 4: 50% 분할 익절 → 잔여 50% 정상 처리 ---
# Lev 5, Long 진입 $100, 1차 익절 $103 (50% 청산), 2차 청산 $105
# 1차: reduce_amt = $25K, pnl_pct = 0.03, gross = $750, fee = $20, net = $730 → capital $10,730
# 잔여 position_size = $25K (가격 $100 기준 unchanged)
# 2차: position_size = $25K (★ 50% 익절 후 잔여), pnl_pct = 0.05, gross = $1250, fee = $20
# funding = $25K × 0.0001 × 0.1일 = $0.25
# net = $1229.75 → capital = 10730 + 1229.75 = $11,959.75
print("\n[케이스 4] 50% 분할 익절 + 잔여 청산 정합")
e = MockPautoEngine()
e.open_position("LONG", 100.0, t0)
e._reduce_position(103.0, t0 + timedelta(hours=1), "1차 익절")
assert_close(e.capital, 10730.0, "capital after 50% 익절")
assert_close(e.position_size, 25000.0, "잔여 position_size")
e._close_position(105.0, t1, "전량 청산")
assert_close(e.capital, 11959.75, "capital after 잔여 50% 청산")
print(f"  총 변화: $10,000 → ${e.capital:.2f}")

# --- 케이스 5: 장기 holding (15일) funding cost 누적 ---
# Lev 5, Long 진입 $100, 청산 $101 (가격 +1%), 15일 holding
# gross = $50K × 0.01 = $500
# fee = $40
# funding = $50K × 0.0001 × 15 = $75
# net = $500 - $40 - $75 = $385
# capital = $10,385
print("\n[케이스 5] 15일 long holding → funding cost 누적")
e = MockPautoEngine()
e.open_position("LONG", 100.0, t0)
t_long = t0 + timedelta(days=15)
e._close_position(101.0, t_long, "test")
assert_close(e.capital, 10385.0, "capital after 15-day hold")
print(f"  funding cost 영향 확인 (15일 누적)")

# === 최종 보고 ===
print("\n" + "=" * 70)
total = len(results)
passed = sum(1 for *_, ok in results if ok)
print(f"단위 테스트 결과: {passed}/{total} 통과")
if passed == total:
    print("✓ 모든 케이스 통과 — 복리 로직 ① 정상 작동")
    print("✓ 강제청산 안전장치 ③ 정상 작동")
    print("✓ 50% 분할 익절 정합성 확인")
else:
    print("✗ 일부 케이스 실패 — 코드 재검토 필요")
    for msg, a, ex, ok in results:
        if not ok:
            print(f"  FAIL: {msg} — actual {a}, expected {ex}")
sys.exit(0 if passed == total else 1)
