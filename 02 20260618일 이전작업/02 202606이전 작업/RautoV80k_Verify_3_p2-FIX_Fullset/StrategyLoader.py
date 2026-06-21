# ==============================================================================
# [파일명] StrategyLoader.py
# 코드길이: 약 280줄, 내부버전: V80k_Verify_2
# 작성일: 2026-05-01
# ==============================================================================
# [정체성]
#   strategies/<name>.zip → 임시 디렉토리 추출 → R/P/E 모듈 import.
#   ChampionGUI / BotManager가 호출.
#
# [📥 IN]
#   strategy_name: 'Observer_R001' 등 (ZIP 파일명에서 .zip 제외)
# [📤 OUT]
#   StrategyBundle 객체 (R/P/E 모듈 + 메타데이터)
#
# [추출 위치]
#   <BASE_DIR>/strategies_extracted/<strategy_name>/
#   재가동 시 기존 추출 디렉토리 재사용 (ZIP mtime 비교) — 추출 비용 0
#
# [사용]
#   loader = StrategyLoader()
#   bundle = loader.load('3balancedTBM_R001')
#   regime_module = bundle.R
#   bundle.R.determine_regime_kinematics(df, params)
# ==============================================================================

import os
import sys
import json
import zipfile
import shutil
import importlib
import importlib.util
import threading
import logging
from typing import Optional, Dict, Tuple, Any
from dataclasses import dataclass, field


@dataclass
class StrategyBundle:
    """전략 패키지 — 메타데이터 + R/P/E 모듈."""
    name: str
    version: str
    metadata: dict = field(default_factory=dict)
    R: Any = None  # regime module
    P: Any = None  # predict module
    E: Any = None  # exec module
    extracted_path: str = ''
    is_observer: bool = False
    
    @property
    def trades(self) -> bool:
        return self.metadata.get('trades', not self.is_observer)
    
    def get_modules(self) -> Tuple[Any, Any, Any]:
        return self.R, self.P, self.E
    
    def __repr__(self):
        marker = '★ Observer' if self.is_observer else '거래 가능'
        return f'<StrategyBundle {self.name} v{self.version} {marker}>'


class StrategyLoader:
    """전략 ZIP 로더 — 캐시 + 추출 + import."""
    
    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            base_dir = os.environ.get('PAUTO_BASE_DIR') or os.path.dirname(os.path.abspath(__file__))
        self.base_dir = base_dir
        self.strategies_dir = os.path.join(base_dir, 'strategies')
        self.extracted_dir = os.path.join(base_dir, 'strategies_extracted')
        self._cache: Dict[str, StrategyBundle] = {}
        self._lock = threading.RLock()
        os.makedirs(self.extracted_dir, exist_ok=True)
    
    def list_strategies(self) -> list:
        """strategies/*.zip 자동 스캔 → 메타데이터 반환."""
        if not os.path.isdir(self.strategies_dir):
            return []
        
        result = []
        for f in sorted(os.listdir(self.strategies_dir)):
            if not f.endswith('.zip'):
                continue
            name = f[:-4]
            zip_path = os.path.join(self.strategies_dir, f)
            
            # metadata.json만 빠르게 읽음 (전체 추출 X)
            try:
                with zipfile.ZipFile(zip_path) as zf:
                    if 'metadata.json' not in zf.namelist():
                        continue
                    with zf.open('metadata.json') as mf:
                        meta = json.loads(mf.read().decode('utf-8'))
                
                result.append({
                    'name': name,
                    'zip_path': zip_path,
                    'metadata': meta,
                    'is_observer': meta.get('is_observer', False),
                    'description': meta.get('description', ''),
                    'size_mb': os.path.getsize(zip_path) / 1024 / 1024,
                })
            except Exception as e:
                logging.warning(f"[StrategyLoader] {f} 메타데이터 읽기 실패: {e}")
        
        return result
    
    def _is_extraction_fresh(self, strategy_name: str) -> bool:
        """추출된 디렉토리가 ZIP보다 최신인지."""
        zip_path = os.path.join(self.strategies_dir, f'{strategy_name}.zip')
        ext_path = os.path.join(self.extracted_dir, strategy_name)
        if not os.path.exists(zip_path) or not os.path.exists(ext_path):
            return False
        zip_mtime = os.path.getmtime(zip_path)
        # 디렉토리 안 metadata.json mtime 비교
        meta_path = os.path.join(ext_path, 'metadata.json')
        if not os.path.exists(meta_path):
            return False
        ext_mtime = os.path.getmtime(meta_path)
        return ext_mtime >= zip_mtime
    
    def _extract(self, strategy_name: str) -> str:
        """ZIP을 strategies_extracted/<name>/로 추출. 기존 폴더는 삭제."""
        zip_path = os.path.join(self.strategies_dir, f'{strategy_name}.zip')
        if not os.path.exists(zip_path):
            raise FileNotFoundError(f"전략 ZIP 없음: {zip_path}")
        
        ext_path = os.path.join(self.extracted_dir, strategy_name)
        
        if self._is_extraction_fresh(strategy_name):
            return ext_path
        
        # 기존 추출 폴더 삭제 후 재추출
        if os.path.exists(ext_path):
            try:
                shutil.rmtree(ext_path)
            except Exception as e:
                logging.warning(f"[StrategyLoader] 기존 추출 폴더 삭제 실패: {e}")
        
        os.makedirs(ext_path, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(ext_path)
        
        logging.info(f"[StrategyLoader] {strategy_name} 추출 완료: {ext_path}")
        return ext_path
    
    def load(self, strategy_name: str, force_reload: bool = False) -> StrategyBundle:
        """전략 로드 — 캐시 우선, 없으면 추출 + import."""
        with self._lock:
            if not force_reload and strategy_name in self._cache:
                return self._cache[strategy_name]
            
            # 추출
            ext_path = self._extract(strategy_name)
            
            # 메타데이터
            meta_path = os.path.join(ext_path, 'metadata.json')
            with open(meta_path) as f:
                meta = json.load(f)
            
            # sys.path에 추출 디렉토리의 부모 추가 → 패키지 import 가능
            parent_dir = os.path.dirname(ext_path)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            # 패키지 import (캐시된 모듈 무효화)
            module_keys_to_clear = [k for k in sys.modules.keys()
                                    if k.startswith(strategy_name)]
            for k in module_keys_to_clear:
                del sys.modules[k]
            
            try:
                pkg = importlib.import_module(strategy_name)
                R, P, E = pkg.get_modules()
            except Exception as e:
                logging.error(f"[StrategyLoader] {strategy_name} import 실패: {e}")
                raise
            
            bundle = StrategyBundle(
                name=meta.get('name', strategy_name),
                version=meta.get('version', '?'),
                metadata=meta,
                R=R, P=P, E=E,
                extracted_path=ext_path,
                is_observer=meta.get('is_observer', False),
            )
            
            self._cache[strategy_name] = bundle
            logging.info(f"[StrategyLoader] {bundle} 로드 완료")
            return bundle
    
    def reset_cache(self):
        """모든 전략 캐시 무효화 (테스트용)."""
        with self._lock:
            self._cache.clear()


# ==============================================================================
# 모듈 단위 편의 함수 (글로벌 단일 인스턴스)
# ==============================================================================
_GLOBAL_LOADER: Optional[StrategyLoader] = None


def get_loader() -> StrategyLoader:
    global _GLOBAL_LOADER
    if _GLOBAL_LOADER is None:
        _GLOBAL_LOADER = StrategyLoader()
    return _GLOBAL_LOADER


def list_strategies() -> list:
    return get_loader().list_strategies()


def load_strategy(strategy_name: str) -> StrategyBundle:
    return get_loader().load(strategy_name)


# ==============================================================================
# Selftest
# ==============================================================================
def _selftest():
    print("=" * 60)
    print("StrategyLoader Selftest")
    print("=" * 60)
    
    loader = StrategyLoader()
    
    # 1. list
    strategies = loader.list_strategies()
    print(f"\n[1] 발견된 전략: {len(strategies)}개")
    for s in strategies:
        marker = '★ Observer' if s['is_observer'] else '거래 가능'
        print(f"  - {s['name']} ({s['size_mb']:.1f}MB) {marker}")
        print(f"    설명: {s['description']}")
    
    # 2. load 각 전략
    for s in strategies:
        print(f"\n[2] '{s['name']}' 로드 시도...")
        try:
            bundle = loader.load(s['name'])
            print(f"  ✓ {bundle}")
            print(f"    R 모듈: {bundle.R.__name__}")
            print(f"    P 모듈: {bundle.P.__name__}")
            print(f"    E 모듈: {bundle.E.__name__}")
            
            # R/P/E 함수 존재 검증
            assert hasattr(bundle.R, 'determine_regime_kinematics'), 'R has no determine_regime_kinematics'
            assert hasattr(bundle.P, 'get_signal'), 'P has no get_signal'
            assert hasattr(bundle.E, 'evaluate_exit'), 'E has no evaluate_exit'
            print(f"    ✓ R/P/E 인터페이스 검증 통과")
        except Exception as e:
            print(f"  ✗ 실패: {e}")
            import traceback
            traceback.print_exc()
    
    print("\nSelftest 완료")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    _selftest()
