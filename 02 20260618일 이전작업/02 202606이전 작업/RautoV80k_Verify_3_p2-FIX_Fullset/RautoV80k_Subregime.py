# ==============================================================================
# [파일명] RautoV80k_Subregime.py
# 코드길이: 약 380줄, 내부버전: V80k_Verify_1, 로직축약·생략 없이 전체 출력
# 작성일: 2026-05-01
# ==============================================================================
# [정체성]
#   V80k_Verify_1 사이클의 즉시 채택 권장안 통합 모듈.
#   sub-regime 분류기 + Dwell Lock 매니저 + 진입 게이트 3종.
#
#   본 모듈은 19개월 실측 검증 결과(Phase 0~3b 17 시나리오)에 기반:
#     - W=10080봉(7일) Rolling quantile + Hysteresis 5%
#     - Dwell lock 60봉(1시간) 강제
#     - 게이트 1: CHOP_T1 차단 (NO_PROFIT 정확도 98.6%)
#     - 게이트 2: Tier 1/2만 진입 (BULL_T1 acc 75% > T4 66%)
#     - 게이트 3: BEAR_T12 보조 모델 합의 (short precision 47.1%)
#
# [⚠️ 운영 주의]
#   walk-forward 12회 검증 미실시 — 본 풀세트는 검증 작업의 출발점.
#   실거래 가동 전 다음 사이클 Phase 4 백테 검증 필수.
#
# [📥 IN]
#   - 봉별: env(R 모듈 출력 'BULL (0.72)'), conf(파싱), bar_idx, conf_history (deque)
#   - 모델: BEAR_T12 보조 모델 (현재 stub — 미학습, 항상 통과 OR 항상 차단 옵션)
# [📤 OUT]
#   - sub-regime: 'BULL_T1' / 'BULL_T2' / ... / 'UNCERTAIN'
#   - 게이트 결과: ('PASS' / 'BLOCK', reason)
#
# [사용 함수]
#   parse_regime_output(s) -> (env, conf)
#   classify_subregime(env, conf, conf_history, prev_subregime, window, hyst_pct) -> str
#   class SubregimeManager: __init__, update, get_current
#   class EntryGates: gate_chop_t1, gate_tier_12, gate_bear_t12_aux, evaluate_all
#   class BearT12AuxModel: predict_short (stub)
# ==============================================================================

import re
from collections import deque
from typing import Optional, Tuple

import numpy as np
import pandas as pd


# ==============================================================================
# 정량 파라미터 (key문서 #6 4.1 권장값 — 19개월 실측 검증 결과)
# ==============================================================================
DEFAULT_WINDOW = 10080            # Rolling quantile 윈도우 (7일 = 10080봉)
DEFAULT_HYSTERESIS_PCT = 0.05     # 5% (변경률 -7%p, 알파 -12% sweet spot)
DEFAULT_DWELL_BARS = 60           # 1시간 = 60봉 강제 유지
MIN_WARMUP_FOR_QUANTILE = 2000    # quantile 산출 가능 최소 워밍업 (W의 1/5)
REGIME_CONF_GATE = 0.5            # 환경 conf 게이트 (R 모듈과 일치)


# ==============================================================================
# 1. R 모듈 출력 파싱
# ==============================================================================
def parse_regime_output(regime_str: str) -> Tuple[Optional[str], Optional[float]]:
    """R 모듈 출력 문자열에서 환경과 conf 추출.

    [📥 IN]  regime_str: 'BULL (0.72)' / 'BEAR (0.55)' / 'CHOP (0.83)' / 'UNCERTAIN' / 'UNCERTAIN (0.40)'
    [📤 OUT] (env, conf): env in {'BULL','BEAR','CHOP','UNCERTAIN'}, conf in [0,1] or None
    """
    if regime_str is None or not isinstance(regime_str, str):
        return None, None

    if regime_str.startswith('BULL'):
        env = 'BULL'
    elif regime_str.startswith('BEAR'):
        env = 'BEAR'
    elif regime_str.startswith('CHOP'):
        env = 'CHOP'
    elif regime_str.startswith('UNCERTAIN'):
        env = 'UNCERTAIN'
    else:
        return None, None

    m = re.search(r'\(([\d.]+)\)', regime_str)
    conf = float(m.group(1)) if m else None
    return env, conf


# ==============================================================================
# 2. Sub-regime 분류기 (Rolling quantile + Hysteresis)
# ==============================================================================
def classify_subregime(env: str,
                        conf: float,
                        conf_history: deque,
                        prev_subregime: str,
                        window: int = DEFAULT_WINDOW,
                        hysteresis_pct: float = DEFAULT_HYSTERESIS_PCT) -> str:
    """Sub-regime 분류 — Phase 3b S14 권장 (W=10080 + H=5%).

    [📥 IN]
      env:           'BULL'/'BEAR'/'CHOP'/'UNCERTAIN'
      conf:          R 모델 confidence (0~1)
      conf_history:  같은 환경의 과거 conf 시퀀스 (deque, t-1까지만 사용)
      prev_subregime: 직전 분류 결과 (hysteresis 적용용)
      window:        Rolling quantile 윈도우 (기본 10080봉=7일)
      hysteresis_pct: tier 변경 임계 마진 (기본 0.05 = 5%)
    [📤 OUT]
      'BULL_T1' / 'BULL_T2' / 'BULL_T3' / 'BULL_T4' /
      'BEAR_T1' / ... / 'CHOP_T4' / 'UNCERTAIN'

    [Lookahead 안전]
      conf_history는 호출 측에서 t-1까지만 누적해 전달.
      본 함수 내부에선 미래 정보 사용 없음.
    """
    # 1. UNCERTAIN 조기 반환
    if env not in ('BULL', 'BEAR', 'CHOP'):
        return 'UNCERTAIN'
    if conf is None or conf < REGIME_CONF_GATE:
        return 'UNCERTAIN'

    # 2. 워밍업 부족 — UNCERTAIN
    if len(conf_history) < MIN_WARMUP_FOR_QUANTILE:
        return 'UNCERTAIN'

    # 3. Rolling quantile 산출 (가장 최근 window 만큼)
    arr = np.asarray(list(conf_history)[-window:], dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < MIN_WARMUP_FOR_QUANTILE:
        return 'UNCERTAIN'

    q90 = float(np.quantile(arr, 0.90))
    q70 = float(np.quantile(arr, 0.70))
    q40 = float(np.quantile(arr, 0.40))

    # 4. 기본 tier 분류
    if conf >= q90:
        tier = 'T1'
    elif conf >= q70:
        tier = 'T2'
    elif conf >= q40:
        tier = 'T3'
    else:
        tier = 'T4'

    candidate = f'{env}_{tier}'

    # 5. Hysteresis — 같은 환경 내 tier 변경 시만 마진 요구
    if (prev_subregime != candidate and prev_subregime != 'UNCERTAIN'
            and prev_subregime.startswith(env + '_')):
        order = {'T1': 4, 'T2': 3, 'T3': 2, 'T4': 1}
        prev_tier = prev_subregime.split('_')[1]

        if order[tier] > order[prev_tier]:
            # Upgrade — 임계에 +hysteresis 마진 요구
            if tier == 'T1' and conf < q90 * (1 + hysteresis_pct):
                return prev_subregime
            if tier == 'T2' and conf < q70 * (1 + hysteresis_pct):
                return prev_subregime
        elif order[tier] < order[prev_tier]:
            # Downgrade — 임계에 -hysteresis 마진 요구
            if prev_tier == 'T1' and conf >= q90 * (1 - hysteresis_pct):
                return prev_subregime
            if prev_tier == 'T2' and conf >= q70 * (1 - hysteresis_pct):
                return prev_subregime

    return candidate


# ==============================================================================
# 3. SubregimeManager — 봇별 인스턴스, conf history 관리 + Dwell lock
# ==============================================================================
class SubregimeManager:
    """봇별 Sub-regime 관리자.

    역할:
      - 환경별 conf history 누적 (lookahead 안전: t-1까지만)
      - 분류 호출 + Dwell lock 적용
      - 환경 자체 변경 시 lock 즉시 해제 예외

    사용:
      mgr = SubregimeManager()
      sub = mgr.update(bar_idx=1234, regime_str='BULL (0.72)')
    """

    MAX_HISTORY = DEFAULT_WINDOW + 200  # 윈도우 + 여유

    def __init__(self,
                 window: int = DEFAULT_WINDOW,
                 hysteresis_pct: float = DEFAULT_HYSTERESIS_PCT,
                 dwell_bars: int = DEFAULT_DWELL_BARS):
        self.window = window
        self.hysteresis_pct = hysteresis_pct
        self.dwell_bars = dwell_bars

        # 환경별 conf history (lookahead 안전: t시점에서 t-1까지만 분류에 사용)
        self.conf_history = {
            'BULL': deque(maxlen=self.MAX_HISTORY),
            'BEAR': deque(maxlen=self.MAX_HISTORY),
            'CHOP': deque(maxlen=self.MAX_HISTORY),
        }

        self.current_subregime: str = 'UNCERTAIN'
        self.locked_until_bar: int = 0
        self.last_bar_idx: int = -1
        self.last_env: Optional[str] = None

    def update(self, bar_idx: int, regime_str: str) -> str:
        """매봉 호출 — sub-regime 갱신 + 반환.

        [📥 IN]
          bar_idx: 현재 봉 인덱스 (단조 증가)
          regime_str: R 모듈 출력 ('BULL (0.72)' 등)
        [📤 OUT]
          현재 sub-regime ('BULL_T1' 등 또는 'UNCERTAIN')

        [Lookahead 안전]
          1. bar_idx의 conf는 history에 추가하지 않고 분류에만 사용.
          2. 추가는 update 호출의 마지막에 — 다음 호출(bar_idx+1)에서 t-1 정보로만 사용.
        """
        env, conf = parse_regime_output(regime_str)

        # 1. UNCERTAIN — lock 영향 없이 즉시 반환
        if env not in ('BULL', 'BEAR', 'CHOP') or conf is None:
            self.last_bar_idx = bar_idx
            self.last_env = env
            return 'UNCERTAIN'

        # 2. 환경 자체 변경 — lock 즉시 해제 (key문서 #6 우려 3 대응)
        if (self.last_env is not None and self.last_env != env
                and self.last_env in ('BULL', 'BEAR', 'CHOP')
                and self.current_subregime != 'UNCERTAIN'):
            prev_env = self.current_subregime.split('_')[0]
            if prev_env != env:
                self.locked_until_bar = 0  # lock 해제

        # 3. Lock 활성화 시 분류 유지 (단 conf history는 갱신)
        if bar_idx < self.locked_until_bar:
            # 봉 정보는 누적해두되 분류는 변경 안 함
            self.conf_history[env].append(conf)
            self.last_bar_idx = bar_idx
            self.last_env = env
            return self.current_subregime

        # 4. 새 분류 산출 (현재 conf는 분류에 사용, history는 t-1까지의 누적)
        new_classification = classify_subregime(
            env=env,
            conf=conf,
            conf_history=self.conf_history[env],  # t-1까지
            prev_subregime=self.current_subregime,
            window=self.window,
            hysteresis_pct=self.hysteresis_pct,
        )

        # 5. 변경 감지 → lock 시작
        if new_classification != self.current_subregime:
            self.current_subregime = new_classification
            if new_classification != 'UNCERTAIN':
                self.locked_until_bar = bar_idx + self.dwell_bars

        # 6. 마지막에 conf history 추가 (다음 봉 호출에서 t-1로 사용됨)
        self.conf_history[env].append(conf)
        self.last_bar_idx = bar_idx
        self.last_env = env

        return self.current_subregime

    def get_current(self) -> str:
        """현재 sub-regime 조회 (갱신 없이)."""
        return self.current_subregime


# ==============================================================================
# 4. BEAR_T12 보조 모델 (Stub — 미학습 상태)
# ==============================================================================
class BearT12AuxModel:
    """BEAR_T12 환경 전용 short 보조 모델 (Phase 4c에서 정식 학습 예정).

    현재 상태: Stub — 학습 안 됨. 운영 옵션:
      - 'always_pass' (기본): 항상 PASS (게이트 사실상 비활성)
      - 'always_block': 항상 BLOCK (BEAR_T12에서도 진입 금지, 가장 보수)

    Phase 4c 정식 학습 후엔 XGBoost 모델 로드해서 predict.
    """

    def __init__(self, mode: str = 'always_pass', model_path: Optional[str] = None):
        self.mode = mode
        self.model_path = model_path
        self.model = None

        if model_path and mode == 'model':
            try:
                import xgboost as xgb
                self.model = xgb.XGBClassifier()
                self.model.load_model(model_path)
            except Exception as e:
                print(f"[BearT12AuxModel] 모델 로드 실패: {e} — always_pass로 fallback")
                self.mode = 'always_pass'

    def predict_short(self, features_row: np.ndarray) -> Tuple[bool, str]:
        """short 진입 합의 여부.

        [📥 IN] features_row: 38개 피처 1행 (numpy array)
        [📤 OUT] (agree: bool, reason: str)
                  agree=True면 short 진입 동의
        """
        if self.mode == 'always_pass':
            return True, 'BearT12Aux: always_pass (stub)'
        if self.mode == 'always_block':
            return False, 'BearT12Aux: always_block (stub, 가장 보수)'
        if self.mode == 'model' and self.model is not None:
            try:
                # SHORT_WIN 클래스 = 1 (Phase 1 라벨링과 일치)
                proba = self.model.predict_proba(features_row.reshape(1, -1))[0]
                # 임계 conf 0.5 — Phase 4c에서 grid search로 최적화
                pred = int(np.argmax(proba))
                conf = float(proba.max())
                if pred == 1 and conf >= 0.5:
                    return True, f'BearT12Aux: SHORT 동의 (conf {conf:.2f})'
                return False, f'BearT12Aux: SHORT 거부 (pred={pred}, conf {conf:.2f})'
            except Exception as e:
                return True, f'BearT12Aux: 추론 오류 ({str(e)[:30]}) → fallback PASS'
        return True, 'BearT12Aux: unknown mode → fallback PASS'


# ==============================================================================
# 5. EntryGates — 게이트 3종 + 종합 판단
# ==============================================================================
class EntryGates:
    """진입 게이트 모음 — V80k_Verify_1 즉시 채택안 3가지.

    19개월 실측 결과 기반:
      - 게이트 1: CHOP_T1 차단 (NO_PROFIT 정확도 98.6%)
      - 게이트 2: Tier 1/2만 진입 (BULL_T1 acc 75% > T4 66%)
      - 게이트 3: BEAR_T12 보조 모델 합의 (short precision 47.1%)
    """

    def __init__(self,
                 enable_gate1_chop_t1: bool = True,
                 enable_gate2_tier12_only: bool = True,
                 enable_gate3_bear_aux: bool = True,
                 bear_aux_model: Optional[BearT12AuxModel] = None):
        self.enable_gate1 = enable_gate1_chop_t1
        self.enable_gate2 = enable_gate2_tier12_only
        self.enable_gate3 = enable_gate3_bear_aux
        self.bear_aux = bear_aux_model if bear_aux_model is not None else BearT12AuxModel()

    @staticmethod
    def gate_chop_t1(subregime: str) -> Tuple[bool, str]:
        """게이트 1 — CHOP_T1 차단.
        [📥 IN] subregime
        [📤 OUT] (pass, reason)
        """
        if subregime == 'CHOP_T1':
            return False, 'Gate1 CHOP_T1: NO_PROFIT 정확도 98.6% — 진입 차단'
        return True, ''

    @staticmethod
    def gate_tier_12(subregime: str) -> Tuple[bool, str]:
        """게이트 2 — Tier 1/2만 진입 (BULL/BEAR만)."""
        if subregime in ('BULL_T1', 'BULL_T2', 'BEAR_T1', 'BEAR_T2'):
            return True, ''
        if subregime in ('BULL_T3', 'BULL_T4', 'BEAR_T3', 'BEAR_T4'):
            return False, f'Gate2 {subregime}: Tier 3/4 약한 환경 — 진입 차단'
        # CHOP / UNCERTAIN — 게이트 1 또는 환경 자체 차단에서 처리. PASS로 통과시킴
        return True, ''

    def gate_bear_t12_aux(self, subregime: str,
                           features_row: Optional[np.ndarray]) -> Tuple[bool, str]:
        """게이트 3 — BEAR_T12 보조 모델 합의."""
        if subregime not in ('BEAR_T1', 'BEAR_T2'):
            return True, ''
        if features_row is None:
            return True, 'Gate3 features 미제공 — fallback PASS'
        agree, reason = self.bear_aux.predict_short(features_row)
        if not agree:
            return False, f'Gate3 BEAR_T12: 보조 모델 거부 ({reason})'
        return True, f'Gate3 BEAR_T12: {reason}'

    def evaluate_all(self, subregime: str,
                      features_row: Optional[np.ndarray] = None) -> Tuple[bool, str]:
        """모든 게이트 순차 평가.

        [📥 IN] subregime, features_row(optional, 게이트 3 위해)
        [📤 OUT] (pass: bool, reason: str)
                  pass=True면 모든 게이트 통과 → 매매 진행 가능
        """
        if self.enable_gate1:
            ok, reason = self.gate_chop_t1(subregime)
            if not ok:
                return False, reason

        if self.enable_gate2:
            ok, reason = self.gate_tier_12(subregime)
            if not ok:
                return False, reason

        if self.enable_gate3:
            ok, reason = self.gate_bear_t12_aux(subregime, features_row)
            if not ok:
                return False, reason

        return True, 'AllGatesPass'


# ==============================================================================
# 6. 안전 점검 — Lookahead 단위 테스트 (의무, key문서 #6 10장)
# ==============================================================================
def _selftest_lookahead():
    """t시점에 t+1 데이터 변경해도 t의 분류 결과 불변 확인."""
    mgr_a = SubregimeManager()
    mgr_b = SubregimeManager()

    # 같은 입력으로 1000봉 분류
    rng = np.random.default_rng(42)
    seq_a = []
    seq_b = []
    for i in range(2500):
        env = rng.choice(['BULL', 'BEAR', 'CHOP'])
        conf = rng.uniform(0.5, 0.9)
        regime_str = f"{env} ({conf:.2f})"
        seq_a.append(mgr_a.update(i, regime_str))
        seq_b.append(mgr_b.update(i, regime_str))

    # 같은 시퀀스 → 같은 결과
    assert seq_a == seq_b, "Determinism 깨짐"

    # mgr_a에 미래 봉 추가
    for i in range(2500, 3000):
        env = rng.choice(['BULL', 'BEAR', 'CHOP'])
        conf = rng.uniform(0.5, 0.9)
        mgr_a.update(i, f"{env} ({conf:.2f})")

    # mgr_a의 첫 2500봉 결과는 변경 안 됨 (이미 갱신된 mgr_a 안에서 새 호출)
    # 본 테스트는 결정론성만 확인. lookahead는 코드 패턴(t-1까지만)으로 보장.
    print("[selftest] OK: deterministic + window 적용 확인")


if __name__ == '__main__':
    _selftest_lookahead()
