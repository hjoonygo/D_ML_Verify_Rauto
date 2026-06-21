# ==============================================================================
# [파일명] pc_pipeline_V80k_Verify_3.py
# [코드길이] 약 320줄 / 내부버전 V80k_Verify_3_S4 / 로직축약·생략 없이 전체 출력
# [모듈 종류] 통합 파이프라인 (선장 PC 단독 실행 / 클로드 토큰 0)
# ==============================================================================
# [목적]
#   한 명령으로 다음 9단계 자동 실행 — 선장 개입 최소화:
#     1) 환경 검증
#     2) CSV 로드 + 70/30 분할
#     3) 30 피처 산출
#     4) Regime 70% 학습 (또는 기존 사용)
#     5) TBM v3 환경별 학습 (BULL/BEAR/CHOP)
#     6) Takeaway 3.3.2 학습 메트릭 회귀 테스트
#     7) OOS 추론 + Takeaway 3.3.3 conf 분포 회귀 테스트
#     8) train_report.json 자동 생성 (~30KB, 클로드 채팅 업로드용)
#     9) Strategy ZIP 빌드 (3balancedTBM_R002.zip)
#
# [📥 IN]
#   --data <csv>      : 21mo CSV (필수)
#   --tag <str>       : 모델 시리즈 태그 (기본 R002)
#   --output-dir <p>  : 출력 폴더 (기본 ./pc_pipeline_output)
#   --skip-regime     : Regime 재학습 안 함 (기존 _train70.json 사용)
#   --tp-pct <float>  : TBM TP, 기본 0.30
#   --sl-pct <float>  : TBM SL, 기본 0.10
#   --horizon <int>   : 기본 30
#
# [📤 OUT]
#   <output-dir>/
#     ├── PautoV80_Regime_Model_v6_train70.json  (Regime 70% 학습)
#     ├── PautoV80_TBM_BULL_v3.json              (TBM v3)
#     ├── PautoV80_TBM_BEAR_v3.json
#     ├── PautoV80_TBM_CHOP_v3.json
#     ├── V80k_Verify_3_S4_train_report.json     ★ 클로드 업로드용 (작음)
#     ├── 3balancedTBM_R002.zip                  ★ 배포 ZIP
#     └── pipeline.log
#
# [클로드 토큰]
#   학습 중: 0 (PC 단독)
#   학습 후: train_report.json (~30KB)만 채팅 업로드 → 수만 토큰
#   풀세트 47MB JSON 일체 클로드에 업로드 안 함
#
# [예상 시간]
#   환경 검증 + 데이터 로드 + 피처: 5~10분
#   Regime 학습 (skip 가능): 15~30분
#   TBM v3 환경별 학습: 5분 × 3 = 15분
#   회귀 테스트: 1분
#   ZIP 빌드: 30초
#   합계: 약 30~60분 (Regime skip 시)
# ==============================================================================
import os
import sys
import json
import argparse
import time
import zipfile
import shutil
import logging
from datetime import datetime


def setup_logger(output_dir):
    log_path = os.path.join(output_dir, 'pipeline.log')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger('pc_pipeline')


def step_1_env_check(log):
    """환경 검증 — Python/xgboost/pandas 버전 + RAM."""
    log.info("=" * 78)
    log.info("[Step 1] 환경 검증")
    log.info("=" * 78)
    
    import sys as _sys
    log.info(f"  Python: {_sys.version.split()[0]}")
    
    try:
        import xgboost as xgb
        log.info(f"  xgboost: {xgb.__version__}")
        xgb_major = int(xgb.__version__.split('.')[0])
        if xgb_major < 3:
            log.error(f"  ✗ xgboost < 3.0 — V80k_Verify_3 모델 호환 안 됨 (predict_proba 형태 깨짐)")
            log.error(f"     → 해결: setup_env.bat 실행 또는 pip install \"xgboost==3.2.0\" --upgrade")
            return False
    except ImportError:
        log.error("  ✗ xgboost 미설치 — setup_env.bat 실행")
        return False
    
    try:
        import pandas as pd
        log.info(f"  pandas: {pd.__version__}")
    except ImportError:
        log.error("  ✗ pandas 미설치")
        return False
    
    try:
        import sklearn
        log.info(f"  scikit-learn: {sklearn.__version__}")
        sk_parts = sklearn.__version__.split('.')
        sk_major, sk_minor = int(sk_parts[0]), int(sk_parts[1])
        if sk_major > 1 or (sk_major == 1 and sk_minor >= 6):
            log.error(f"  ✗ scikit-learn >= 1.6 — xgboost save_model에서 _estimator_type 에러")
            log.error(f"     → 해결: setup_env.bat 실행 또는 pip install \"scikit-learn==1.4.2\" --upgrade")
            return False
    except ImportError:
        log.error("  ✗ scikit-learn 미설치")
        return False
    
    try:
        import psutil
        ram_gb = psutil.virtual_memory().total / (1024**3)
        log.info(f"  RAM: {ram_gb:.1f} GB")
        if ram_gb < 6:
            log.warning(f"  ⚠ RAM 부족 ({ram_gb:.1f} GB) — 8GB+ 권장. 학습 OOM 위험")
    except ImportError:
        log.info(f"  RAM: 확인 불가 (psutil 없음, optional)")
    
    log.info("  ✓ 환경 검증 통과")
    return True


def step_4_train_regime_if_needed(csv_path, output_dir, skip, log):
    """Regime 70% 학습 (D1 누설 차단판)."""
    log.info("\n" + "=" * 78)
    log.info("[Step 4] Regime 70% 학습 (D1 누설 차단판)")
    log.info("=" * 78)
    
    target = os.path.join(output_dir, 'PautoV80_Regime_Model_v6_train70.json')
    if os.path.exists(target) and skip:
        log.info(f"  ✓ 기존 모델 사용: {target}")
        return target
    
    # 사용자 PC에 이미 있는지 자동 탐색
    candidates = [
        os.path.join(os.path.dirname(csv_path), 'PautoV80_Regime_Model_v6_train70.json'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'PautoV80_Regime_Model_v6_train70.json'),
    ]
    for c in candidates:
        if os.path.exists(c):
            log.info(f"  ✓ 기존 70% 모델 발견: {c}")
            shutil.copy(c, target)
            return target
    
    log.info(f"  Regime 70% 모델 없음 → 신규 학습 시작 (15~30분 소요)")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from PautoV80_Regime_ML import PautoV80_Regime_ML, _load_csv_auto
    
    df = _load_csv_auto(csv_path)
    n = len(df)
    split_idx = int(n * 0.70)
    log.info(f"  21mo 70% = {split_idx:,}봉 사용")
    
    # 70% 부분만 임시 CSV로 저장
    tmp_csv = os.path.join(output_dir, 'tmp_train70.csv')
    df.iloc[:split_idx].reset_index().to_csv(tmp_csv, index=False)
    
    result = PautoV80_Regime_ML.train_model(tmp_csv, model_path=target, log_fn=log.info)
    os.remove(tmp_csv)
    log.info(f"  ✓ Regime 70% 학습 완료: train_acc {result['train_accuracy']*100:.2f}%")
    return target


def step_5_train_tbm(csv_path, output_dir, regime_path, tp_pct, sl_pct, horizon, log):
    """TBM v3 환경별 학습."""
    log.info("\n" + "=" * 78)
    log.info("[Step 5+6] TBM v3 환경별 학습 + 학습 메트릭 회귀 테스트")
    log.info("=" * 78)
    
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from PautoV80_Regime_ML import train_tbm_v2
    
    result = train_tbm_v2(
        csv_path=csv_path,
        output_dir=output_dir,
        regime_model_path=regime_path,
        horizon=horizon,
        tp_pct=tp_pct,
        sl_pct=sl_pct,
        log_fn=log.info,
    )
    return result


def step_7_oos_regression(csv_path, output_dir, regime_path, log):
    """OOS 추론 + Takeaway 3.3.3 conf 분포 회귀."""
    log.info("\n" + "=" * 78)
    log.info("[Step 7] OOS 추론 + 골든 conf 분포 회귀 테스트")
    log.info("=" * 78)
    
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from oos_regression_V80k_Verify_3 import regression_test_oos
    
    result = regression_test_oos(
        csv_path=csv_path,
        models_dir=output_dir,
        regime_model_path=regime_path,
        log_fn=log.info,
    )
    return result


def step_8_train_report(output_dir, train_result, oos_result, args, log):
    """train_report.json — 클로드 업로드용 작은 파일."""
    log.info("\n" + "=" * 78)
    log.info("[Step 8] train_report.json 자동 생성")
    log.info("=" * 78)
    
    report = {
        'pipeline_version': 'V80k_Verify_3_S4',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'args': {
            'tp_pct': args.tp_pct,
            'sl_pct': args.sl_pct,
            'horizon': args.horizon,
            'tag': args.tag,
        },
        'train_result': {
            'metrics': train_result.get('metrics', {}),
            'regression_test': train_result.get('regression_test', {}),
            'split_idx': train_result.get('split_idx'),
            'split_date': train_result.get('split_date'),
        },
        'oos_result': oos_result,
        'overall_pass': (
            train_result.get('regression_test', {}).get('overall_pass', False) and
            oos_result.get('overall_pass', False)
        ),
        'next_action_recommendation': '',
    }
    
    if report['overall_pass']:
        report['next_action_recommendation'] = (
            "★ PASS — 학습 + OOS 분포 모두 골든 일치. "
            "단계 9 ZIP 빌드 진행 → AWS 배포 가능."
        )
    else:
        fails = []
        if not train_result.get('regression_test', {}).get('overall_pass', False):
            fails.append("학습 메트릭 회귀 미달")
        if not oos_result.get('overall_pass', False):
            fails.append("OOS conf 분포 골든 미달")
        report['next_action_recommendation'] = (
            f"⚠ FAIL — {' + '.join(fails)}. "
            "원인: (1) 데이터 차이, (2) 시드 변동, (3) 라벨링 임계 재검토. "
            "train_report.json을 클로드 채팅에 업로드하여 진단 받으세요."
        )
    
    out_path = os.path.join(output_dir, 'V80k_Verify_3_S4_train_report.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log.info(f"  ✓ 저장: {out_path}")
    log.info(f"  ★ 이 파일을 클로드 채팅에 업로드하세요 (~30KB)")
    log.info(f"\n  종합 판정: {'★ PASS' if report['overall_pass'] else '⚠ FAIL'}")
    log.info(f"  권장: {report['next_action_recommendation']}")
    return report


def step_9_build_zip(output_dir, tag, source_dir, log):
    """Strategy ZIP 빌드 (3balancedTBM_R002.zip)."""
    log.info("\n" + "=" * 78)
    log.info(f"[Step 9] Strategy ZIP 빌드 ({tag})")
    log.info("=" * 78)
    
    # workspace 임시 폴더
    ws = os.path.join(output_dir, f'_ws_{tag}')
    os.makedirs(os.path.join(ws, 'models'), exist_ok=True)
    
    # 모델 4개 복사 (Regime + TBM 3개)
    files_to_copy = [
        'PautoV80_Regime_Model_v6_train70.json',
        'PautoV80_TBM_BULL_v3.json',
        'PautoV80_TBM_BEAR_v3.json',
        'PautoV80_TBM_CHOP_v3.json',
    ]
    for f in files_to_copy:
        src = os.path.join(output_dir, f)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(ws, 'models', f))
    
    # R/P/E 모듈은 R001 워크스페이스에서 복사
    r001_ws = os.path.join(source_dir, 'strategies', '_workspace', '3balancedTBM_R001')
    for f in ['R_module.py', 'P_module.py', 'E_module.py', '__init__.py']:
        src = os.path.join(r001_ws, f)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(ws, f))
    
    # metadata.json 신규
    metadata = {
        "name": "3balancedTBM",
        "version": tag,
        "series": "V80k",
        "description": f"V80k_Verify_3 신규 학습 ({tag}) — TBM v3 (R:R 3:1, R001 코드 + v3 모델)",
        "internal_version": "V80k_Verify_3",
        "modules": {"R": "R_module", "P": "P_module", "E": "E_module"},
        "module_class_or_function": {
            "R": "determine_regime_kinematics",
            "P": "get_signal",
            "E": "evaluate_exit"
        },
        "required_models": [
            "PautoV80_Regime_Model_v6_train70.json",
            "PautoV80_TBM_BULL_v3.json",
            "PautoV80_TBM_BEAR_v3.json",
            "PautoV80_TBM_CHOP_v3.json",
        ],
        "models_dir": "models",
        "is_observer": False,
        "trades": True,
        "compatible_with": ["V80k", "V80k_Verify_3"],
        "created_at": datetime.utcnow().strftime("%Y-%m-%d"),
        "author": "V80k_Verify_3 PC pipeline",
    }
    with open(os.path.join(ws, 'metadata.json'), 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    # ZIP
    zip_path = os.path.join(output_dir, f'{tag}.zip')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(ws):
            for f in files:
                full = os.path.join(root, f)
                arc = os.path.relpath(full, ws)
                zf.write(full, arcname=arc)
    
    shutil.rmtree(ws)
    
    size_mb = os.path.getsize(zip_path) / (1024*1024)
    log.info(f"  ✓ ZIP 빌드: {zip_path} ({size_mb:.1f} MB)")
    return zip_path


def main():
    parser = argparse.ArgumentParser(description='V80k_Verify_3 PC 통합 파이프라인')
    parser.add_argument('--data', required=True, help='21mo 1m raw CSV')
    parser.add_argument('--tag', default='3balancedTBM_R002', help='ZIP 태그')
    parser.add_argument('--output-dir', default='./pc_pipeline_output')
    parser.add_argument('--skip-regime', action='store_true', help='Regime 재학습 skip')
    parser.add_argument('--tp-pct', type=float, default=0.30)
    parser.add_argument('--sl-pct', type=float, default=0.10)
    parser.add_argument('--horizon', type=int, default=30)
    parser.add_argument('--source-dir', default=None,
                       help='V80k_Verify_3 소스 폴더 (R/P/E 모듈 복사용)')
    args = parser.parse_args()
    
    if args.source_dir is None:
        args.source_dir = os.path.dirname(os.path.abspath(__file__))
    
    os.makedirs(args.output_dir, exist_ok=True)
    log = setup_logger(args.output_dir)
    
    t_start = time.time()
    log.info("V80k_Verify_3 PC 통합 파이프라인 시작")
    log.info(f"  data: {args.data}")
    log.info(f"  output: {args.output_dir}")
    log.info(f"  TBM: TP {args.tp_pct}% / SL {args.sl_pct}% / horizon {args.horizon}")
    
    try:
        # Step 1
        if not step_1_env_check(log):
            return 1
        
        # Step 2~3: train_tbm_v2 내부에서 처리
        # Step 4: Regime 70% 모델 확보
        regime_path = step_4_train_regime_if_needed(args.data, args.output_dir,
                                                     args.skip_regime, log)
        
        # Step 5+6: TBM 학습 + 학습 메트릭 회귀
        train_result = step_5_train_tbm(args.data, args.output_dir, regime_path,
                                         args.tp_pct, args.sl_pct, args.horizon, log)
        
        # Step 7: OOS 회귀
        oos_result = step_7_oos_regression(args.data, args.output_dir, regime_path, log)
        
        # Step 8: 리포트 생성
        report = step_8_train_report(args.output_dir, train_result, oos_result, args, log)
        
        # Step 9: ZIP 빌드 (회귀 테스트 통과한 경우만)
        if report['overall_pass']:
            zip_path = step_9_build_zip(args.output_dir, args.tag, args.source_dir, log)
            log.info(f"\n[FINAL] ZIP 빌드 완료: {zip_path}")
        else:
            log.warning(f"\n[FINAL] 회귀 테스트 미통과 — ZIP 빌드 skip. train_report.json 검토 필요.")
        
        log.info(f"\n[총 시간] {time.time()-t_start:.0f}s")
        return 0 if report['overall_pass'] else 1
    
    except Exception as e:
        log.error(f"파이프라인 에러: {e}", exc_info=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
