# -*- coding: utf-8 -*-
# [파일명] plugin_trend_stack_RAUTO.py
# 코드길이: 약 200줄 | 내부버전: RAUTO_TrendStack_v1_Stg13confirmed | 로직 전체 출력(축약/생략 없음)
# ─────────────────────────────────────────────────────────────────────────────
# [이 파일이 하는 일 — 고딩 설명]
#   RAUTO 추세봇의 최종 확정 스택(④)을 '한 파일'로 봉인한 플러그인이다. 챔피언 엔진
#   (SpTrd_Fib_V1_Champion.py)은 손대지 않는다(해시 7f9192e3). 엔진이 내보내는 신호와 거래결과를
#   '바깥에서' 두 모듈로 보정한다. 업로드된 Plugin Key 노트(Stg16)의 구조를 따르되, Ch6 확정사항 반영:
#     · 모듈 A(ML 장세 사이징) = 폐기. Ch6 Stg5에서 ML 장세예측 AUC 0.5(예측력 0)로 확인. 코드에 안 넣음.
#     · 모듈 B(칩필터)  = 유지. CHOP>65 & ER<0.35 & ADX<25 이면 추세봇 진입 스킵.
#     · 모듈 C(쿨다운)  = 신규. 연속 손절(sl) K번이면 M봉 진입중단. Ch6 핵심 알파(Stg9~13).
#     · er게이트       = 엔진 내장(run_strategy의 gate_mode='er', gate_er=0.45). 플러그인이 켜는 게 아니라
#                        엔진 호출 시 인자로 주는 값. 여기선 '확정값'으로 문서화만.
#
#   [확정 근거 — Stg13 복리+CPCV, 직접 95%]
#     ④(칩+쿨다운): $51,184 / MDD -23.57 / 2025 +6.65%(최고) / CPCV p25 1.570(최고)
#     ③(쿨만)     : $53,462 / 2025 +0.51% / CPCV p25 1.556  ← 전체잔고는 높으나 약한해 방어 약함
#     사장님 결정: ④ (목표 '매월 플러스'엔 약한해 방어가 핵심)
#
#   [충돌 방지 — 우선순위 고정]  한 거래의 운명은 아래 순서로 한 번만 결정(두 모듈이 같은 거래를 두 번 안 건드림):
#     1) B(칩필터) 켜짐 & 칩이면        -> 진입 스킵 (여기서 끝)
#     2) 아니고 C(쿨다운) 발동 중이면     -> 진입 스킵 (여기서 끝)
#     3) 둘 다 아니면                   -> 진입 허용 (원래 챔피언봇)
#   이유: 칩(B)은 '아예 들어가지 말 자리', 쿨다운(C)은 '연속 손절 후 쉬는 자리'. 둘 다 진입 차단이라
#         순서가 달라도 결과(스킵)는 같지만, 통계 집계를 위해 사유를 구분해 기록한다.
#
#   [★미래참조 차단]  chip(CHOP/ER/ADX)·쿨다운 모두 '진입봉까지의 과거 결과'에서만 계산. 미래 안 봄.
#     단 칩 지표는 봉 마감 시점에 확정되므로, 실시간에선 '봉 마감 후' 판정해야 lookahead 안 생김(주의1).
#
# [In/Out 태그]
#   CONFIG                  : 설정 딕셔너리(모듈 ON/OFF·파라미터). 숫자만 바꾸면 조정.
#   is_chip(ind,i,cfgB)     : In 지표·봉index·칩설정 / Out True=칩(진입금지 후보)
#   filter_trades_chip(...)  : In 거래리스트·지표·설정 / Out 칩 아닌 거래만
#   apply_cooldown_stack(...): In 거래리스트·설정 / Out 쿨다운 통과 거래만 + 통계 (cooldown.py 호출)
#   decide_realtime(...)    : In 실시간 지표·쿨다운상태 / Out (allow_entry, reason) — 실물 RAUTO용
#   ENGINE_CALL_HINT        : 엔진 호출 시 줄 확정 인자(er게이트 등) 문서화
# ─────────────────────────────────────────────────────────────────────────────
import numpy as np

# ============================ 설정 (CONFIG) ============================
# 전부 여기서 숫자만 바꾸면 조정된다. enabled=False면 그 모듈은 '없는 것'처럼 동작.
CONFIG = {
    'er_gate': {                       # 엔진 내장 게이트(플러그인이 끄는 게 아니라 엔진 호출 인자)
        'gate_mode': 'er',
        'gate_er': 0.45,               # Stg15 확정값
    },
    'B_chip': {                        # 모듈 B — 칩필터 (Stg15 확정)
        'enabled': True,
        'chop_hi': 65.0,               # CHOP 이 값 초과면 칩 후보
        'er_lo': 0.35,                 # ER 이 값 미만이면 칩 후보
        'adx_lo': 25.0,                # ADX 이 값 미만이면 칩 후보 (셋 다 AND여야 '칩')
    },
    'C_cooldown': {                    # 모듈 C — 쿨다운 (Ch6 Stg9~13 확정)
        'enabled': True,
        'K': 4,                        # 연속 손절 K번이면
        'M': 8,                        # M봉 동안 진입 중단
        'bar_minutes': 420,            # 7h봉 = 420분
    },
    # 모듈 A(ML 장세 사이징)는 Ch6 Stg5에서 폐기(AUC 0.5). 의도적으로 넣지 않음.
}

# 엔진 호출 시 줄 확정 인자(문서화). 백테스트/실물 공통.
ENGINE_CALL_HINT = dict(gate_mode='er', gate_er=0.45, atr_mult=0.8,
                        fib=(0.3, 0.5, 0.6), split_mode='A', split_n=3)


# ============================ 모듈 B — 칩필터 ============================
def is_chip(ind, i, cfgB):
    """진입봉 i가 '칩(추세 없는 갈지자)'인가. 셋 다 AND. NaN이면 칩 아님(보수적)."""
    c = ind['chop'][i]; e = ind['er'][i]; a = ind['adx'][i]
    if any(x != x for x in (c, e, a)):     # NaN 방어
        return False
    return bool((c > cfgB['chop_hi']) and (e < cfgB['er_lo']) and (a < cfgB['adx_lo']))


def filter_trades_chip(trades, ind, bar_of_trade, CONFIG):
    """백테스트용: 거래 리스트에서 칩 거래를 제거. trades 각 원소는 dict(진입봉 index 포함).
    bar_of_trade(t) -> 그 거래 진입봉의 지표 index."""
    cfgB = CONFIG.get('B_chip', {})
    if not cfgB.get('enabled'):
        return list(trades), 0
    kept = []; n_removed = 0
    for t in trades:
        i = bar_of_trade(t)
        if is_chip(ind, i, cfgB):
            n_removed += 1
            continue
        kept.append(t)
    return kept, n_removed


# ============================ 모듈 C — 쿨다운 ============================
def apply_cooldown_stack(trades, CONFIG, cooldown_module):
    """백테스트용: cooldown.py의 apply_cooldown 호출(엔진 무수정 원칙, 검증된 모듈 재사용).
    trades는 시간순, 각 dict에 'reason'('sl'/'trend_flip')·'entry_t' 포함."""
    cfgC = CONFIG.get('C_cooldown', {})
    if not cfgC.get('enabled'):
        return list(trades), 0, 0
    keep_idx, n_excluded, n_trigger = cooldown_module.apply_cooldown(
        trades, cfgC['bar_minutes'], cfgC['K'], cfgC['M'])
    kept = [trades[i] for i in keep_idx]
    return kept, n_excluded, n_trigger


# ============================ 통합 적용 (백테스트) ============================
def apply_stack_backtest(raw_trades, ind, bar_of_trade, CONFIG, cooldown_module):
    """RAUTO 추세봇 ④스택을 백테스트 거래에 적용. 우선순위 고정: B(칩) -> C(쿨다운).
    In : raw_trades(엔진 run_strategy 결과, er게이트는 이미 엔진에서 적용됨),
         ind(compute_indicators 결과), bar_of_trade(거래->진입봉 index), CONFIG, cooldown_module
    Out: dict(kept=최종거래, n_chip_removed, n_cool_excluded, n_cool_trigger)"""
    # 1) 칩필터
    after_chip, n_chip = filter_trades_chip(raw_trades, ind, bar_of_trade, CONFIG)
    # 2) 쿨다운 (칩 통과분에 대해)
    after_cool, n_cool_exc, n_cool_trig = apply_cooldown_stack(after_chip, CONFIG, cooldown_module)
    return dict(kept=after_cool, n_chip_removed=n_chip,
                n_cool_excluded=n_cool_exc, n_cool_trigger=n_cool_trig)


# ============================ 실시간 판정 (실물 RAUTO) ============================
class CooldownState:
    """실물 RAUTO용 쿨다운 상태 추적기. 봉마다 update_after_trade()로 손절결과를 먹이고,
    진입 직전 is_blocked()로 막혔는지 확인. (백테스트 cooldown.py와 같은 논리, 실시간 버전)"""
    def __init__(self, K, M):
        self.K = K; self.M = M
        self.consecutive_sl = 0      # 연속 손절 카운트
        self.blocked_until_bar = -1  # 이 봉 index까지 진입 금지

    def update_after_trade(self, reason, R, current_bar_idx):
        """거래가 끝날 때 호출. 백테스트 cooldown.py와 동일한 3갈래 리셋 규칙:
          (1) sl 손절(reason=='sl' and R<0) -> 연속카운트 +1
          (2) 수익(R>0)                     -> 연속카운트 0 리셋
          (3) 그 외(flip 손실 R<0, 또는 R==0) -> 카운트 유지 (sl만 센다)
        ★수정 이력(2026-06-02): 후임 지적①. 이전엔 else 전부 리셋이라 flip 손실에 리셋돼
          실물이 백테스트보다 쿨다운을 덜 발동했다. 백테스트(헤드라인 숫자 출처)와 일치시킴."""
        if reason == 'sl' and R < 0:
            self.consecutive_sl += 1
            if self.consecutive_sl >= self.K:
                self.blocked_until_bar = current_bar_idx + self.M
                self.consecutive_sl = 0   # 발동 후 리셋(중복발동 방지)
        elif R > 0:
            self.consecutive_sl = 0       # 수익 나면 리셋
        # else: flip 손실(R<0) 또는 R==0 -> 카운트 유지 (백테스트와 동일)

    def is_blocked(self, current_bar_idx):
        return current_bar_idx < self.blocked_until_bar


def decide_realtime(ind, bar_idx, cooldown_state, CONFIG):
    """실물 RAUTO용 진입 판정. 우선순위 고정: B(칩) -> C(쿨다운) -> 허용.
    In : ind(현재까지 확정봉 지표), bar_idx(현재 봉), cooldown_state(CooldownState), CONFIG
    Out: (allow_entry: bool, reason: str)
    ★주의: ind는 '봉 마감 후 확정값'이어야 한다. 장중 미확정값 쓰면 lookahead."""
    cfgB = CONFIG.get('B_chip', {})
    cfgC = CONFIG.get('C_cooldown', {})
    # 1) 칩필터
    if cfgB.get('enabled') and is_chip(ind, bar_idx, cfgB):
        return (False, 'chip_skip')
    # 2) 쿨다운
    if cfgC.get('enabled') and cooldown_state is not None and cooldown_state.is_blocked(bar_idx):
        return (False, 'cooldown_block')
    # 3) 허용
    return (True, 'allow')


# ============================ 자기 점검 ============================
def self_check():
    """플러그인 로직 자기검증(데이터 없이). import 시 호출 안 함, 수동 실행용."""
    # 칩 판정
    ind = {'chop': np.array([70.0, 50.0, 66.0]),
           'er':   np.array([0.30, 0.50, 0.20]),
           'adx':  np.array([20.0, 40.0, 24.0])}
    assert is_chip(ind, 0, CONFIG['B_chip']) == True   # 70>65,0.30<0.35,20<25 = 칩
    assert is_chip(ind, 1, CONFIG['B_chip']) == False  # 50<65 = 칩 아님
    assert is_chip(ind, 2, CONFIG['B_chip']) == True   # 66>65,0.20<0.35,24<25 = 칩
    # 쿨다운 상태기 (백테스트와 동일한 3갈래 리셋 검증)
    cs = CooldownState(K=4, M=8)
    for _ in range(3):
        cs.update_after_trade('sl', -0.02, 100)        # sl 손절 3연속
    assert cs.is_blocked(105) == False                 # 3연속(아직 K=4 미만)
    cs.update_after_trade('sl', -0.02, 100)            # 4연속 -> 발동, 108까지 차단
    assert cs.is_blocked(105) == True
    assert cs.is_blocked(108) == False                 # M=8 지나면 해제
    # ★flip 손실은 카운트 유지(후임 지적① 수정 검증)
    cs2f = CooldownState(K=2, M=5)
    cs2f.update_after_trade('sl', -0.02, 10)           # sl -> 카운트 1
    cs2f.update_after_trade('trend_flip', -0.01, 11)   # flip 손실 -> 유지(리셋 아님)
    assert cs2f.consecutive_sl == 1
    cs2f.update_after_trade('sl', -0.02, 12)           # sl -> 카운트 2 = K, 발동
    assert cs2f.is_blocked(13) == True                 # flip이 리셋 안 했으므로 발동
    # 수익은 리셋
    cs3 = CooldownState(K=2, M=5)
    cs3.update_after_trade('sl', -0.02, 20)            # 카운트 1
    cs3.update_after_trade('trend_flip', 0.03, 21)     # 수익 -> 리셋
    assert cs3.consecutive_sl == 0
    # 실시간 판정 우선순위
    allow, r = decide_realtime(ind, 0, None, CONFIG)
    assert allow == False and r == 'chip_skip'         # 0번봉 칩
    cs2 = CooldownState(K=4, M=8)                       # 깨끗한 상태(쿨다운 미발동)
    allow, r = decide_realtime(ind, 1, cs2, CONFIG)     # 1번봉 칩아님, 쿨다운 해제상태
    assert allow == True and r == 'allow'
    print("[self_check] PASS — 칩판정/쿨다운상태(3갈래리셋)/실시간 우선순위 정상")


if __name__ == "__main__":
    self_check()
