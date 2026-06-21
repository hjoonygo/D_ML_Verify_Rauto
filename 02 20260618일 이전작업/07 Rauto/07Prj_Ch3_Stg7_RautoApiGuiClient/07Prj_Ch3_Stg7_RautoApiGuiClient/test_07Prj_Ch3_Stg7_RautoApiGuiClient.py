# [파일명] test_07Prj_Ch3_Stg7_RautoApiGuiClient.py
# 코드길이: 약 110줄 / 내부버전: stg7_test_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] ㉡ 통합 시연: 헤드리스 엔진을 REST 서버로 띄우고, 'API 클라이언트'로만 구동한다.
#        load→run→상태조회→kill/reset 을 전부 HTTP로 호출 → 엔진이 분리됨을 증명하고,
#        API 경유로도 +827%가 그대로 재현되는지 확인. 이어서 PyQt6 GUI 클라이언트를
#        오프스크린으로 띄워 'API에서 상태를 끌어와' 화면값을 채우는 배선을 확인.
# [Lookahead] 엔진 리플레이는 entry_t 순서·asof feat(검증과 동일).
# ── 사용 파일 ── engine_service.py / api_server.py / api_client.py / rauto_gui_client.py
# ── 함수 In/Out ── main(): 서버기동→API구동→GUI배선→서버종료
# ── 상수 ── 없음
# ─────────────────────────────────────────────────────────────────────────
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from engine_service import EngineService
from api_server import start_server, stop_server
from api_client import RautoAPIClient


def main():
    engine = EngineService(n_slots=8)
    srv, port = start_server(engine, '127.0.0.1', 0)
    base = f"http://127.0.0.1:{port}"
    client = RautoAPIClient(base)
    print(f"[서버] 헤드리스 엔진 REST 기동 → {base}")

    # 1) API로 봇 로드 → 리플레이 실행
    meta = client.load_bot(0, "bot_trendstack_replay")
    print(f"[API load] 슬롯0 ← {meta['name']}/{meta['version']}")
    client.run_replay()
    acc = client.get_account()
    champ = client.get_champion()
    print(f"[API run]  수익 {acc['ret_pct']}% / MDD {acc['mdd_pct']}% / Calmar {acc['calmar']} / 하드스탑 {acc['hardstop']}")
    print(f"[API champion] 슬롯={champ['unique_champions']} 진입 {champ['n_entered']} / 차단 {champ['n_halted']}")
    scores = client.get_scores()
    print(f"[API scores] 레짐별 키 {list(scores.keys())}")

    # 2) API로 킬스위치 → 리셋
    st = client.trip_kill()
    print(f"[API kill]  halted={st['safety']['halted']}")
    st = client.reset_safety()
    print(f"[API reset] halted={st['safety']['halted']}")

    # 3) PyQt6 GUI 클라이언트: 엔진을 '직접 생성하지 않고' API로 붙어 상태표시 (오프스크린)
    from PyQt6.QtWidgets import QApplication
    from rauto_gui_client import RautoGuiClient
    app = QApplication.instance() or QApplication([])
    gui = RautoGuiClient(client)
    st_gui = gui.refresh()                      # API 폴링 → 화면값 채움
    print(f"[GUI client] UI모드={gui.ui_mode()} | 화면 계좌수익={st_gui['account']['ret_pct']}% | "
          f"테이블행={gui.table.rowCount()} | 챔피언표시={st_gui['champion']['unique_champions']}")
    # 버튼→API 배선 확인
    gui.do_kill()
    print(f"[GUI→API kill]  화면 안전={gui._last_status['safety']['halted']}")
    gui.do_reset()
    print(f"[GUI→API reset] 화면 안전={gui._last_status['safety']['halted']}")

    stop_server(srv)
    print("[서버] 종료")


if __name__ == '__main__':
    main()
