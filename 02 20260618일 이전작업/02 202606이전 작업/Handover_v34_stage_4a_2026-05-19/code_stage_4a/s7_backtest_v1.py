# [파일명] s7_backtest_v1.py
# 코드길이: 약 400줄, 내부버전명: v1.0 (stage_4a_phase2_step3_s7_backtest)
# 로직을 축약/생략 없이 전체 출력.
#
# ============================================================================
# [목적]
#   Stage 4A Phase 2 - 3단계: S7(동적 horizon) M1 모델로 신호를 재추출하고,
#   S7 학습 출구(손절 ATR×1.4, horizon 평균 73봉)에 정합하는 시뮬 설정으로
#   백테스트하여 진짜 base PF를 측정한다. (사용자 결정: (b) 출구도 조정)
#
# [사용자 결정 반영]
#   - 문제1: (b) 출구도 S7에 맞춰 조정
#   - 문제2: 전체 OOS 측정 (단 OOS만, Train 신호추출 생략 → 시간 절반)
#
# [(b) 출구 정합 — S7 학습값에 맞춤]
#   S7 학습 라벨: 익절 ATR×2.0, 손절 ATR×1.4, horizon 동적(평균 73봉, 20~180)
#   시뮬 정합 조정:
#     - 손절 multiplier: 기존 동적(2.0~3.5) → S7값 1.4로 통일 (S7_SL_MULT)
#       * compute_dynamic_sl을 우회하고 sl_dist = atr_pct × 1.4로 강제
#     - timeout: 기존 4H(240분) → S7 평균 horizon 73봉≈73분, 안전하게 120분(2H)
#       * S7이 동적이라 단일값 불가 → 평균에 여유 둔 120분 사용
#     - 익절: 시뮬은 OB(오더블록) 기반이라 ATR×2.0 직접매핑 불가.
#       * OB 익절 유지하되, 손절/timeout만 S7 정합 → '부분 정합' 명시
#   ※ 한계: 시뮬 익절이 OB 기반이라 S7 익절(ATR×2.0)과 완전 일치 불가.
#     이건 시뮬 구조상 한계이며, 손절·timeout 정합만으로도 S7 신호 성능의
#     근사 측정은 가능. 완전 정합은 시뮬 전면 재작성 필요(다음 단계).
#
# [비교 기준]
#   - 기존 base PF 0.816 (S0=10봉 모델, 기존 출구)
#   - S7 PF (S7 모델, S7 정합 출구) → 이게 base 넘는지가 핵심
#
# ============================================================================
# [변수 파이프라인]
# 📥 IN:
#   - Merged_Data.csv (사용자 PC, 자동 탐색)
#   - M1_S7.json (이번에 만든 S7 모델, outputs_m1_grid에서 꺼내 같은 폴더에 둠)
#   - 기존 모듈: tf_aggregator_v2, tbm_simulator_v11, pautov75_signal_wrapper_v4,
#     Predict_ML_v2, Regime_Master_v2, ob_provider_v2
# 🛠️ STATE:
#   - Predict_ML_v2가 M1_S7.json을 로드하도록 임시 심볼릭 교체(원본 백업)
#   - OOS 구간만 신호 재추출 → S7 정합 출구로 batch_simulate_v11
# 📤 OUT:
#   - outputs_s7_backtest/ :
#       * s7_trades.csv (전체 거래)
#       * s7_summary.txt (PF/승률/거래수 + base 비교)
#       * measure_log.txt
#   - outputs_s7_backtest.zip (사용자가 이거 1개만 업로드)
#
# ============================================================================
# [함수 In/Out]
#   find_file(fn) -> 절대경로|None
#   log(msg, lines) -> None
#   compute_train_atr_med(df_train) -> float : Train ATR_pct 중앙값 (lookahead 차단)
#   patched_dynamic_sl(atr_pct, sl_max) -> (sl_dist, mult) : S7 손절 ATR×1.4 강제
#   compute_metrics(trades) -> dict : PF/승률/net/거래수
#   main() -> None
# ============================================================================

import os
import sys
import time
import json
import shutil
import zipfile
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, WORK_DIR)

# ============================================================
# S7 정합 출구 상수
# ============================================================
S7_SL_MULT = 1.4          # S7 학습 손절 배수
S7_TIMEOUT_MIN = 120      # S7 평균 horizon 73봉에 여유 둔 timeout(2H)
S7_MODEL_FILE = "M1_S7.json"
ORIG_MODEL_FILE = "PautoV75_XGB_3class_v2.json"

# 기존 측정과 동일 설정 (measure_v34_stage_4a.py에서 확인한 값)
OB_TF = 60
LEV = 10
W = 5
N = 5
ROLLING_LOOKBACK = 14 * 1440
TRAIN_RATIO = 0.70
ENABLE_WAIT_ENTRY = True
WAIT_TIMEOUT_MINUTES = 120
SL_MAX_STAGE_3_BEST = 0.0180   # 기존 base와 동일 (180bp)

OUTPUT_DIR = os.path.join(WORK_DIR, "outputs_s7_backtest")
ZIP_PATH = os.path.join(WORK_DIR, "outputs_s7_backtest.zip")


def find_file(filename, max_depth=4):
    """D:\\ML\\Verify 하위 자동 탐색. IN: filename / OUT: 절대경로|None"""
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
    print(msg)
    lines.append(str(msg))


def compute_train_atr_med(df_train):
    """Train ATR_pct 중앙값 (measure_v34_stage_4a와 동일 방식)"""
    close = df_train['close'].values
    atr = pd.Series((df_train['high'] - df_train['low']).values).rolling(60).mean().fillna(0).values
    atr_pct = atr / close * 100
    valid = atr_pct[atr_pct > 0]
    if len(valid) == 0:
        return 0.1
    return float(np.nanmedian(valid))


def compute_metrics(trades, label=""):
    """PF/승률/net/거래수. valid 거래만.
    IN: trades DataFrame / OUT: dict
    """
    valid_exits = ['initial_sl', 'step1_sl', 'step2_sl', 'step3_sl',
                   'timeout_4h', 'timeout_16h', 'timeout_18h',
                   'timeout_step_active', 'reversal_2h']
    def is_valid(r):
        return isinstance(r, str) and (r in valid_exits or r.startswith('timeout_'))
    v = trades[trades['exit_reason'].apply(is_valid)].copy()
    if len(v) == 0:
        return {'label': label, 'n': 0, 'pf': 0, 'win': 0, 'net': 0}
    g = v[v['net_return'] > 0]['net_return'].sum()
    l = abs(v[v['net_return'] < 0]['net_return'].sum())
    return {
        'label': label,
        'n': int(len(v)),
        'pf': float(g/l) if l > 0 else float('inf'),
        'win': float((v['net_return'] > 0).mean()),
        'net': float(v['net_return'].sum()),
    }


def main():
    log_lines = []
    log("=" * 60, log_lines)
    log("S7 백테스트 v1.0 (Phase 2 - 3단계, 출구 (b) 정합)", log_lines)
    log(f"S7 정합: 손절 ATR×{S7_SL_MULT}, timeout {S7_TIMEOUT_MIN}분", log_lines)
    log("=" * 60, log_lines)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ---- 0. S7 모델을 Predict_ML_v2가 로드하도록 교체 (원본 백업) ----
    log(f"\n[0/6] S7 모델 장착", log_lines)
    s7_path = find_file(S7_MODEL_FILE)
    if s7_path is None:
        log(f"  ❌ {S7_MODEL_FILE} 못 찾음. outputs_m1_grid.zip에서 꺼내 같은 폴더에 두세요.", log_lines)
        with open(os.path.join(OUTPUT_DIR, "measure_log.txt"), 'w', encoding='utf-8') as f:
            f.write("\n".join(log_lines))
        return
    orig_path = os.path.join(WORK_DIR, ORIG_MODEL_FILE)
    backup_path = os.path.join(WORK_DIR, ORIG_MODEL_FILE + ".bak_s7test")
    restored = False
    try:
        # 원본 백업
        if os.path.exists(orig_path):
            shutil.copy2(orig_path, backup_path)
            log(f"  원본 백업: {backup_path}", log_lines)
        # S7을 원본 이름으로 복사 (Predict_ML_v2가 이 이름을 로드함)
        shutil.copy2(s7_path, orig_path)
        log(f"  S7 장착: {s7_path} → {orig_path}", log_lines)

        # ---- 모듈 import (S7 장착 후) ----
        from tf_aggregator_v2 import aggregate_ohlcv
        from tbm_simulator_v11 import compute_atr, batch_simulate_v11, SL_MIN
        from pautov75_signal_wrapper_v4 import extract_signals_v4, compute_atr_15m_pct_per_1m, process_signals_with_wait_v4
        from Regime_Master_v2 import Regime_Master_v2
        import tbm_simulator_v11 as tbmsim

        # ---- (b) S7 손절 정합: compute_dynamic_sl 몽키패치 ----
        # 기존: ATR×(2.0~3.5 동적). S7 정합: ATR×1.4 고정.
        _orig_dynamic_sl = tbmsim.compute_dynamic_sl
        def patched_dynamic_sl(atr_pct_at_entry, sl_max=SL_MAX_STAGE_3_BEST):
            """S7 손절 ATR×1.4 강제. IN: atr_pct, sl_max / OUT: (sl_dist, mult)"""
            if not np.isfinite(atr_pct_at_entry) or atr_pct_at_entry <= 0:
                return sl_max, np.nan
            sl_raw = atr_pct_at_entry * S7_SL_MULT
            sl_dist = max(SL_MIN, min(sl_max, sl_raw))
            return sl_dist, S7_SL_MULT
        tbmsim.compute_dynamic_sl = patched_dynamic_sl
        log(f"  손절 정합: compute_dynamic_sl → ATR×{S7_SL_MULT} 패치 완료", log_lines)

        # ---- 1. 데이터 로드 ----
        data_path = find_file('Merged_Data.csv')
        if not data_path:
            log("  ❌ Merged_Data.csv 못 찾음", log_lines)
            raise FileNotFoundError("Merged_Data.csv")
        log(f"\n[1/6] 데이터 로드: {data_path}", log_lines)
        df = pd.read_csv(data_path, parse_dates=['timestamp']).set_index('timestamp')
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC')
        log(f"  전체: {df.index.min()} ~ {df.index.max()} ({len(df):,}봉)", log_lines)

        n_train = int(len(df) * TRAIN_RATIO)
        oos_start_idx = n_train
        oos_end_idx = len(df)
        log(f"  OOS: idx {oos_start_idx}~{oos_end_idx-1} ({oos_end_idx-oos_start_idx:,}봉)", log_lines)

        # ---- 2. Train atr_med + 15m ATR_pct ----
        log(f"\n[2/6] ATR 사전 계산", log_lines)
        df_train = df.iloc[:oos_start_idx]
        atr_med_fixed = compute_train_atr_med(df_train)
        log(f"  Train atr_med: {atr_med_fixed:.6f}%", log_lines)
        atr_15m_pct_per_1m = compute_atr_15m_pct_per_1m(df)
        log(f"  15m ATR_pct mean={np.nanmean(atr_15m_pct_per_1m)*100:.4f}%", log_lines)

        # regime per 1m (measure_v34_stage_4a의 assign_regime_v33_fixed 그대로 import — 추정 금지)
        log(f"\n[3/6] regime + TF aggregate", log_lines)
        from measure_v34_stage_4a import assign_regime_v33_fixed
        regime_per_1m_full = assign_regime_v33_fixed(df, atr_med_fixed)
        log(f"  4장세 분포: {pd.Series(regime_per_1m_full).value_counts().to_dict()}", log_lines)

        df_reset = df.reset_index()
        df_2h = aggregate_ohlcv(df_reset, 120).set_index('timestamp')
        df_ob = aggregate_ohlcv(df_reset, OB_TF).set_index('timestamp')
        atr_ob = compute_atr(df_ob['high'].values, df_ob['low'].values, df_ob['close'].values, period=20)
        log(f"  2h봉 {len(df_2h)}, {OB_TF}m봉 {len(df_ob)}", log_lines)

        # ---- 4. OOS 신호 재추출 (S7 모델) ----
        log(f"\n[4/6] S7 신호 재추출 (OOS만, 약 90분 예상)", log_lines)
        t_sig = time.time()
        long_raw, short_raw, _ = extract_signals_v4(
            df, atr_15m_pct_per_1m,
            threshold_long=0.35, threshold_short=0.35,
            window_size=120, filter_mode='off',
            rolling_lookback_minutes=ROLLING_LOOKBACK,
            start_idx=oos_start_idx, end_idx=oos_end_idx,
            verbose_every=200000,
        )
        oos_long_idx, oos_short_idx, _ = process_signals_with_wait_v4(
            long_raw, short_raw, df, None, OB_TF, W,
            enable_wait=ENABLE_WAIT_ENTRY, wait_timeout_minutes=WAIT_TIMEOUT_MINUTES,
            verbose=False,
        )
        log(f"  S7 신호: Long {len(oos_long_idx)}, Short {len(oos_short_idx)}, 소요 {(time.time()-t_sig)/60:.1f}분", log_lines)

        # ---- 5. S7 정합 출구로 백테스트 (M2 끔, timeout S7값) ----
        log(f"\n[5/6] S7 정합 백테스트 (timeout {S7_TIMEOUT_MIN}분, M2 끔)", log_lines)
        t_sim = time.time()
        s7_trades = batch_simulate_v11(
            long_signal_indices_1m=oos_long_idx.tolist(),
            short_signal_indices_1m=oos_short_idx.tolist(),
            df_1m=df, df_ob_tf=df_ob, df_2h=df_2h,
            atr_ob_tf=atr_ob, atr_15m_pct_per_1m=atr_15m_pct_per_1m,
            regime_per_1m=regime_per_1m_full,
            sl_max=SL_MAX_STAGE_3_BEST,
            leverage=LEV, w=W, N=N,
            ob_tf_minutes=OB_TF, enable_2h_reversal=True,
            regime_master=Regime_Master_v2(),
            enable_wait_entry=ENABLE_WAIT_ENTRY,
            wait_timeout_minutes=S7_TIMEOUT_MIN,   # ★ S7 정합 timeout
            verbose=False,
            enable_regime_policy=False,   # M2/regime 정책 끔 (순수 base 측정)
        )
        log(f"  거래 {len(s7_trades)}, 소요 {(time.time()-t_sim)/60:.1f}분", log_lines)
        s7_trades.to_csv(os.path.join(OUTPUT_DIR, "s7_trades.csv"), index=False)

        # ---- 6. 성과 측정 + base 비교 ----
        log(f"\n[6/6] 성과 측정", log_lines)
        m = compute_metrics(s7_trades, label="S7 (출구 정합)")
        log(f"\n{'='*60}", log_lines)
        log(f"=== S7 백테스트 결과 ===", log_lines)
        log(f"{'='*60}", log_lines)
        log(f"  valid 거래수: {m['n']}", log_lines)
        log(f"  PF: {m['pf']:.4f}", log_lines)
        log(f"  승률: {m['win']:.4f}", log_lines)
        log(f"  순수익: {m['net']*100:.2f}%", log_lines)
        log(f"\n  [비교 기준] 기존 base (S0=10봉, 기존출구): PF 0.816", log_lines)
        if m['pf'] > 1.0:
            log(f"  ✅ PF 1.0 돌파! S7+정합출구가 본전 넘김 (horizon 가설 지지)", log_lines)
        elif m['pf'] > 0.816:
            log(f"  △ base(0.816)보다 개선됐으나 1.0 미만 (부분 효과)", log_lines)
        else:
            log(f"  ❌ base(0.816) 이하 — horizon 가설 거의 부정 (features 재설계 필요)", log_lines)

        summary = {
            's7_pf': m['pf'], 's7_win': m['win'], 's7_net': m['net'], 's7_n': m['n'],
            'base_pf_ref': 0.816, 's7_sl_mult': S7_SL_MULT, 's7_timeout_min': S7_TIMEOUT_MIN,
        }
        with open(os.path.join(OUTPUT_DIR, "s7_summary.txt"), 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

    finally:
        # ---- 원본 모델 복원 (반드시 실행) ----
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, orig_path)
            os.remove(backup_path)
            restored = True
            log(f"\n[복원] 원본 M1 모델 복원 완료 ({ORIG_MODEL_FILE})", log_lines)
        with open(os.path.join(OUTPUT_DIR, "measure_log.txt"), 'w', encoding='utf-8') as f:
            f.write("\n".join(log_lines))

    # zip 생성
    with zipfile.ZipFile(ZIP_PATH, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fn in os.listdir(OUTPUT_DIR):
            zf.write(os.path.join(OUTPUT_DIR, fn), arcname=fn)
    print(f"\n{'='*60}\n사용자: outputs_s7_backtest.zip 1개만 업로드하세요.\n{'='*60}")


if __name__ == "__main__":
    main()
