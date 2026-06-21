# [파일명] check_07Prj_Ch3_Stg7_RautoApiGuiClient.py
# 코드길이: 약 150줄 / 내부버전: stg7_check_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] ㉡(API 경계 + GUI 클라이언트)를 10개 시나리오로 검증한다.
#        핵심: 엔진을 HTTP API 뒤로 분리하고, 클라이언트로만 구동해도 +827% 재현 +
#        GUI가 엔진을 '직접 생성하지 않고' API에서 상태를 끌어와 화면을 채우는가.
# [Lookahead] 엔진 리플레이는 entry_t 순서·asof feat.
# ── 사용 파일 ── engine_service / api_server / api_client / rauto_gui_client / rauto_paper_engine
#  OUT(../00WorkHstr) <YYYYMMDDHHMM>.txt + 00WorkHstr_INDEX.txt(append)
# ── 함수 In/Out ── approx(a,b,t) / main(): 10 시나리오 PASS/FAIL + 기록
# ── 상수 ── 기대값 / OUT_DIR
# ─────────────────────────────────────────────────────────────────────────
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from datetime import datetime
from engine_service import EngineService
from api_server import start_server, stop_server
from api_client import RautoAPIClient

BASE = "07Prj_Ch3_Stg7_RautoApiGuiClient"
OUT_DIR = os.path.join('..', '00WorkHstr')
EXP_RET = 827; EXP_MDD = -16.1; EXP_CAL = 51.3


def approx(a, b, t=1e-9):
    try:
        return abs(float(a) - float(b)) <= t
    except (TypeError, ValueError):
        return False


def main():
    engine = EngineService(n_slots=8)
    srv, port = start_server(engine, '127.0.0.1', 0)
    client = RautoAPIClient(f"http://127.0.0.1:{port}")

    # S1 서버 도달 + 상태규약
    st0 = client.get_status()
    s1 = all(k in st0 for k in ("slots_loaded", "n_slots", "safety", "account", "champion"))

    # S2 API 로드
    meta = client.load_bot(0, "bot_trendstack_replay")
    s2 = (meta.get("name") == "TrendStack" and client.get_status()["slots_loaded"] == [0])

    # S3 API 런 → 재현
    client.run_replay()
    acc = client.get_account()
    s3 = (round(acc["ret_pct"]) == EXP_RET and round(acc["mdd_pct"], 1) == EXP_MDD and round(acc["calmar"], 1) == EXP_CAL)

    # S4 API 챔피언
    champ = client.get_champion()
    s4 = (champ["unique_champions"] == [0] and champ["n_entered"] == 264 and champ["n_halted"] == 0)

    # S5 API 스코어(레짐별)
    scores = client.get_scores()
    s5 = (len(scores) >= 2 and any(k.startswith("0|") for k in scores))

    # S6 API 킬/리셋
    halted_after_kill = client.trip_kill()["safety"]["halted"]
    halted_after_reset = client.reset_safety()["safety"]["halted"]
    s6 = (halted_after_kill is True and halted_after_reset is False)

    # S7 GUI 클라이언트(오프스크린): 엔진 직접생성 없이 API에서 상태 끌어와 화면값 채움
    from PyQt6.QtWidgets import QApplication
    from rauto_gui_client import RautoGuiClient
    app = QApplication.instance() or QApplication([])
    gui = RautoGuiClient(client)
    st_gui = gui.refresh()
    s7 = (st_gui is not None and round(st_gui["account"]["ret_pct"]) == EXP_RET
          and gui.table.rowCount() == engine.n_slots)

    # S8 GUI 버튼 → API 배선 (kill/reset)
    gui.do_kill(); killed = gui._last_status["safety"]["halted"]
    gui.do_reset(); unkilled = gui._last_status["safety"]["halted"]
    s8 = (killed is True and unkilled is False)

    # S9 API 언로드
    client.unload_bot(0)
    s9 = (client.get_status()["slots_loaded"] == [])

    # S10 GUI는 엔진을 직접 생성하지 않음(분리 확인): client만 보유, engine 참조 없음
    s10 = (hasattr(gui, "client") and not hasattr(gui, "engine") and not hasattr(gui, "orch"))

    stop_server(srv)

    checks = [
        ("S1 서버 도달 + 상태규약 키",            s1),
        ("S2 API 봇 로드(슬롯0 TrendStack)",      s2),
        ("S3 API 경유 +827%/-16.1%/51.3 재현",   s3),
        ("S4 API 챔피언=[0] 진입264/차단0",       s4),
        ("S5 API 레짐별 스코어 조회",              s5),
        ("S6 API 킬스위치/리셋",                  s6),
        ("S7 GUI: API에서 상태 끌어와 화면채움",     s7),
        ("S8 GUI 버튼→API 배선(kill/reset)",      s8),
        ("S9 API 언로드(슬롯 비움)",               s9),
        ("S10 GUI 엔진 직접생성 없음(분리)",        s10),
    ]
    n_pass = sum(1 for _, ok in checks if ok)
    all_ok = (n_pass == len(checks))

    print(f"=== {BASE} 검증 ({n_pass}/{len(checks)} PASS) ===")
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"API경유 재현: ret={acc['ret_pct']}% mdd={acc['mdd_pct']}% cal={acc['calmar']} 챔피언={champ['unique_champions']}")
    print(f"GUI UI모드: {gui.ui_mode()} (PC: pyqtgraph+UI_Components 있으면 'UI_Components')")
    print(f"종합: {'PASS ✅ 전 시나리오 통과' if all_ok else 'FAIL ⚠️ 미통과 항목 확인'}")

    try:
        os.makedirs(OUT_DIR, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d%H%M')
        with open(os.path.join(OUT_DIR, f'{ts}.txt'), 'w', encoding='utf-8') as f:
            f.write(f"[{BASE}] API 경계 + GUI 클라이언트 검증 리포트\n")
            f.write(f"API경유 재현: ret={acc['ret_pct']}% mdd={acc['mdd_pct']}% cal={acc['calmar']} 챔피언={champ['unique_champions']}\n")
            f.write(f"GUI UI모드: {gui.ui_mode()}\n\n")
            for name, ok in checks:
                f.write(f"  [{'PASS' if ok else 'FAIL'}] {name}\n")
            f.write(f"\n종합: {n_pass}/{len(checks)} {'PASS' if all_ok else 'FAIL'}\n")
            f.write("판정: 엔진이 API 뒤로 분리되고 클라이언트로만 구동/재현, GUI는 API 클라이언트로 동작\n")
        with open(os.path.join(OUT_DIR, '00WorkHstr_INDEX.txt'), 'a', encoding='utf-8') as f:
            f.write(f"{ts} | {BASE} | {n_pass}/{len(checks)} {'PASS' if all_ok else 'FAIL'} | "
                    f"API경유 ret={acc['ret_pct']}% mdd={acc['mdd_pct']}% cal={acc['calmar']} | "
                    f"engine_service+REST(api_server/api_client)+PyQt6 GUI클라이언트(엔진분리)\n")
        print(f"[기록] ../00WorkHstr/{ts}.txt + INDEX append")
    except Exception as e:
        print(f"[기록 실패] {e}")


if __name__ == '__main__':
    main()
