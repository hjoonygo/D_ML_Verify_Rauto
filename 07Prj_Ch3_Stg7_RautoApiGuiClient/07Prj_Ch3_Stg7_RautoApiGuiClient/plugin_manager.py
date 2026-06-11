# [파일명] plugin_manager.py
# 코드길이: 약 90줄 / 내부버전: plugin_manager_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 최대 8개 슬롯에 자기완결 봇 플러그인을 '리부트 없이' 로드/언로드한다(importlib).
#        엔진을 끄지 않고 봇을 갈아끼우는 것이 핵심 요구사항(요구사항 5).
# [Lookahead] 해당 없음(로딩/언로딩 관리만).
# ── 사용 파일 ── rauto_contract.py (BotPlugin)
# ── 함수 In/Out ──
#  _find_plugin_cls(mod)  In: 모듈 → Out: BotPlugin 하위클래스|None (모듈 내 자동탐지)
#  PluginManager(n_slots)        In: 슬롯수(기본8) → Out: 매니저
#   .load(slot,module_name,class_name=None,ctx=None) In: 슬롯·모듈명 → Out: 봇인스턴스(로드+on_init)
#   .unload(slot)        In: 슬롯 → Out: 제거(리부트 없이 슬롯 비움)·True/False
#   .reload(slot,...)    In: 슬롯·모듈명 → Out: 언로드 후 재로드(importlib.reload)
#   .get(slot)           In: 슬롯 → Out: 봇|None
#   .loaded_slots()      In: -    → Out: 로드된 슬롯 인덱스 리스트
#   .meta_of(slot)       In: 슬롯 → Out: META dict|None
# ── 상수 ── 없음
# ─────────────────────────────────────────────────────────────────────────
import importlib
import inspect
from typing import Optional, Dict, Any, List
from rauto_contract import BotPlugin


def _find_plugin_cls(mod):
    """모듈 안에서 BotPlugin 하위클래스를 자동 탐지(베이스 자신은 제외)."""
    for _, obj in inspect.getmembers(mod, inspect.isclass):
        if issubclass(obj, BotPlugin) and obj is not BotPlugin:
            return obj
    return None


class PluginManager:
    def __init__(self, n_slots: int = 8):
        self.n_slots = n_slots
        self.slots: List[Optional[BotPlugin]] = [None] * n_slots
        self._meta: List[Optional[Dict[str, Any]]] = [None] * n_slots
        self._modnames: List[Optional[str]] = [None] * n_slots

    def _check_slot(self, slot: int):
        if not (0 <= slot < self.n_slots):
            raise IndexError(f"슬롯 범위 초과: {slot} (0~{self.n_slots - 1})")

    def load(self, slot: int, module_name: str, class_name: Optional[str] = None,
             ctx: Optional[Dict[str, Any]] = None) -> BotPlugin:
        self._check_slot(slot)
        mod = importlib.import_module(module_name)
        mod = importlib.reload(mod)                      # 최신 소스 반영
        cls = getattr(mod, class_name) if class_name else _find_plugin_cls(mod)
        if cls is None:
            raise ValueError(f"{module_name}에서 BotPlugin 하위클래스를 못 찾음")
        bot = cls()
        bot.on_init(ctx or {})
        self.slots[slot] = bot
        self._meta[slot] = dict(getattr(bot, "META", {}))
        self._modnames[slot] = module_name
        return bot

    def unload(self, slot: int) -> bool:
        self._check_slot(slot)
        if self.slots[slot] is None:
            return False
        self.slots[slot] = None                          # 리부트 없이 슬롯 비움
        self._meta[slot] = None
        self._modnames[slot] = None
        return True

    def reload(self, slot: int, module_name: Optional[str] = None,
               class_name: Optional[str] = None, ctx: Optional[Dict[str, Any]] = None) -> BotPlugin:
        self._check_slot(slot)
        mn = module_name or self._modnames[slot]
        if mn is None:
            raise ValueError(f"슬롯 {slot}: 재로드할 모듈명 없음")
        self.unload(slot)
        return self.load(slot, mn, class_name, ctx)

    def get(self, slot: int) -> Optional[BotPlugin]:
        self._check_slot(slot)
        return self.slots[slot]

    def loaded_slots(self) -> List[int]:
        return [i for i, b in enumerate(self.slots) if b is not None]

    def meta_of(self, slot: int) -> Optional[Dict[str, Any]]:
        self._check_slot(slot)
        return self._meta[slot]
