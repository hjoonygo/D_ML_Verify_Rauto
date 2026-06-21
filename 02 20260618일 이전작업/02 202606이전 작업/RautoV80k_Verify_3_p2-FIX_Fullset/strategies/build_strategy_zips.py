#!/usr/bin/env python3
# ==============================================================================
# [파일명] strategies/build_strategy_zips.py
# 코드길이: 약 80줄, 내부버전: V80k_Verify_2
# 작성일: 2026-05-01
# ==============================================================================
# [정체성]
#   strategies/_workspace/<strategy_name>/ 폴더를 strategies/<strategy_name>.zip 으로 패키징.
#   메타데이터 검증 + ZIP 생성.
#
# [사용]
#   python strategies/build_strategy_zips.py             # 전체 빌드
#   python strategies/build_strategy_zips.py 3balancedTBM_R001  # 특정 전략만
# ==============================================================================
import os
import sys
import json
import zipfile
import shutil

WORKSPACE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_workspace')
OUT_DIR = os.path.dirname(os.path.abspath(__file__))


def validate_metadata(strategy_dir):
    """metadata.json 존재 + 필수 필드 검증."""
    meta_path = os.path.join(strategy_dir, 'metadata.json')
    if not os.path.exists(meta_path):
        return False, "metadata.json 없음"
    try:
        with open(meta_path) as f:
            meta = json.load(f)
    except Exception as e:
        return False, f"metadata.json 파싱 실패: {e}"
    
    required = ['name', 'version', 'modules', 'is_observer']
    for k in required:
        if k not in meta:
            return False, f"필수 필드 누락: {k}"
    
    # __init__.py + R/P/E 모듈 존재
    for f in ['__init__.py', 'R_module.py', 'P_module.py', 'E_module.py']:
        if not os.path.exists(os.path.join(strategy_dir, f)):
            return False, f"파일 누락: {f}"
    
    return True, meta


def build_zip(strategy_name):
    src = os.path.join(WORKSPACE_DIR, strategy_name)
    if not os.path.isdir(src):
        print(f"  [SKIP] {strategy_name}: 디렉토리 없음")
        return False
    
    ok, result = validate_metadata(src)
    if not ok:
        print(f"  [FAIL] {strategy_name}: {result}")
        return False
    
    meta = result
    
    # ZIP 작성
    out = os.path.join(OUT_DIR, f"{strategy_name}.zip")
    if os.path.exists(out):
        os.remove(out)
    
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files in os.walk(src):
            # __pycache__ 제외
            dirs[:] = [d for d in dirs if d != '__pycache__']
            for f in files:
                if f.endswith('.pyc'):
                    continue
                full_path = os.path.join(root, f)
                arc_path = os.path.relpath(full_path, src)
                zf.write(full_path, arcname=arc_path)
    
    size_mb = os.path.getsize(out) / 1024 / 1024
    is_obs = '★ Observer' if meta.get('is_observer') else '거래 가능'
    print(f"  [OK] {strategy_name}.zip ({size_mb:.1f}MB) — {is_obs}")
    return True


def main():
    if not os.path.exists(WORKSPACE_DIR):
        print(f"[ERROR] _workspace 디렉토리 없음: {WORKSPACE_DIR}")
        sys.exit(1)
    
    targets = sys.argv[1:] if len(sys.argv) > 1 else None
    
    if targets is None:
        targets = [d for d in os.listdir(WORKSPACE_DIR)
                  if os.path.isdir(os.path.join(WORKSPACE_DIR, d))
                  and not d.startswith('_') and not d.startswith('.')]
    
    print(f"[빌드 시작] 대상: {targets}")
    success = 0
    for t in targets:
        if build_zip(t):
            success += 1
    print(f"\n[완료] {success}/{len(targets)} 전략 빌드 성공")


if __name__ == '__main__':
    main()
