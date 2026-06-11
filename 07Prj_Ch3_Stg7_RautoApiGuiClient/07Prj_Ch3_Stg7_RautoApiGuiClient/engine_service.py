# [파일명] engine_service.py
# 코드길이: 약 150줄 / 내부버전: engine_service_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] '헤드리스 엔진'의 공개 facade(단일 진실원천). 24h AWS에서 도는 엔진 본체로,
#        plugin_manager + orchestrator + paper_account + champion(scorer/selector) + safety 를 묶고
#        외부(API 서버)가 호출할 메서드를 노출한다. GUI는 이 엔진을 '직접 생성하지 않고' API로 붙는다.
# [Lookahead] 리플레이는 entry_t 순서 순차복리·asof feat(검증과 동일). 미래참조 없음.
# ── 사용 파일 ──
#  IN(데이터, 상위 D:\ML\verify 자동탐지) stg6_levsweep_ledger.csv / *OPVnN*devledger*.csv / *featcache.csv
#  rauto_contract / rauto_paper_engine / plugin_manager / champion / safety / rauto_orchestrator
# ── 함수 In/Out ──
#  _naive/find_in_tree/load_replay_df()  거래DF[+dev/regime_dir/feat] 구성
#  EngineService(n_slots)         In: 슬롯수 → Out: 엔진
#   .load_data()        In: -            → Out: 거래수(데이터 적재)
#   .load_bot(slot,module,class_name)    In: 슬롯·모듈 → Out: META(로드)
#   .unload_bot(slot)   In: 슬롯 → Out: bool
#   .list_slots()       In: -    → Out: [{slot,meta}]
#   .run_replay()       In: -    → Out: status(런타임 리셋 후 리플레이 실행)
#   .get_account()/get_champion()/get_scores()/get_status()  In: - → Out: 상태 dict
#   .trip_kill()/reset_safety()  In: - → Out: status
# ── 상수 ── SEARCH 경로목록
# ─────────────────────────────────────────────────────────────────────────
import os, sys, glob, threading
import numpy as np
import pandas as pd
from rauto_paper_engine import PaperAccount
from plugin_manager import PluginManager
from champion import Scorer, ChampionSelector
from safety import SafetyGuard
from rauto_orchestrator import RautoOrchestrator

SEARCH = ['.', '..', '../..', '/mnt/user-data/uploads',
          '/home/claude/dryrun2/verify',
          '/home/claude/ho/Handover_07Prj_Ch2_TrendStack_stg6/results']


def _naive(s):
    t = pd.to_datetime(s, errors='coerce')
    try:
        t = t.dt.tz_localize(None)
    except (TypeError, AttributeError):
        try:
            t = t.dt.tz_convert(None)
        except Exception:
            pass
    return t


def find_in_tree(cands):
    for d in SEARCH:
        for c in cands:
            p = os.path.join(d, c)
            if os.path.exists(p):
                return p
            h = glob.glob(os.path.join(d, c))
            if h:
                return sorted(h)[0]
    return None


def load_replay_df():
    lp = find_in_tree(['stg6_levsweep_ledger.csv', '*levsweep_ledger.csv'])
    if not lp:
        raise FileNotFoundError('원장(stg6_levsweep_ledger.csv) 없음')
    led = pd.read_csv(lp)
    led['entry_t'] = _naive(led['entry_t'])
    led = led.sort_values('entry_t').reset_index(drop=True)
    dp = find_in_tree(['*OPVnN*devledger*.csv', '*devledger*.csv'])
    if dp:
        dv = pd.read_csv(dp)
        dv['entry_t'] = _naive(dv['entry_t'])
        led = led.merge(dv[['entry_t', 'dev', 'regime_dir']], on='entry_t', how='left')
    else:
        led['dev'] = np.nan; led['regime_dir'] = np.nan
    fc = find_in_tree(['*featcache*.csv'])
    if fc:
        c = pd.read_csv(fc); c['entry_t'] = _naive(c['entry_t'])
        mp = dict(zip(c['entry_t'], c['feat']))
        led['feat'] = [mp.get(pd.Timestamp(t)) for t in led['entry_t']]
    else:
        led['feat'] = None
    return led


class EngineService:
    def __init__(self, n_slots: int = 8):
        self.n_slots = n_slots
        self.manager = PluginManager(n_slots)
        self._df = None
        self._lock = threading.RLock()
        self._reset_runtime()

    def _reset_runtime(self):
        self.account = PaperAccount()
        self.scorer = Scorer()
        self.selector = ChampionSelector(margin=0.15, min_n=5)
        self.guard = SafetyGuard(mdd_limit=-20.0, max_consec=0)
        self.orch = RautoOrchestrator(self.manager, self.account, self.scorer, self.selector, self.guard)
        self._last = None

    def load_data(self):
        self._df = load_replay_df()
        return len(self._df)

    def load_bot(self, slot, module, class_name=None):
        with self._lock:
            self.manager.load(int(slot), module, class_name)
            return self.manager.meta_of(int(slot))

    def unload_bot(self, slot):
        with self._lock:
            return self.manager.unload(int(slot))

    def list_slots(self):
        return [{"slot": i, "meta": self.manager.meta_of(i)} for i in range(self.n_slots)]

    def run_replay(self):
        with self._lock:
            if self._df is None:
                self.load_data()
            self._reset_runtime()
            self._last = self.orch.run_replay(self._df)
            return self.get_status()

    def get_account(self):
        ret, mdd, cal = self.account.metrics()
        return {"balance": round(self.account.bal, 2), "ret_pct": round(ret, 2),
                "mdd_pct": round(mdd, 2), "calmar": round(cal, 2) if cal == cal else None,
                "trades": len(self.account.trades), "hardstop": self.account.n_liq}

    def get_champion(self):
        if not self._last:
            return {"unique_champions": [], "n_entered": 0, "n_halted": 0}
        return {"unique_champions": self._last["unique_champions"],
                "n_entered": self._last["n_entered"], "n_halted": self._last["n_halted"]}

    def get_scores(self):
        return {f"{s}|{r}": v for (s, r), v in self.scorer.table().items()}

    def trip_kill(self):
        with self._lock:
            self.guard.trip_kill()
            return self.get_status()

    def reset_safety(self):
        with self._lock:
            self.guard.reset()
            return self.get_status()

    def get_status(self):
        return {"slots_loaded": self.manager.loaded_slots(), "n_slots": self.n_slots,
                "safety": self.guard.status(), "account": self.get_account(),
                "champion": self.get_champion()}
