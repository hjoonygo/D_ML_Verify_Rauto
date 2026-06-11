# -*- coding: utf-8 -*-
"""
[파일명] run_all_stage_4a.py
코드길이: 약 320줄, 내부버전명: v2.0_verified
검증: run_all_stage_3_5.py 패턴 그대로 + measure 호출 + 자동 zip 추가

[목적] Stage 4A Phase 1 통합 실행
  사전 점검 → measure 호출 (Step 0~3 + train_meta_model_v1 자동 호출) → 작동 검증 → zip 압축

[실행]
  cd D:\\ML\\Verify\\Handover_v34_stage_4a_2026-05-19\\code_stage_4a
  python run_all_stage_4a.py

[옵션]
  --skip-confirm    사용자 y 입력 생략
  --check-only      사전 점검만
  --post-only       작동 검증만
"""
import os
import sys
import time
import shutil
import zipfile
import importlib
import inspect
import argparse
from datetime import datetime

try:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(WORK_DIR, "outputs_stage_4a")
sys.path.insert(0, WORK_DIR)


def find_file(filename):
    candidates = [
        os.path.join(WORK_DIR, filename),
        os.path.join(WORK_DIR, "..", filename),
        os.path.join(WORK_DIR, "..", "..", filename),
    ]
    grandparent = os.path.abspath(os.path.join(WORK_DIR, "..", ".."))
    if os.path.isdir(grandparent):
        try:
            for entry in os.listdir(grandparent):
                subpath = os.path.join(grandparent, entry)
                if os.path.isdir(subpath):
                    candidates.append(os.path.join(subpath, filename))
                    try:
                        for entry2 in os.listdir(subpath):
                            sub2 = os.path.join(subpath, entry2)
                            if os.path.isdir(sub2):
                                candidates.append(os.path.join(sub2, filename))
                    except (PermissionError, OSError):
                        pass
        except (PermissionError, OSError):
            pass
    for path in candidates:
        if os.path.exists(path):
            return os.path.abspath(path)
    return None


def _ok(msg):    print(f"  ✓ {msg}")
def _warn(msg):  print(f"  ⚠️ {msg}")
def _err(msg):   print(f"  ❌ {msg}")
def _info(msg):  print(f"    {msg}")


def preflight_check():
    """사전 점검 7단계."""
    print("\n" + "=" * 72)
    print(f"[사전 점검] {datetime.now()}")
    print("=" * 72)

    all_ok = True

    # [1/7] Python + 패키지
    print("\n[1/7] Python + 패키지")
    py = sys.version_info
    print(f"  Python: {py.major}.{py.minor}.{py.micro}")
    if py.major < 3 or (py.major == 3 and py.minor < 8):
        _err("Python 3.8+ 필요")
        all_ok = False
    else:
        _ok("Python OK")

    for pkg in ['pandas', 'numpy', 'xgboost', 'sklearn', 'scipy']:
        try:
            mod = importlib.import_module(pkg)
            _ok(f"{pkg} {getattr(mod, '__version__', 'unknown')}")
        except ImportError:
            _err(f"{pkg} 미설치 — pip install {pkg}")
            all_ok = False

    # [2/7] 폴더 구조
    print("\n[2/7] 폴더 구조")
    print(f"  WORK_DIR:   {WORK_DIR}")
    print(f"  OUTPUT_DIR: {OUTPUT_DIR}")
    grandparent = os.path.abspath(os.path.join(WORK_DIR, "..", ".."))
    if 'Verify' in grandparent or 'verify' in grandparent.lower():
        _ok("Verify 폴더 인식")
    else:
        _warn(f"표준 경로: D:\\ML\\Verify\\Handover_v34_stage_4a_...\\code_stage_4a")

    # [3/7] 36개월 데이터
    print("\n[3/7] 36개월 raw 데이터")
    raw = find_file('Merged_Data.csv')
    if raw:
        size_mb = os.path.getsize(raw) / 1024 / 1024
        _ok(f"Merged_Data.csv: {raw} ({size_mb:.1f} MB)")
        if size_mb < 400 or size_mb > 500:
            _warn(f"크기 비정상 (기준 454.3 MB)")
    else:
        _err("Merged_Data.csv 못 찾음 (D:\\ML\\Verify\\에 있어야 함)")
        all_ok = False

    # [4/7] M1 모델 + 신호 캐시
    print("\n[4/7] M1 모델 + OOS 캐시")
    for f in ['PautoV75_XGB_3class_v2.json', 'PautoV75_XGB_3class_v2_meta.json']:
        p = find_file(f)
        if p:
            _ok(f"{f}: {p}")
        else:
            _err(f"{f} 못 찾음")
            all_ok = False

    cache = find_file('signals_cache_stage_3_5.pkl')
    if cache:
        size_mb = os.path.getsize(cache) / 1024 / 1024
        if size_mb < 0.01:
            _warn(f"signals_cache_stage_3_5.pkl 비어있음 ({size_mb:.2f} MB) — 재추출 (90분 추가)")
        else:
            _ok(f"signals_cache_stage_3_5.pkl: {size_mb:.1f} MB")
    else:
        _warn("signals_cache_stage_3_5.pkl 없음 — 재추출 (90분 추가)")

    oos_t = find_file('trades_s0_v10_baseline_sl180.csv')
    if oos_t:
        _ok(f"trades_s0_v10_baseline_sl180.csv: {oos_t}")
    else:
        _err("trades_s0_v10_baseline_sl180.csv 못 찾음 — M2 학습에 필요")
        all_ok = False

    # [5/7] 외부 모듈 + 시그니처
    print("\n[5/7] 외부 모듈 + 시그니처")
    required = ['tbm_simulator_v11', 'Predict_ML_v2', 'Regime_Master_v2',
                'pautov75_signal_wrapper_v4', 'tf_aggregator_v2',
                'ML_Predictor_Pipeline_v2',
                'measure_v34_stage_4a', 'train_meta_model_v1']
    for m in required:
        try:
            importlib.import_module(m)
            _ok(f"{m} OK")
        except Exception as e:
            _err(f"{m} 실패: {e}")
            all_ok = False

    # 시그니처 정확히 검증 — extract_signals_v4
    print("\n  pautov75_signal_wrapper_v4.extract_signals_v4 시그니처")
    try:
        from pautov75_signal_wrapper_v4 import extract_signals_v4
        sig = inspect.signature(extract_signals_v4)
        params = list(sig.parameters.keys())
        expected = ['df_1m', 'atr_15m_pct_per_1m', 'start_idx', 'end_idx']
        missing = [k for k in expected if k not in params]
        if missing:
            _err(f"누락 인자: {missing}")
            all_ok = False
        else:
            _ok(f"시그니처 OK")
    except Exception as e:
        _err(f"시그니처 확인 실패: {e}")
        all_ok = False

    # batch_simulate_v11 시그니처
    print("\n  tbm_simulator_v11.batch_simulate_v11 시그니처")
    try:
        from tbm_simulator_v11 import batch_simulate_v11
        sig = inspect.signature(batch_simulate_v11)
        params = list(sig.parameters.keys())
        expected = ['long_signal_indices_1m', 'short_signal_indices_1m', 'df_1m',
                    'df_ob_tf', 'df_2h', 'atr_ob_tf', 'atr_15m_pct_per_1m',
                    'regime_per_1m', 'sl_max', 'leverage', 'w', 'N']
        missing = [k for k in expected if k not in params]
        if missing:
            _err(f"누락 인자: {missing}")
            all_ok = False
        else:
            _ok(f"시그니처 OK")
    except Exception as e:
        _err(f"시그니처 확인 실패: {e}")
        all_ok = False

    # [6/7] 디스크
    print("\n[6/7] 디스크")
    try:
        usage = shutil.disk_usage(WORK_DIR)
        free_gb = usage.free / 1024**3
        print(f"  여유: {free_gb:.1f} GB")
        if free_gb < 5:
            _err("5GB 미만 — 위험"); all_ok = False
        elif free_gb < 10:
            _warn("10GB 미만 — 주의")
        else:
            _ok("여유 충분")
    except Exception as e:
        _warn(f"확인 실패: {e}")

    # [7/7] 출력 폴더
    print("\n[7/7] 출력 폴더")
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        _ok(f"{OUTPUT_DIR}")
        existing = os.listdir(OUTPUT_DIR)
        if existing:
            _warn(f"기존 파일 {len(existing)}개 — 덮어씌워질 수 있음")
    except Exception as e:
        _err(f"생성 실패: {e}"); all_ok = False

    # 요약
    print("\n" + "=" * 72)
    if all_ok:
        print(f"[✓ 사전 점검 통과] {datetime.now()}")
        print(f"\n작업 시간 예상:")
        print(f"  Step 0 (RM 분포):           5~10분")
        print(f"  Step 1 (Train 시뮬+features): 90~150분")
        print(f"  M2 학습 (자동):              5~15분")
        print(f"  Step 2 (OOS 5 시나리오):     25~50분")
        print(f"  총:                          2~4시간")
    else:
        print(f"[❌ 사전 점검 실패] 위 ❌ 해결 후 다시 실행")
    print("=" * 72)
    return all_ok


def post_run_validation():
    """작동 검증."""
    print("\n" + "=" * 72)
    print(f"[작동 검증] {datetime.now()}")
    print("=" * 72)
    all_ok = True

    if not os.path.exists(OUTPUT_DIR):
        _err(f"{OUTPUT_DIR} 없음")
        return False

    # 시나리오 trades csv 5개
    print("\n[1/4] 시나리오 trades csv 5개")
    for s in ['base_no_meta', 'meta_simple', 'meta_purged', 'meta_regime', 'meta_oos_only']:
        p = os.path.join(OUTPUT_DIR, f'trades_{s}.csv')
        if os.path.exists(p):
            try:
                import pandas as pd
                df = pd.read_csv(p)
                _ok(f"trades_{s}.csv: {len(df)}행")
            except Exception as e:
                _err(f"trades_{s}.csv: {e}"); all_ok = False
        else:
            _err(f"trades_{s}.csv 없음"); all_ok = False

    # 요약 csv
    print("\n[2/4] 요약 csv")
    p = os.path.join(OUTPUT_DIR, 'all_scenarios_stage_4a.csv')
    if os.path.exists(p):
        try:
            import pandas as pd
            df = pd.read_csv(p, index_col=0)
            _ok(f"all_scenarios_stage_4a.csv: {len(df)}행")
            print(f"\n  [PF 요약]")
            for idx in df.index:
                pf = df.loc[idx, 'pf'] if 'pf' in df.columns else 'N/A'
                print(f"    {idx}: PF={pf}")
        except Exception as e:
            _err(f"읽기 실패: {e}"); all_ok = False
    else:
        _err("all_scenarios_stage_4a.csv 없음"); all_ok = False

    # decision_tree csv
    p = os.path.join(OUTPUT_DIR, 'decision_tree_evaluation.csv')
    if os.path.exists(p):
        try:
            import pandas as pd
            df = pd.read_csv(p)
            _ok(f"decision_tree_evaluation.csv")
            for col in df.columns:
                val = df.iloc[0][col] if len(df) > 0 else 'N/A'
                _info(f"{col}: {val}")
        except Exception as e:
            _warn(f"읽기 실패: {e}")
    else:
        _err("decision_tree_evaluation.csv 없음"); all_ok = False

    # M2 모델 8개
    print("\n[3/4] M2 모델 8개 (outputs_stage_4a/ 통합)")
    for s in ['meta_simple', 'meta_purged', 'meta_regime', 'meta_oos_only']:
        for suffix in ['.json', '_meta.json']:
            p = os.path.join(OUTPUT_DIR, f'M2_{s}{suffix}')
            if os.path.exists(p):
                _ok(f"M2_{s}{suffix}")
            else:
                _err(f"M2_{s}{suffix} 없음"); all_ok = False

    # 추가 측정
    print("\n[4/4] 추가 측정")
    for f in ['additional_regime_master_distribution.csv',
              'additional_m1_prob_distribution.csv',
              'regime_master_at_entry.pkl',
              'signal_features_train_4a.pkl',
              'signal_features_oos_4a.pkl']:
        p = os.path.join(OUTPUT_DIR, f)
        if os.path.exists(p):
            _ok(f)
        else:
            _warn(f"{f} 없음")

    print("\n" + "=" * 72)
    if all_ok:
        print(f"[✓ 모두 통과]")
    else:
        print(f"[⚠️ 일부 누락]")
    print("=" * 72)
    return all_ok


def compress_outputs():
    """outputs_stage_4a/ 폴더 → outputs_stage_4a.zip."""
    if not os.path.exists(OUTPUT_DIR):
        _err(f"{OUTPUT_DIR} 없음")
        return None
    zip_path = os.path.join(WORK_DIR, "outputs_stage_4a.zip")
    print(f"\n[zip 압축] {zip_path}")
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(OUTPUT_DIR):
                for f in files:
                    src = os.path.join(root, f)
                    arc = os.path.relpath(src, WORK_DIR)
                    zf.write(src, arc)
        size_mb = os.path.getsize(zip_path) / 1024 / 1024
        _ok(f"완료: {zip_path} ({size_mb:.1f} MB)")
        return zip_path
    except Exception as e:
        _err(f"실패: {e}")
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-confirm', action='store_true')
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--post-only', action='store_true')
    args = parser.parse_args()

    print("\n" + "█" * 72)
    print(f"█  Stage 4A Phase 1 — wrapper v2.0_verified")
    print(f"█  사용자 결정: Y / b / 트리+우선순위 / a")
    print(f"█  실행: {datetime.now()}")
    print("█" * 72)

    if args.post_only:
        passed = post_run_validation()
        if passed:
            compress_outputs()
        sys.exit(0 if passed else 1)

    passed = preflight_check()
    if not passed:
        print("\n❌ 사전 점검 실패. 위 항목 해결 후 다시 실행.")
        sys.exit(1)

    if args.check_only:
        print("\n[check-only] 점검 통과 — 본 작업 안 함")
        sys.exit(0)

    if not args.skip_confirm:
        print("\n\n[최종 확인]")
        print(f"  작업 2~4시간 소요")
        print(f"  결과: {OUTPUT_DIR}")
        print(f"  진행: y, 취소: n: ", end='', flush=True)
        try:
            ans = input().strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\n취소")
            sys.exit(0)
        if ans != 'y':
            print("\n취소")
            sys.exit(0)

    # 본 작업
    print("\n\n" + "█" * 72)
    print(f"█  본 작업 시작 {datetime.now()}")
    print("█" * 72)
    t_start = time.time()
    try:
        import measure_v34_stage_4a
        result = measure_v34_stage_4a.main()
        elapsed = time.time() - t_start
        print(f"\n본 작업 소요: {elapsed/60:.1f}분 = {elapsed/3600:.2f}h")
        if not result:
            print("\n❌ 본 작업 실패")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ 예외: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 검증 + zip
    valid = post_run_validation()
    zip_path = compress_outputs()

    print("\n" + "█" * 72)
    if valid and zip_path:
        print(f"█  ✓ Stage 4A Phase 1 완료 {datetime.now()}")
        print(f"█  업로드 파일: {zip_path}")
        print(f"█  → 새 채팅창에 업로드")
        print(f"█  로그: outputs_stage_4a\\measure_log_4a.txt")
        print(f"█  트리 평가: outputs_stage_4a\\decision_tree_evaluation.csv")
    else:
        print(f"█  ⚠️ 부분 완료 {datetime.now()}")
        if zip_path:
            print(f"█  부분 결과: {zip_path}")
    print("█" * 72)
    sys.exit(0 if valid else 2)


if __name__ == "__main__":
    main()
