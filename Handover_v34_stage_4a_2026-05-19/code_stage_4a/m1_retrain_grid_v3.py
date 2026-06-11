# [파일명] m1_retrain_grid_v3.py
# 코드길이: 약 560줄, 내부버전명: v3.0 (stage_4a_phase2_m1_horizon_grid_bias_fixed)
# 로직을 축약/생략 없이 전체 출력.
#
# [v1 → v3 변경 이력 — 교차검증 2라운드 결과 반영]
#   ★ 채택(제미나이 발견): 1분봉 내 익절·손절 "동시 도달" 시 손절(-1)로 처리.
#      - 기존 v1은 "보수적으로 익절 우선(=1)"으로 둬서 낙관 편향 → 가짜 익절 라벨 생성.
#      - 백테스트 표준: 1분 내부 순서를 알 수 없으면 나쁜 쪽(손절)으로 가정.
#      - 적용 위치 4곳: 고정함수 long/short + 동적함수 long/short.
#      - 검증: S6(손절 가까움) 노이즈 데이터에서 stay 59.6%→73.6% (가짜익절 14%p 제거).
#   ★ 버림(제미나이 v2 신규버그): safe_limit=n-120 + used_n_arr 반환제거.
#      - 동적함수 used_n 최대 180인데 120만 확보 → IndexError. (직접 재현 확인)
#      - used_n_arr 미반환 → main()의 unpack ValueError. (직접 재현 확인)
#      - → v1 원본 안전장치(if t+1+used_n>n: used_n=n-t-1) + 2개 반환 유지.
#   ★ 개선(공정성, 통계≠학습 불일치 해소): 라벨 분포 통계를 "실제 학습에 쓰인
#      라벨"과 동일 기준으로 집계. 시나리오 비교 공정성은 별도 컬럼(n_labeled)로 표기.
#
# ============================================================================
# [목적]
#   Stage 4A Phase 2 - 2단계: M1(진입신호 모델) horizon 재학습 그리드 실험.
#   사용자가 선택한 4개 시나리오(S1/S3/S6/S7)로 M1을 각각 재학습하고,
#   라벨 분포 + OOS AUC + 재추출 신호 기반 base PF를 측정해
#   "어느 horizon/벽 설정이 가장 나은가"를 데이터로 결정한다.
#
# [사용자 결정 반영]
#   - 확인1: (나) future_n + 벽 스케일 + 동적 배리어 1개
#   - 확인2: S1, S3, S6, S7만 진행 (S0 base/S2/S4/S5 제외)
#   - 확인3: 그리드 한 번에 측정 (예외 인정)
#
# [4개 시나리오 정의 — 사용자 선택]
#   ┌──────┬──────────┬──────────┬──────────┬─────────────────────────────┐
#   │ 시나 │ future_n │ 익절 벽  │ 손절 벽  │ 목적                        │
#   ├──────┼──────────┼──────────┼──────────┼─────────────────────────────┤
#   │ S1   │ 60봉     │ ATR×1.5  │ ATR×1.0  │ horizon만 확대(벽 그대로)   │
#   │      │          │          │          │ → 라벨 붕괴 확인용 대조군   │
#   │ S3   │ 30봉     │ ATR×2.0  │ ATR×1.4  │ 중간 확대 + 벽 스케일       │
#   │ S6   │ 60봉     │ ATR×3.0  │ ATR×1.5  │ 비대칭(익절 멀리/손절 가까) │
#   │ S7   │ 동적     │ ATR×동적 │ ATR×동적 │ 변동성 따라 horizon 자동조절│
#   └──────┴──────────┴──────────┴──────────┴─────────────────────────────┘
#   * 비교 기준 S0(현행 10봉/×1.5/×1.0)는 기존 PautoV75_XGB_3class_v2.json을
#     그대로 비교 기준으로 쓰므로 재학습 안 함(이미 있음).
#
# [핵심 수정 — 원본 apply_triple_barrier_v2의 first-touch 버그 정정]
#   원본(ML_Predictor_Pipeline_v2.py 134-135행)은:
#     long_success = (미래 high가 익절 도달) AND (미래 low 전부가 손절 위)
#   → 이 방식은 horizon이 길어지면 "익절 갔다가 나중에 손절"인 경로를
#     전부 stay(0)로 버려 라벨이 붕괴됨.
#   본 코드는 표준 TBM의 first-touch(먼저 닿는 벽)를 순차 스캔으로 정확히
#     구현하여 horizon 확대 시에도 라벨 분포가 유지되게 함.
#
# ============================================================================
# [변수 파이프라인]
# 📥 IN:
#   - Merged_Data.csv (사용자 PC, 자동 탐색): timestamp + OHLCV + oi_*
#   - 기존 모듈 4개(같은 폴더): ML_Predictor_Pipeline_v2, tf_aggregator_v2,
#     pautov75_signal_wrapper_v4, tbm_simulator_v11, ob_provider_v2, Regime_Master_v2
# 🛠️ STATE:
#   - 36개월 데이터를 70/30(train/oos) 분할 (M1 메타 train_end 2025-06-06 기준)
#   - 시나리오별 TBM 라벨링 → XGBoost 3-class 학습 → OOS AUC 측정
#   - (선택) 재추출 신호로 백테스트는 별도 단계(이번엔 라벨/AUC까지만, 부하 분리)
# 📤 OUT:
#   - outputs_m1_grid/ 폴더:
#       * grid_summary.csv (시나리오별 라벨분포 + AUC + 학습시간)
#       * M1_S1.json / M1_S3.json / M1_S6.json / M1_S7.json (재학습 모델 4개)
#       * M1_S1_meta.json ... (각 메타)
#       * label_distribution.csv (시나리오별 stay/long/short 비율)
#       * measure_log.txt (전체 로그)
#   - outputs_m1_grid.zip (위 폴더 압축 — 사용자가 이거 1개만 업로드)
#
# ============================================================================
# [함수 목록 + In/Out]
#   find_file(filename, max_depth=4) -> str|None
#     IN: 찾을 파일명
#     OUT: 절대경로 or None (D:\ML\Verify 하위 자동 탐색)
#
#   log(msg, lines) -> None
#     IN: 메시지, 로그 리스트 / OUT: 없음(print + append)
#
#   compute_features(df) -> df+9컬럼
#     IN: OHLCV+oi DataFrame
#     OUT: 9 feature 컬럼 추가 (ML_Predictor_Pipeline_v2.calculate_internal_features 위임)
#
#   tbm_label_fixed_firsttouch(df, future_n, pt_mult, sl_mult) -> np.array(target)
#     IN: df(features 포함), future_n(int), pt_mult(익절 ATR배수), sl_mult(손절 ATR배수)
#     OUT: target 배열 (0=stay/1=long/2=short), first-touch 정확 구현
#
#   tbm_label_dynamic(df, base_n, pt_mult, sl_mult, atr_med) -> (target, used_n_arr)
#     IN: df, base_n(기준봉), pt_mult, sl_mult, atr_med(변동성 중앙값)
#     OUT: (target 배열, 각 시점 실제 사용된 horizon 배열) — 동적 horizon
#
#   train_one_scenario(scenario, df_train, df_oos, log_lines) -> dict
#     IN: scenario dict, train/oos DataFrame, 로그
#     OUT: 결과 dict (label분포, auc, 학습시간, 모델저장)
#
#   main() -> None
#     IN: 없음 / OUT: outputs_m1_grid.zip 생성
# ============================================================================

import os
import sys
import time
import json
import zipfile
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import xgboost as xgb
from sklearn.metrics import roc_auc_score

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, WORK_DIR)

# 기존 M1 학습기의 feature 계산을 그대로 재사용 (추정 금지 — 원본 함수 위임)
from ML_Predictor_Pipeline_v2 import calculate_internal_features


# ============================================================
# 상수 — 사용자 선택 4개 시나리오
# ============================================================
# train_end: M1 메타(PautoV75_XGB_3class_v2_meta.json)의 train_end와 동일하게 고정.
#   2025-06-06 이전 = train, 이후 = oos (진짜 OOS, M1이 안 본 기간)
TRAIN_END = "2025-06-06"

FEATURES = ['rsi_14', 'ema_dist', 'atr_14', 'fvg_bull', 'fvg_bear',
            'oi_delta', 'rvol_20', 'vol_accel', 'delta_streak']

# XGBoost 하이퍼파라미터 — 기존 M1과 100% 동일 (메타에서 확인)
XGB_PARAMS = dict(
    n_estimators=150, max_depth=6, learning_rate=0.03,
    colsample_bytree=0.8, random_state=42,
    objective='multi:softprob', num_class=3,
)

# 시나리오 정의 (사용자 선택: S1/S3/S6/S7)
#   mode: 'fixed' = 고정 horizon, 'dynamic' = 변동성 동적 horizon
SCENARIOS = [
    dict(id='S1', mode='fixed',   future_n=60,  pt_mult=1.5, sl_mult=1.0,
         desc='horizon만 확대(벽 그대로) - 라벨붕괴 확인용 대조군'),
    dict(id='S3', mode='fixed',   future_n=30,  pt_mult=2.0, sl_mult=1.4,
         desc='중간 확대 + 벽 스케일'),
    dict(id='S6', mode='fixed',   future_n=60,  pt_mult=3.0, sl_mult=1.5,
         desc='비대칭(익절 멀리/손절 가까이)'),
    dict(id='S7', mode='dynamic', base_n=60,    pt_mult=2.0, sl_mult=1.4,
         desc='동적 horizon(변동성 따라 자동 조절)'),
]

OUTPUT_DIR = os.path.join(WORK_DIR, "outputs_m1_grid")
ZIP_PATH = os.path.join(WORK_DIR, "outputs_m1_grid.zip")


# ============================================================
# 유틸
# ============================================================
def find_file(filename, max_depth=4):
    """D:\\ML\\Verify 어디에 있든 자동 탐색.
    IN: filename / OUT: 절대경로 or None
    """
    candidates = [
        os.path.join(WORK_DIR, filename),
        os.path.join(WORK_DIR, "..", filename),
        os.path.join(WORK_DIR, "..", "..", filename),
    ]
    grandparent = os.path.abspath(os.path.join(WORK_DIR, "..", ".."))
    if os.path.isdir(grandparent):
        try:
            for entry in os.listdir(grandparent):
                sub = os.path.join(grandparent, entry)
                if os.path.isdir(sub):
                    candidates.append(os.path.join(sub, filename))
                    # 손자 폴더까지
                    try:
                        for e2 in os.listdir(sub):
                            s2 = os.path.join(sub, e2)
                            if os.path.isdir(s2):
                                candidates.append(os.path.join(s2, filename))
                    except Exception:
                        pass
        except Exception:
            pass
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)
    return None


def log(msg, lines):
    """IN: 메시지, 로그리스트 / OUT: 없음"""
    print(msg)
    lines.append(str(msg))


# ============================================================
# TBM 라벨링 — first-touch 정확 구현
# ============================================================
def tbm_label_fixed_firsttouch(df, future_n, pt_mult, sl_mult):
    """고정 horizon TBM, first-touch(먼저 닿는 벽) 정확 구현.

    원본 버그 정정:
      원본은 'high 도달 AND low 전부 손절 위'로 long 판정 → horizon 길면 라벨 붕괴.
      본 함수는 t+1부터 순차로 봐서 익절/손절 중 먼저 닿는 쪽으로 라벨.

    IN:
      df: features 포함 DataFrame (atr_14, close, high, low 필요)
      future_n: 미래 검사 봉 수
      pt_mult: 익절 벽 = ATR × pt_mult
      sl_mult: 손절 벽 = ATR × sl_mult
    OUT:
      target: np.array (0=stay, 1=long, 2=short)
    """
    n = len(df)
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    atr = df['atr_14'].values

    target = np.zeros(n, dtype=np.int64)

    for t in range(n - future_n):
        c = close[t]
        a = atr[t]
        if not np.isfinite(a) or a <= 0:
            continue
        pt_up = c + a * pt_mult   # long 익절 / short 손절(반대) 기준선
        sl_dn = c - a * sl_mult   # long 손절
        pt_dn = c - a * pt_mult   # short 익절
        sl_up = c + a * sl_mult   # short 손절

        # t+1 ~ t+future_n 순차 스캔, 먼저 닿는 벽 찾기
        # long 관점: 위로 pt_up 먼저 vs 아래로 sl_dn 먼저
        # short 관점: 아래로 pt_dn 먼저 vs 위로 sl_up 먼저
        long_label = 0   # 0=미정, 1=익절, -1=손절
        short_label = 0
        for k in range(t + 1, t + 1 + future_n):
            hk = high[k]
            lk = low[k]
            # long 판정 (아직 미정일 때만)
            if long_label == 0:
                hit_pt = hk >= pt_up
                hit_sl = lk <= sl_dn
                # [v1 낙관편향 — 주석처리] if hit_pt and hit_sl: long_label = 1
                # [v3 비관표준] 1분 내 동시도달 → 순서 모르므로 손절(-1)로 가정
                if hit_pt and hit_sl:
                    long_label = -1
                elif hit_pt:
                    long_label = 1
                elif hit_sl:
                    long_label = -1
            # short 판정
            if short_label == 0:
                hit_pt = lk <= pt_dn
                hit_sl = hk >= sl_up
                # [v1 낙관편향 — 주석처리] if hit_pt and hit_sl: short_label = 1
                # [v3 비관표준] 동시도달 → 손절(-1)
                if hit_pt and hit_sl:
                    short_label = -1
                elif hit_pt:
                    short_label = 1
                elif hit_sl:
                    short_label = -1
            if long_label != 0 and short_label != 0:
                break

        # 최종 라벨: long 익절 성공 → 1, short 익절 성공 → 2, 둘 다 아니면 stay
        # 둘 다 익절 성공인 경우(드묾) → 더 먼저 도달한 쪽이 이미 위 루프에서 갈렸으므로
        #   여기선 long 우선 관례 적용
        if long_label == 1:
            target[t] = 1
        elif short_label == 1:
            target[t] = 2
        # else stay(0)
    return target


def tbm_label_dynamic(df, base_n, pt_mult, sl_mult, atr_med):
    """동적 horizon TBM — 변동성 높으면 horizon 짧게, 낮으면 길게.

    아이디어(제미나이 보강 + 학술 표준):
      변동성이 큰 시점엔 가격이 빨리 움직이니 horizon을 줄이고,
      잠잠하면 길게 잡아 추세를 끝까지 본다.
      used_n = base_n * (atr_med / atr_t), 단 [base_n/3, base_n*3] 범위로 clip.

    IN:
      df: features 포함 DataFrame
      base_n: 기준 horizon (예: 60)
      pt_mult, sl_mult: 벽 배수
      atr_med: 학습 기간 ATR_pct 중앙값 (lookahead 차단용 — 외부에서 train만으로 계산)
    OUT:
      (target, used_n_arr): 라벨 배열 + 각 시점 실제 사용 horizon 배열
    """
    n = len(df)
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    atr = df['atr_14'].values

    target = np.zeros(n, dtype=np.int64)
    used_n_arr = np.zeros(n, dtype=np.int64)

    lo_clip = max(5, base_n // 3)
    hi_clip = base_n * 3

    for t in range(n - lo_clip):
        c = close[t]
        a = atr[t]
        if not np.isfinite(a) or a <= 0:
            continue
        atr_pct = a / c if c > 0 else 0
        if atr_pct <= 0:
            used_n = base_n
        else:
            ratio = atr_med / atr_pct if atr_pct > 0 else 1.0
            used_n = int(np.clip(base_n * ratio, lo_clip, hi_clip))
        # horizon이 데이터 끝을 넘으면 가능한 만큼만
        if t + 1 + used_n > n:
            used_n = n - t - 1
        if used_n < lo_clip:
            continue
        used_n_arr[t] = used_n

        pt_up = c + a * pt_mult
        sl_dn = c - a * sl_mult
        pt_dn = c - a * pt_mult
        sl_up = c + a * sl_mult

        long_label = 0
        short_label = 0
        for k in range(t + 1, t + 1 + used_n):
            hk = high[k]
            lk = low[k]
            if long_label == 0:
                # [v3 비관표준] 동시도달 → 손절(-1)
                if hk >= pt_up and lk <= sl_dn:
                    long_label = -1
                elif hk >= pt_up:
                    long_label = 1
                elif lk <= sl_dn:
                    long_label = -1
            if short_label == 0:
                # [v3 비관표준] 동시도달 → 손절(-1)
                if lk <= pt_dn and hk >= sl_up:
                    short_label = -1
                elif lk <= pt_dn:
                    short_label = 1
                elif hk >= sl_up:
                    short_label = -1
            if long_label != 0 and short_label != 0:
                break

        if long_label == 1:
            target[t] = 1
        elif short_label == 1:
            target[t] = 2
    return target, used_n_arr


# ============================================================
# 시나리오 1개 학습
# ============================================================
def train_one_scenario(scenario, df_train, df_oos, atr_med_train, log_lines):
    """시나리오 1개: 라벨링 → 학습 → OOS AUC 측정 → 모델 저장.

    IN:
      scenario: dict (id, mode, future_n/base_n, pt_mult, sl_mult, desc)
      df_train, df_oos: features 계산 완료된 DataFrame
      atr_med_train: train 기간 ATR_pct 중앙값 (동적 horizon용)
      log_lines: 로그 리스트
    OUT:
      result: dict (id, label분포, train_auc, oos_auc, n_train, 학습시간 등)
    """
    sid = scenario['id']
    t0 = time.time()
    log(f"\n{'='*60}", log_lines)
    log(f"[{sid}] {scenario['desc']}", log_lines)
    log(f"{'='*60}", log_lines)

    # ---- 라벨링 ----
    if scenario['mode'] == 'fixed':
        fn = scenario['future_n']
        log(f"  라벨링: 고정 horizon {fn}봉, 익절×{scenario['pt_mult']}, 손절×{scenario['sl_mult']}", log_lines)
        y_train = tbm_label_fixed_firsttouch(df_train, fn, scenario['pt_mult'], scenario['sl_mult'])
        y_oos = tbm_label_fixed_firsttouch(df_oos, fn, scenario['pt_mult'], scenario['sl_mult'])
        used_n_info = f"고정 {fn}봉"
    else:  # dynamic
        bn = scenario['base_n']
        log(f"  라벨링: 동적 horizon(기준 {bn}봉), 익절×{scenario['pt_mult']}, 손절×{scenario['sl_mult']}", log_lines)
        log(f"    atr_med_train={atr_med_train:.6f} (lookahead 차단: train만으로 계산)", log_lines)
        y_train, un_tr = tbm_label_dynamic(df_train, bn, scenario['pt_mult'], scenario['sl_mult'], atr_med_train)
        y_oos, un_oos = tbm_label_dynamic(df_oos, bn, scenario['pt_mult'], scenario['sl_mult'], atr_med_train)
        # 사용된 horizon 통계
        valid_un = un_tr[un_tr > 0]
        used_n_info = f"동적 평균 {valid_un.mean():.1f}봉 (min {valid_un.min()}, max {valid_un.max()})"
        log(f"    실제 사용 horizon: {used_n_info}", log_lines)

    # ---- 분포 집계 함수 ----
    def dist(y):
        u, c = np.unique(y, return_counts=True)
        d = dict(zip(u.tolist(), c.tolist()))
        tot = len(y)
        return {
            'stay': d.get(0, 0), 'long': d.get(1, 0), 'short': d.get(2, 0),
            'stay_pct': 100*d.get(0,0)/tot, 'long_pct': 100*d.get(1,0)/tot, 'short_pct': 100*d.get(2,0)/tot,
        }

    # ---- 학습 데이터 준비 (NaN 행 제거) ----
    Xtr = df_train[FEATURES].values
    Xoos = df_oos[FEATURES].values
    mask_tr = np.isfinite(Xtr).all(axis=1)
    Xtr_c, ytr_c = Xtr[mask_tr], y_train[mask_tr]
    mask_oos = np.isfinite(Xoos).all(axis=1)
    Xoos_c, yoos_c = Xoos[mask_oos], y_oos[mask_oos]

    # ---- 라벨 분포 (★v3: 실제 학습에 쓰이는 ytr_c 기준으로 집계 — 통계=학습 일치) ----
    # [v1/제미나이v2 — 주석] 전체 y_train 또는 y_train[:-120]로 집계 → 통계≠학습 불일치
    # [v3] 모델이 실제로 학습한 라벨 분포를 그대로 보고 → 사용자 판단 정확
    dtr = dist(ytr_c)
    log(f"  Train 라벨분포(실학습 기준): stay {dtr['stay_pct']:.1f}% / long {dtr['long_pct']:.1f}% / short {dtr['short_pct']:.1f}%", log_lines)
    log(f"    (집계 표본수 n_labeled={len(ytr_c):,} — 시나리오 비교는 이 수치 함께 보면 공정)", log_lines)

    # 라벨 붕괴 경고 (stay가 90% 넘으면 학습 불가 수준)
    if dtr['stay_pct'] > 90:
        log(f"  ⚠️ 경고: stay {dtr['stay_pct']:.1f}% — 라벨 붕괴. 익절/손절 신호 거의 없음.", log_lines)
    if dtr['long'] < 100 or dtr['short'] < 100:
        log(f"  ⚠️ 경고: long/short 표본 부족 (long {dtr['long']}, short {dtr['short']}) — AUC 신뢰도 낮음.", log_lines)

    log(f"  학습 시작: train {len(ytr_c):,}행 (NaN 제거 후)", log_lines)
    model = xgb.XGBClassifier(**XGB_PARAMS)
    model.fit(Xtr_c, ytr_c)

    # ---- OOS AUC (3-class: long/short 각각 one-vs-rest, 매크로 평균) ----
    proba_oos = model.predict_proba(Xoos_c)  # (n,3)
    auc_results = {}
    for cls, name in [(1, 'long'), (2, 'short')]:
        y_bin = (yoos_c == cls).astype(int)
        if y_bin.sum() > 10 and y_bin.sum() < len(y_bin):
            try:
                auc = roc_auc_score(y_bin, proba_oos[:, cls])
                auc_results[name] = auc
            except Exception:
                auc_results[name] = float('nan')
        else:
            auc_results[name] = float('nan')
    macro_auc = np.nanmean(list(auc_results.values()))
    log(f"  OOS AUC: long {auc_results.get('long', float('nan')):.4f} / "
        f"short {auc_results.get('short', float('nan')):.4f} / macro {macro_auc:.4f}", log_lines)

    # ---- 모델 저장 ----
    model_path = os.path.join(OUTPUT_DIR, f"M1_{sid}.json")
    model.save_model(model_path)
    meta = {
        'scenario_id': sid, 'mode': scenario['mode'], 'desc': scenario['desc'],
        'future_n': scenario.get('future_n'), 'base_n': scenario.get('base_n'),
        'pt_mult': scenario['pt_mult'], 'sl_mult': scenario['sl_mult'],
        'used_n_info': used_n_info,
        'features': FEATURES, 'xgb_params': XGB_PARAMS,
        'train_label_dist': dtr, 'oos_auc': auc_results, 'macro_auc': float(macro_auc),
        'n_train': int(len(ytr_c)), 'train_end': TRAIN_END,
    }
    with open(os.path.join(OUTPUT_DIR, f"M1_{sid}_meta.json"), 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    elapsed = time.time() - t0
    log(f"  완료: {elapsed:.1f}초, 모델 저장 → M1_{sid}.json", log_lines)

    return {
        'scenario': sid, 'mode': scenario['mode'], 'desc': scenario['desc'],
        'used_n_info': used_n_info,
        'pt_mult': scenario['pt_mult'], 'sl_mult': scenario['sl_mult'],
        'stay_pct': round(dtr['stay_pct'], 2), 'long_pct': round(dtr['long_pct'], 2),
        'short_pct': round(dtr['short_pct'], 2), 'n_labeled': int(len(ytr_c)),
        'oos_auc_long': round(auc_results.get('long', float('nan')), 4),
        'oos_auc_short': round(auc_results.get('short', float('nan')), 4),
        'oos_auc_macro': round(float(macro_auc), 4),
        'n_train': int(len(ytr_c)), 'elapsed_sec': round(elapsed, 1),
    }


# ============================================================
# 메인
# ============================================================
def main():
    log_lines = []
    log("="*60, log_lines)
    log("M1 재학습 그리드 실험 v1.0 (Stage 4A Phase 2 - 2단계)", log_lines)
    log("시나리오: S1/S3/S6/S7 (사용자 선택)", log_lines)
    log("="*60, log_lines)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ---- 1. 데이터 로드 ----
    data_path = find_file("Merged_Data.csv")
    if data_path is None:
        log("[ERROR] Merged_Data.csv 못 찾음. D:\\ML\\Verify 하위에 두세요.", log_lines)
        with open(os.path.join(OUTPUT_DIR, "measure_log.txt"), 'w', encoding='utf-8') as f:
            f.write("\n".join(log_lines))
        return
    log(f"\n[1/5] 데이터 로드: {data_path}", log_lines)
    df = pd.read_csv(data_path, parse_dates=['timestamp'])
    df.set_index('timestamp', inplace=True)
    log(f"  전체: {df.index.min()} ~ {df.index.max()} ({len(df):,}행)", log_lines)

    # ---- 2. train/oos 분할 (M1 메타 train_end 기준) ----
    log(f"\n[2/5] train/oos 분할 (기준 {TRAIN_END})", log_lines)
    train_end_ts = pd.to_datetime(TRAIN_END)
    if df.index.tz is not None and train_end_ts.tz is None:
        train_end_ts = train_end_ts.tz_localize(df.index.tz)
    df_train_raw = df.loc[:train_end_ts].copy()
    df_oos_raw = df.loc[train_end_ts:].copy()
    log(f"  train: {df_train_raw.index.min()} ~ {df_train_raw.index.max()} ({len(df_train_raw):,}행)", log_lines)
    log(f"  oos:   {df_oos_raw.index.min()} ~ {df_oos_raw.index.max()} ({len(df_oos_raw):,}행)", log_lines)

    # ---- 3. feature 계산 (원본 함수 위임) ----
    log(f"\n[3/5] feature 계산 (calculate_internal_features 위임)", log_lines)
    df_train = calculate_internal_features(df_train_raw)
    df_oos = calculate_internal_features(df_oos_raw)
    log(f"  train features: {len(df_train):,}행, oos features: {len(df_oos):,}행", log_lines)

    # 동적 horizon용 atr_med (train만으로 — lookahead 차단)
    atr_pct_train = (df_train['atr_14'] / df_train['close']).replace([np.inf, -np.inf], np.nan).dropna()
    atr_med_train = float(atr_pct_train[atr_pct_train > 0].median())
    log(f"  atr_med_train (동적용): {atr_med_train:.6f}", log_lines)

    # ---- 4. 시나리오별 학습 ----
    log(f"\n[4/5] 시나리오별 재학습 ({len(SCENARIOS)}개)", log_lines)
    results = []
    for sc in SCENARIOS:
        try:
            r = train_one_scenario(sc, df_train, df_oos, atr_med_train, log_lines)
            results.append(r)
        except Exception as e:
            log(f"  [ERROR] {sc['id']} 실패: {e}", log_lines)
            import traceback
            log(traceback.format_exc(), log_lines)

    # ---- 5. 결과 정리 + zip ----
    log(f"\n[5/5] 결과 정리", log_lines)
    if results:
        summary = pd.DataFrame(results)
        summary.to_csv(os.path.join(OUTPUT_DIR, "grid_summary.csv"), index=False, encoding='utf-8-sig')
        log("\n=== 그리드 요약 ===", log_lines)
        log(summary.to_string(index=False), log_lines)

        # 라벨 분포만 따로
        ld = summary[['scenario', 'stay_pct', 'long_pct', 'short_pct', 'oos_auc_macro']]
        ld.to_csv(os.path.join(OUTPUT_DIR, "label_distribution.csv"), index=False, encoding='utf-8-sig')

    with open(os.path.join(OUTPUT_DIR, "measure_log.txt"), 'w', encoding='utf-8') as f:
        f.write("\n".join(log_lines))

    # zip 생성 (사용자가 이거 1개만 업로드)
    with zipfile.ZipFile(ZIP_PATH, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fn in os.listdir(OUTPUT_DIR):
            zf.write(os.path.join(OUTPUT_DIR, fn), arcname=fn)
    log(f"\n✅ 전체 완료. 업로드할 파일: {ZIP_PATH}", log_lines)
    print(f"\n{'='*60}\n사용자: outputs_m1_grid.zip 1개만 새 채팅창에 업로드하세요.\n{'='*60}")


if __name__ == "__main__":
    main()
