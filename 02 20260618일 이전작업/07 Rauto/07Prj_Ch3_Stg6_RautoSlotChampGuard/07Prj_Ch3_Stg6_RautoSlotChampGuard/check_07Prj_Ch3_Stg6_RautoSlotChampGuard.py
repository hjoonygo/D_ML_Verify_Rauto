# [파일명] check_07Prj_Ch3_Stg6_RautoSlotChampGuard.py
# 코드길이: 약 150줄 / 내부버전: stg6_check_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] ㉠(슬롯매니저+챔피언+안전)를 12개 시나리오로 검증한다.
#        핵심: 챔피언·안전을 끼운 오케스트레이터가 +827%/-16.1%/51.3 그대로 재현하는가
#        + 로드/언로드/재로드, 1봇 자동챔피언, 레짐스코어, 안전(-20%/킬/연속손실), 히스테리시스.
# [Lookahead] 레짐=asof feat. test_의 load() 재사용.
# ── 사용 파일 ──
#  IN  test_07Prj_Ch3_Stg6_RautoSlotChampGuard.py (load 재사용)
#  plugin_manager.py / champion.py / safety.py / rauto_orchestrator.py / rauto_paper_engine.py
#  OUT(../00WorkHstr) <YYYYMMDDHHMM>.txt + 00WorkHstr_INDEX.txt(append)
# ── 함수 In/Out ──
#  approx(a,b,t)  근사일치
#  main()         12 시나리오 PASS/FAIL + 리포트/INDEX 기록
# ── 상수 ── 기대값 / OUT_DIR
# ─────────────────────────────────────────────────────────────────────────
import os
from datetime import datetime
import test_07Prj_Ch3_Stg6_RautoSlotChampGuard as T
from rauto_paper_engine import PaperAccount
from plugin_manager import PluginManager
from champion import Scorer, ChampionSelector
from safety import SafetyGuard
from rauto_orchestrator import RautoOrchestrator

BASE = "07Prj_Ch3_Stg6_RautoSlotChampGuard"
OUT_DIR = os.path.join('..', '00WorkHstr')
EXP_RET = 827; EXP_MDD = -16.1; EXP_CAL = 51.3


def approx(a, b, t=1e-9):
    try:
        return abs(float(a) - float(b)) <= t
    except (TypeError, ValueError):
        return False


def main():
    df, lsrc = T.load()

    # --- 매니저 로드/언로드/재로드 ---
    mgr = PluginManager(n_slots=8)
    b = mgr.load(0, "bot_trendstack_replay")
    s1 = (mgr.meta_of(0)["name"] == "TrendStack" and mgr.loaded_slots() == [0])
    s2 = (mgr.n_slots == 8)
    unloaded = mgr.unload(0); empty = (mgr.loaded_slots() == [])
    mgr.reload(0, "bot_trendstack_replay"); reloaded = (mgr.loaded_slots() == [0])
    s3 = (unloaded and empty and reloaded)

    # --- 오케스트레이터 통합 리플레이 (충실 재현) ---
    acct = PaperAccount(); scorer = Scorer()
    selector = ChampionSelector(margin=0.15, min_n=5)
    guard = SafetyGuard(mdd_limit=-20.0, max_consec=0)
    orch = RautoOrchestrator(mgr, acct, scorer, selector, guard)
    res = orch.run_replay(df)
    ret, mdd, cal = acct.metrics()

    s4 = (res["unique_champions"] == [0])                       # 1봇 자동챔피언
    s5 = (round(ret) == EXP_RET and round(mdd, 1) == EXP_MDD and round(cal, 1) == EXP_CAL)
    s6 = (res["n_entered"] == 264 and res["n_halted"] == 0)
    total_n = sum(v["n"] for v in res["scorer_table"].values())
    s7 = (total_n == 264 and len(res["scorer_table"]) >= 2)     # 레짐별 스코어 누적
    s8 = (guard.status()["halted"] is False and guard.circuit is False)  # 무인 정상구간 오발동 없음

    # --- 안전 단위검증 ---
    g_mdd = SafetyGuard(mdd_limit=-20.0); g_mdd.on_equity(-20.1)
    s9 = (g_mdd.circuit is True and g_mdd.allow_entry() is False)
    g_kill = SafetyGuard(); g_kill.trip_kill(); killed = (g_kill.allow_entry() is False)
    g_kill.reset(); s10 = (killed and g_kill.allow_entry() is True)
    g_c = SafetyGuard(max_consec=4)
    for _ in range(4):
        g_c.on_trade(-0.01)
    halted4 = (g_c.consec_halt is True and g_c.allow_entry() is False)
    g_c.reset(); reset_ok = g_c.allow_entry() is True
    g_c2 = SafetyGuard(max_consec=4)
    for p in (-0.01, -0.01, -0.01, +0.02):
        g_c2.on_trade(p)
    no_halt3 = (g_c2.consec_halt is False and g_c2.consec_losses == 0)
    s11 = (halted4 and reset_ok and no_halt3)

    # --- 히스테리시스 단위검증 (마진 미달 유지 / 초과 교체) ---
    sc = Scorer()
    # 챔피언=슬롯0 cal≈10, 챌린저=슬롯1 cal≈11(<10*1.15) → 교체X / cal≈12(>11.5) → 교체O
    sc.stat[(0, "up")] = {"bal": 110.0, "peak": 110.0, "mdd": -0.10, "n": 10}   # ret10% mdd-10% cal=1.0
    sc.stat[(1, "up")] = {"bal": 110.0, "peak": 110.0, "mdd": -0.0917, "n": 10}  # cal≈1.09
    sel = ChampionSelector(margin=0.15, min_n=5)
    hold = (sel.select([0, 1], "up", sc, current=0, flat=True) == 0)            # 1.09 < 1.0*1.15 → 유지
    sc.stat[(1, "up")] = {"bal": 110.0, "peak": 110.0, "mdd": -0.083, "n": 10}   # cal≈1.20 > 1.15
    switch = (sel.select([0, 1], "up", sc, current=0, flat=True) == 1)
    s12 = (hold and switch)

    checks = [
        ("S1 매니저 load(슬롯0 TrendStack)",       s1),
        ("S2 슬롯 용량 8",                         s2),
        ("S3 언로드+재로드(리부트 없이)",            s3),
        ("S4 1봇 자동 챔피언(슬롯0)",               s4),
        ("S5 +827%/-16.1%/51.3 재현",            s5),
        ("S6 진입 264 / 차단 0",                  s6),
        ("S7 레짐별 스코어 누적(합 264)",            s7),
        ("S8 정상구간 안전 오발동 없음",             s8),
        ("S9 -20% 서킷 트립",                     s9),
        ("S10 킬스위치+리셋",                      s10),
        ("S11 연속손실 차단(4)+리셋, 3+승 무차단",   s11),
        ("S12 히스테리시스(마진 미달 유지/초과 교체)", s12),
    ]
    n_pass = sum(1 for _, ok in checks if ok)
    all_ok = (n_pass == len(checks))

    print(f"=== {BASE} 검증 ({n_pass}/{len(checks)} PASS) ===")
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"리플레이: ret={ret:.2f}% mdd={mdd:.2f}% cal={cal:.2f} 챔피언={res['unique_champions']} 진입/차단={res['n_entered']}/{res['n_halted']}")
    print(f"종합: {'PASS ✅ 전 시나리오 통과' if all_ok else 'FAIL ⚠️ 미통과 항목 확인'}")

    try:
        os.makedirs(OUT_DIR, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d%H%M')
        with open(os.path.join(OUT_DIR, f'{ts}.txt'), 'w', encoding='utf-8') as f:
            f.write(f"[{BASE}] 슬롯매니저+챔피언+안전 검증 리포트\n")
            f.write(f"데이터: 원장={lsrc}\n")
            f.write(f"리플레이: ret={ret:.2f}% mdd={mdd:.2f}% cal={cal:.2f} 챔피언={res['unique_champions']} 진입/차단={res['n_entered']}/{res['n_halted']}\n\n")
            for name, ok in checks:
                f.write(f"  [{'PASS' if ok else 'FAIL'}] {name}\n")
            f.write(f"\n종합: {n_pass}/{len(checks)} {'PASS' if all_ok else 'FAIL'}\n")
            f.write("판정: 챔피언·안전 끼운 오케스트레이터가 검증값 재현 + 로드/언로드/안전 동작 확인\n")
        with open(os.path.join(OUT_DIR, '00WorkHstr_INDEX.txt'), 'a', encoding='utf-8') as f:
            f.write(f"{ts} | {BASE} | {n_pass}/{len(checks)} {'PASS' if all_ok else 'FAIL'} | "
                    f"ret={ret:.1f}% mdd={mdd:.1f}% cal={cal:.1f} 진입{res['n_entered']}/차단{res['n_halted']} | "
                    f"plugin_manager(8슬롯 로드/언로드)+champion(레짐Calmar/히스테리시스)+safety(-20%/킬/연속손실)\n")
        print(f"[기록] ../00WorkHstr/{ts}.txt + INDEX append")
    except Exception as e:
        print(f"[기록 실패] {e}")


if __name__ == '__main__':
    main()
