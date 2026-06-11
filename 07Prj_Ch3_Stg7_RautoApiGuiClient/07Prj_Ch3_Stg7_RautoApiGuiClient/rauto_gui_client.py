# [파일명] rauto_gui_client.py
# 코드길이: 약 175줄 / 내부버전: rauto_gui_client_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] PyQt6 GUI를 '엔진을 직접 생성하지 않고' RautoAPIClient로 엔진에 붙는 클라이언트로 구현.
#        (현 V80k GUI가 엔진을 in-process로 생성하던 구조 → API 클라이언트로 전환하는 본보기.)
#        주기적 폴링으로 상태/슬롯/계좌/챔피언/안전을 표시하고, 로드/언로드/런/킬/리셋을 API로 호출.
#        RautoV80k_UI_Components(HUDWidget/DetailChartDialog/get_step_style)는 있으면 재사용,
#        없으면(=pyqtgraph 미설치 등) 경량 스텁으로 대체 → 어디서든 기동.
# [Lookahead] 해당 없음(엔진 상태 표시).
# ── 사용 파일 ── api_client.py(RautoAPIClient) / (옵션) RautoV80k_UI_Components.py
# ── 함수 In/Out ──
#  RautoGuiClient(client)  In: RautoAPIClient → Out: QMainWindow(클라이언트 GUI)
#   .refresh()    In: -            → Out: status dict (API에서 폴링→화면 갱신, 테스트용 반환)
#   .do_load()/do_unload()/do_run()/do_kill()/do_reset()  In: - → Out: API 호출 후 refresh
#   .ui_mode()    In: -            → Out: 'UI_Components' | 'stub'
# ── 상수 ── POLL_MS 폴링주기
# ─────────────────────────────────────────────────────────────────────────
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView)
from PyQt6.QtCore import QTimer, Qt

POLL_MS = 2000

try:
    from RautoV80k_UI_Components import HUDWidget, get_step_style
    _UI_OK = True
except Exception:
    _UI_OK = False

    def get_step_style(v):
        return ({0: ("대기", "#2B313F"), 1: ("실행", "#104221"),
                 2: ("익손절중", "#8C5B00"), 3: ("강제종료", "#6A1818")}).get(v, ("오류", "#000"))


class RautoGuiClient(QMainWindow):
    def __init__(self, client):
        super().__init__()
        self.client = client
        self.setWindowTitle("Rauto — 엔진 API 클라이언트 (관리모드)")
        self.resize(1170, 540)
        self._last_status = None

        central = QWidget()
        root = QVBoxLayout(central)

        # 상단 HUD (UI_Components 있으면 재사용)
        if _UI_OK:
            self.hud = HUDWidget()
        else:
            self.hud = QLabel("HUD(stub): 엔진 상태 표시")
            self.hud.setStyleSheet("padding:8px; border:1px solid #888;")
        root.addWidget(self.hud)

        # 계좌 요약
        self.lbl_acct = QLabel("계좌: -")
        self.lbl_champ = QLabel("챔피언: -")
        self.lbl_safety = QLabel("안전: -")
        for w in (self.lbl_acct, self.lbl_champ, self.lbl_safety):
            root.addWidget(w)

        # 슬롯 테이블
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["슬롯", "봇", "챔피언"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table)

        # 버튼바 (모두 API 호출)
        bar = QHBoxLayout()
        self.btn_load = QPushButton("TrendStack 로드(슬롯0)")
        self.btn_unload = QPushButton("슬롯0 언로드")
        self.btn_run = QPushButton("리플레이 실행")
        self.btn_kill = QPushButton("킬스위치")
        self.btn_reset = QPushButton("안전 리셋")
        self.btn_load.clicked.connect(self.do_load)
        self.btn_unload.clicked.connect(self.do_unload)
        self.btn_run.clicked.connect(self.do_run)
        self.btn_kill.clicked.connect(self.do_kill)
        self.btn_reset.clicked.connect(self.do_reset)
        for b in (self.btn_load, self.btn_unload, self.btn_run, self.btn_kill, self.btn_reset):
            bar.addWidget(b)
        root.addLayout(bar)

        self.setCentralWidget(central)

        # 주기 폴링
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(POLL_MS)

    def ui_mode(self):
        return "UI_Components" if _UI_OK else "stub"

    def refresh(self):
        try:
            st = self.client.get_status()
        except Exception as e:
            self.lbl_acct.setText(f"계좌: (엔진 연결 실패: {e})")
            return None
        self._last_status = st
        acc = st.get("account", {})
        champ = st.get("champion", {})
        saf = st.get("safety", {})

        price_txt = f"잔액 ${acc.get('balance', 0):,.0f}"
        regime_txt = f"수익 {acc.get('ret_pct', 0)}% / MDD {acc.get('mdd_pct', 0)}%"
        status_txt = "정지" if saf.get("halted") else "정상"
        if _UI_OK:
            self.hud.update_hud(acc.get('balance', 0.0), regime_txt, 0, status_txt,
                                "halted" if saf.get("halted") else "ok",
                                "CRITICAL" if saf.get("halted") else "INFO")
        else:
            self.hud.setText(f"HUD: {price_txt} | {regime_txt} | 상태:{status_txt}")

        self.lbl_acct.setText(f"계좌: 잔액 ${acc.get('balance', 0):,.2f} | 수익 {acc.get('ret_pct')}% | "
                              f"MDD {acc.get('mdd_pct')}% | Calmar {acc.get('calmar')} | 거래 {acc.get('trades')} | 하드스탑 {acc.get('hardstop')}")
        self.lbl_champ.setText(f"챔피언: 슬롯 {champ.get('unique_champions')} | 진입 {champ.get('n_entered')} / 차단 {champ.get('n_halted')}")
        self.lbl_safety.setText(f"안전: {'⛔정지' if saf.get('halted') else '✅정상'} "
                                f"(kill={saf.get('killed')} circuit={saf.get('circuit')} consec={saf.get('consec_losses')})")

        # 슬롯 테이블
        loaded = set(st.get("slots_loaded", []))
        champs = set(champ.get("unique_champions", []))
        try:
            slots = self.client.list_slots()
        except Exception:
            slots = [{"slot": i, "meta": None} for i in range(st.get("n_slots", 8))]
        self.table.setRowCount(len(slots))
        for i, s in enumerate(slots):
            meta = s.get("meta")
            name = (meta or {}).get("name", "-") if meta else "-"
            self.table.setItem(i, 0, QTableWidgetItem(str(s["slot"])))
            self.table.setItem(i, 1, QTableWidgetItem(name if s["slot"] in loaded else "(빈 슬롯)"))
            self.table.setItem(i, 2, QTableWidgetItem("★ 챔피언" if s["slot"] in champs else ""))
        return st

    def do_load(self):
        try:
            self.client.load_bot(0, "bot_trendstack_replay")
        except Exception:
            pass
        self.refresh()

    def do_unload(self):
        try:
            self.client.unload_bot(0)
        except Exception:
            pass
        self.refresh()

    def do_run(self):
        try:
            self.client.run_replay()
        except Exception:
            pass
        self.refresh()

    def do_kill(self):
        try:
            self.client.trip_kill()
        except Exception:
            pass
        self.refresh()

    def do_reset(self):
        try:
            self.client.reset_safety()
        except Exception:
            pass
        self.refresh()
