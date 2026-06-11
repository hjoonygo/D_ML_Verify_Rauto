# [파일명] test_07Prj_Ch3_Stg6_RautoSlotChampGuard.py
# 코드길이: 약 150줄 / 내부버전: stg6_test_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] ㉠ 통합 시연: plugin_manager(리부트 없는 로드/언로드/재로드) + champion(레짐별 스코어/
#        히스테리시스 선택, 1봇=자동챔피언) + safety(킬·-20%·연속손실 게이트) + paper_account.
#        검증 원장 264거래를 오케스트레이터로 리플레이 → 챔피언/안전이 끼어도 +827% 그대로인지 확인.
# [Lookahead] 레짐=진입봉 마감 이하 asof feat. 거래 entry_t 순서 순차복리.
# ── 사용 파일 (상위 D:\ML\verify 자동탐지) ──
#  IN  stg6_levsweep_ledger.csv / *OPVnN*devledger*.csv / *featcache.csv
#  rauto_contract.py / rauto_paper_engine.py / bot_trendstack_replay.py
#  plugin_manager.py / champion.py / safety.py / rauto_orchestrator.py
#  OUT(cwd) <BASE>_summary.csv  결과 + 챔피언/안전/스코어 요약
# ── 함수 In/Out ──
#  _naive(s) / find_in_tree(cands) / load()  : 거래DF[+dev/regime_dir/feat] 구성 (Stg5와 동일)
# ── 상수 ── SEARCH / BASE
# ─────────────────────────────────────────────────────────────────────────
import os, sys, glob
import numpy as np
import pandas as pd
from rauto_paper_engine import PaperAccount
from plugin_manager import PluginManager
from champion import Scorer, ChampionSelector
from safety import SafetyGuard
from rauto_orchestrator import RautoOrchestrator

BASE = os.path.basename(__file__).replace('test_', '').replace('.py', '')
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


def load():
    lp = find_in_tree(['stg6_levsweep_ledger.csv', '*levsweep_ledger.csv'])
    if not lp:
        print('!! 원장 없음'); sys.exit(1)
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
    return led, os.path.basename(lp)


if __name__ == '__main__':
    df, lsrc = load()
    print(f"[데이터] {len(df)}건 / 원장={lsrc}")

    # 1) 슬롯 로드/언로드/재로드 시연 (리부트 없이)
    mgr = PluginManager(n_slots=8)
    mgr.load(0, "bot_trendstack_replay")
    print(f"[매니저] load(0) → 로드슬롯={mgr.loaded_slots()} META={mgr.meta_of(0)['name']}/{mgr.meta_of(0)['version']}")
    mgr.unload(0)
    print(f"[매니저] unload(0) → 로드슬롯={mgr.loaded_slots()} (엔진 재시작 없음)")
    mgr.reload(0, "bot_trendstack_replay")
    print(f"[매니저] reload(0) → 로드슬롯={mgr.loaded_slots()} (슬롯수 용량={mgr.n_slots})")

    # 2) 챔피언+안전 통합 리플레이 (충실 재현: 연속손실 차단 OFF, -20%/킬은 게이트)
    acct = PaperAccount()
    scorer = Scorer()
    selector = ChampionSelector(margin=0.15, min_n=5)
    guard = SafetyGuard(mdd_limit=-20.0, max_consec=0)
    orch = RautoOrchestrator(mgr, acct, scorer, selector, guard)
    res = orch.run_replay(df)
    ret, mdd, cal = acct.metrics()

    print(f"\n[리플레이 결과] 수익률 {ret:.2f}% / MDD {mdd:.2f}% / Calmar {cal:.2f} / 하드스탑 {acct.n_liq}")
    print(f"[챔피언] 진입 {res['n_entered']}건 / 차단 {res['n_halted']}건 / 챔피언슬롯={res['unique_champions']}")
    print(f"[안전] 상태={guard.status()}")
    print(f"[레짐별 스코어(챔피언)]")
    for (slot, reg), v in sorted(res['scorer_table'].items()):
        print(f"   슬롯{slot} {reg:10s}: n={v['n']:3d} ret={v['ret']:8.2f}% mdd={v['mdd']:6.2f}% cal={v['cal']}")

    summ = pd.DataFrame([{
        'BASE': BASE, 'n_trades': len(df), 'ret_pct': round(ret, 2), 'mdd_pct': round(mdd, 2),
        'calmar': round(cal, 2), 'hardstop_n': acct.n_liq, 'n_entered': res['n_entered'],
        'n_halted': res['n_halted'], 'champions': str(res['unique_champions']),
        'safety_halted': guard.status()['halted'], 'slots': mgr.n_slots,
    }])
    summ.to_csv(f'{BASE}_summary.csv', index=False, encoding='utf-8-sig')
    print(f"\n[저장] {BASE}_summary.csv")
