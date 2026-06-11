# ==============================================================================
# 파일명: RautoV80k_ChampionGUI.py
# 코드길이: 약 320줄 / 내부버전: V8.0k 챔피언 시스템 메인 GUI
# 작성일: 2026-04-29
# ==============================================================================
# [패치 사항 (V75 → V80k)]
#   1. BASE_DIR 동적 탐지 (스크립트 자기 폴더)
#   2. R 콤보 변경 시 P/E 자동 페어링 (PAIRED_MODULES 사전)
#   3. Hot-Reload 백그라운드 스레드 (Not Responding 해결)
#   4. Bot ID 클릭 → 강화된 DetailChartDialog (3일치 차트 + 거래 패널)
#   5. 2버튼 마스터 (Panic / 파라미터 Hot-Reload)
# ==============================================================================
import sys
import os
import subprocess

# 동적 BASE_DIR — 스크립트 자기 위치
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ['PAUTO_BASE_DIR'] = BASE_DIR
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QTableWidget, QTableWidgetItem, QLabel,
                             QHeaderView, QComboBox, QPushButton, QInputDialog, QMessageBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor

from RautoV80k_UI_Components import DetailChartDialog, HUDWidget, get_step_style
from RautoV80k_TradingEngine import RautoV80k_TradingEngine


# ==============================================================================
# R/P/E 페어링 사전 — R 선택 시 자동 P/E 세팅
# ==============================================================================
PAIRED_MODULES = {
    # V8.0k 첫 번째 외부 전략
    'R_ML_V80k_3balancedTBM_R001': (
        'P_ML_V80k_3balancedTBM_R001',
        'E_ML_V80k_3balancedTBM_R001'
    ),
    # ★ V80k_Verify_1: Observer 봇 (검증 데이터 수집 전용, 거래 X)
    'R_Observer_V80k_R001': (
        'P_Observer_V80k_R001',
        'E_Observer_V80k_R001'
    ),
    # 기존 V75 cRSI 전략 (있으면)
    'Regime_Master_V75': (
        'Predict_cRSI_V75',
        'Exec_Dynamic_TS_V75'
    ),
}


DARK_THEME_QSS = """
QMainWindow { background-color: #121419; }
QWidget { color: #E0E0E0; font-family: 'Malgun Gothic', sans-serif; }
QTableWidget { background-color: #1E222D; gridline-color: #2B313F; border: 1px solid #2B313F; border-radius: 5px; }
QHeaderView::section { background-color: #121419; color: #8B94A5; border: none; padding: 10px; font-weight: bold; font-size: 13px; }
QComboBox { background-color: #2B313F; border: 1px solid #434C5E; border-radius: 3px; padding: 4px; color: white; }
QPushButton { border-radius: 4px; padding: 6px 12px; font-weight: bold; border: none; }
QPushButton:hover { opacity: 0.8; }
"""


class DynamicComboBox(QComboBox):
    """R_/P_/E_ 접두사 .py 자동 스캔."""
    def __init__(self, prefix_list, paired_combos=None):
        super().__init__()
        self.prefix_list = prefix_list
        self.paired_combos = paired_combos or {}  # {'P': p_combo, 'E': e_combo}
        self.populate_items()
    
    def showPopup(self):
        self.populate_items()
        super().showPopup()
    
    def populate_items(self):
        current = self.currentText()
        self.clear()
        files = []
        if os.path.exists(BASE_DIR):
            for f in os.listdir(BASE_DIR):
                if f.endswith('.py'):
                    for pref in self.prefix_list:
                        if f.startswith(pref):
                            files.append(f[:-3])
                            break
        files.sort()
        if not files: files = ["모듈 없음"]
        self.addItems(files)
        if current in files: self.setCurrentText(current)
    
    def trigger_pairing(self):
        """R 선택 시 P/E 자동 세팅."""
        r_name = self.currentText()
        if r_name in PAIRED_MODULES:
            p_target, e_target = PAIRED_MODULES[r_name]
            if 'P' in self.paired_combos:
                p_combo = self.paired_combos['P']
                p_combo.populate_items()
                p_idx = p_combo.findText(p_target)
                if p_idx >= 0: p_combo.setCurrentIndex(p_idx)
            if 'E' in self.paired_combos:
                e_combo = self.paired_combos['E']
                e_combo.populate_items()
                e_idx = e_combo.findText(e_target)
                if e_idx >= 0: e_combo.setCurrentIndex(e_idx)


class HotReloadWorker(QThread):
    """모듈 reimport를 백그라운드에서 — GUI Not Responding 해결."""
    finished_signal = pyqtSignal(list)  # 적용된 봇 ID 리스트
    
    def __init__(self, engine, table):
        super().__init__()
        self.engine = engine
        self.table = table
    
    def run(self):
        reloaded = []
        for i, bot in enumerate(self.engine.bots):
            if bot.position.get("side", "WAIT") == "WAIT" and bot.state.value == 1:
                r_mod = self.table.cellWidget(i, 2).currentText()
                p_mod = self.table.cellWidget(i, 3).currentText()
                e_mod = self.table.cellWidget(i, 4).currentText()
                self.engine.update_bot_modules(i, r_mod, p_mod, e_mod)
                reloaded.append(bot.bot_id)
        self.finished_signal.emit(reloaded)


class ChampionGUI_V80k(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("V8.0k 챔피언 시스템 — Binance Rauto 실시간 관제탑")
        self.resize(1550, 800)
        self.setStyleSheet(DARK_THEME_QSS)
        
        self.current_popup_bot_id = None
        self.df_last_ts = 0
        self.popup = None
        
        self.engine = RautoV80k_TradingEngine()
        self.engine.sync_signal.connect(self.update_ui_from_engine)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setSpacing(15)
        
        self.hud = HUDWidget()
        self.layout.addWidget(self.hud)
        self.init_master_controls()
        
        self.table = QTableWidget(8, 9)
        headers = ["Bot ID (메모)", "포지션", "장세 모듈", "예측 모듈",
                   "실행 모듈", "자산 (선물/현물)", "상태", "제어(스텝)", "삭제"]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.layout.addWidget(self.table)
        
        self.init_table_ui()
        self.engine.start()

    def init_master_controls(self):
        master_layout = QHBoxLayout()
        
        btn_panic = QPushButton("[🚨 Panic Sell (전체 청산)]")
        btn_panic.setStyleSheet("background-color: #8B0000; color: white; padding: 10px;")
        btn_panic.clicked.connect(self.panic_sell_all)
        
        btn_reload = QPushButton("[🔄 파라미터 Hot-Reload]")
        btn_reload.setStyleSheet("background-color: #2E8B57; color: white; padding: 10px;")
        btn_reload.clicked.connect(self.safe_hot_reload)
        
        master_layout.addWidget(btn_panic)
        master_layout.addWidget(btn_reload)
        master_layout.addStretch()
        self.layout.addLayout(master_layout)

    def init_table_ui(self):
        for i in range(8):
            self.table.setRowHeight(i, 60)
            bot_id = f"Bot_{i+1}"
            
            # Col 0: Bot ID + 메모
            cw_bot = QWidget()
            l_bot = QHBoxLayout(cw_bot)
            l_bot.setContentsMargins(5, 0, 5, 0)
            btn_bot = QPushButton(bot_id)
            btn_bot.setProperty("memo_text", bot_id)
            btn_bot.setStyleSheet("background-color: transparent; text-decoration: underline; color: #88C0D0; font-weight: bold;")
            btn_bot.clicked.connect(lambda chk, b_id=bot_id: self.open_popup(b_id))
            
            btn_memo = QPushButton("📝")
            btn_memo.setFixedWidth(28)
            btn_memo.setStyleSheet("background-color: #3B4252; color: white; border: 1px solid #434C5E; border-radius: 3px;")
            btn_memo.clicked.connect(lambda chk, b_id=bot_id, btn=btn_bot: self.set_bot_memo(b_id, btn))
            l_bot.addWidget(btn_bot)
            l_bot.addWidget(btn_memo)
            self.table.setCellWidget(i, 0, cw_bot)
            
            # Col 1: 포지션
            item_pos = QTableWidgetItem("대기")
            item_pos.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 1, item_pos)
            
            # Col 2-4: R/P/E 콤보 (R 변경 시 자동 페어링)
            p_combo = DynamicComboBox(['Predict_', 'P_'])
            e_combo = DynamicComboBox(['Exec_', 'E_'])
            r_combo = DynamicComboBox(['Regime_', 'R_'], paired_combos={'P': p_combo, 'E': e_combo})
            r_combo.currentTextChanged.connect(lambda txt, rc=r_combo: rc.trigger_pairing())
            
            self.table.setCellWidget(i, 2, r_combo)
            self.table.setCellWidget(i, 3, p_combo)
            self.table.setCellWidget(i, 4, e_combo)
            
            # Col 5: 자산
            item_asset = QTableWidgetItem("선물: $10,000 (+0)\n현물: $0")
            item_asset.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 5, item_asset)
            
            # Col 6: 상태
            status_item = QTableWidgetItem("대기")
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setBackground(QColor("#2B313F"))
            self.table.setItem(i, 6, status_item)
            
            # Col 7: 제어
            btn_step = QPushButton("작업시작")
            btn_step.setStyleSheet("background-color: #5E81AC; color: white;")
            btn_step.clicked.connect(lambda chk, r=i: self.handle_step_click(r))
            cw_step = QWidget()
            l_step = QHBoxLayout(cw_step)
            l_step.setContentsMargins(10, 5, 10, 5)
            l_step.addWidget(btn_step)
            self.table.setCellWidget(i, 7, cw_step)
            
            # Col 8: 삭제
            btn_del = QPushButton("삭제")
            btn_del.setStyleSheet("background-color: #BF616A; color: white;")
            cw_del = QWidget()
            l_del = QHBoxLayout(cw_del)
            l_del.setContentsMargins(10, 5, 10, 5)
            l_del.addWidget(btn_del)
            self.table.setCellWidget(i, 8, cw_del)

    def set_bot_memo(self, bot_id, btn_bot):
        text, ok = QInputDialog.getText(self, '메모 설정', f'{bot_id} 전략 메모:')
        if ok:
            disp = f"{bot_id} [{text}]" if text else bot_id
            btn_bot.setProperty("memo_text", disp)
            btn_bot.setText(disp)

    def handle_step_click(self, row):
        bot_state_val = self.engine.bots[row].state.value
        next_val = (bot_state_val + 1) % 4
        
        if next_val == 1:
            r_mod = self.table.cellWidget(row, 2).currentText()
            p_mod = self.table.cellWidget(row, 3).currentText()
            e_mod = self.table.cellWidget(row, 4).currentText()
            self.engine.update_bot_modules(row, r_mod, p_mod, e_mod)
        
        self.engine.process_bot_step(row, next_val)
        
        status_item = self.table.item(row, 6)
        btn_step = self.table.cellWidget(row, 7).layout().itemAt(0).widget()
        label, bg, _ = get_step_style(next_val)
        status_item.setText(label)
        status_item.setBackground(QColor(bg))
        
        if next_val == 0:
            btn_step.setText("작업시작"); btn_step.setStyleSheet("background-color: #5E81AC; color: white;")
        elif next_val == 1:
            btn_step.setText("익손절"); btn_step.setStyleSheet("background-color: #A3BE8C; color: black;")
        elif next_val == 2:
            btn_step.setText("강제종료"); btn_step.setStyleSheet("background-color: #EBCB8B; color: black;")
        elif next_val == 3:
            btn_step.setText("처리중"); btn_step.setStyleSheet("background-color: #BF616A; color: white;")

    def safe_hot_reload(self):
        """[V80k 패치] 백그라운드 스레드로 임포트 — Not Responding 해결."""
        self.reload_worker = HotReloadWorker(self.engine, self.table)
        self.reload_worker.finished_signal.connect(self._on_reload_done)
        self.reload_worker.start()

    def _on_reload_done(self, reloaded):
        msg = (f"안전 업데이트 완료.\n적용된 봇: {', '.join(reloaded)}"
               if reloaded else "현재 포지션이 비어있는 RUNNING 봇이 없습니다.")
        QMessageBox.information(self, "🔄 파라미터 Hot-Reload", msg)

    def panic_sell_all(self):
        """전체 봇 강제 청산."""
        reply = QMessageBox.question(self, "Panic Sell", "모든 봇을 강제 청산하시겠습니까?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            for i, bot in enumerate(self.engine.bots):
                if bot.position.get('side', 'WAIT') != 'WAIT':
                    self.engine.process_bot_step(i, 3)  # FORCE_CLOSED
            QMessageBox.information(self, "Panic Sell", "전체 봇 청산 명령 전송 완료.")

    def open_popup(self, bot_id):
        self.current_popup_bot_id = bot_id
        bot_idx = int(bot_id.split('_')[1]) - 1
        self.popup = DetailChartDialog(
            self.engine.bots[bot_idx],
            "데이터 로딩 중...",
            self.engine.data_engine.get_latest_data()
        )
        self.popup.show()

    def update_ui_from_engine(self, price, regime, sys_status, sys_load, bot_states, market_metrics=None):
        # ★ V80k_Verify_2: 시장 객관 지표 활용
        if market_metrics is None:
            market_metrics = {}
        self.hud.update_hud(price, regime, sys_load, sys_status, "정상",
                            market_atr_pct=market_metrics.get('atr_pct'),
                            market_vol_trend=market_metrics.get('vol_trend'),
                            market_crsi=market_metrics.get('crsi'))
        
        for i, state_dict in bot_states.items():
            pos_str = state_dict['side']
            item_pos = self.table.item(i, 1)
            item_pos.setText(pos_str if pos_str != "WAIT" else "대기")
            if pos_str == "LONG":
                item_pos.setForeground(QColor("#00FF41"))
            elif pos_str == "SHORT":
                item_pos.setForeground(QColor("#FF3131"))
            else:
                item_pos.setForeground(QColor("#E0E0E0"))
            
            f_bal = state_dict['futures_bal']
            s_bal = state_dict['spot_bal']
            pnl = state_dict['pnl']
            pnl_str = f"선물: ${f_bal:,.0f} ({pnl:+.0f})\n현물: ${s_bal:,.0f}"
            self.table.item(i, 5).setText(pnl_str)
        
        # 차트 갱신
        df = self.engine.data_engine.get_latest_data()
        if df is None or df.empty: return
        current_ts = df['timestamp'].iloc[-1] if 'timestamp' in df.columns else df.index[-1]
        
        if current_ts != self.df_last_ts:
            if self.popup is not None and self.popup.isVisible() and self.current_popup_bot_id:
                bot_idx = int(self.current_popup_bot_id.split('_')[1]) - 1
                self.popup.refresh_chart(df)
                self.popup.update_realtime(price, self.engine.bots[bot_idx], regime_str=regime)
            self.df_last_ts = current_ts

    def closeEvent(self, event):
        self.engine.stop_engine()
        event.accept()


if __name__ == "__main__":
    import traceback as _tb
    import time as _t
    
    # ★ v3: 글로벌 예외 후크 — 처리되지 않은 예외도 콘솔에 표시
    def _global_excepthook(exc_type, exc_value, exc_traceback):
        print("\n" + "="*70)
        print("🚨 [V80k v3] 처리되지 않은 예외 발생 — 시스템 정지")
        print("="*70)
        _tb.print_exception(exc_type, exc_value, exc_traceback)
        # 파일에도 기록
        try:
            with open(os.path.join(BASE_DIR, "RautoV80k_CRASH.log"), "a", encoding="utf-8") as f:
                f.write(f"\n=== {_t.strftime('%Y-%m-%d %H:%M:%S')} CRASH ===\n")
                _tb.print_exception(exc_type, exc_value, exc_traceback, file=f)
        except Exception: pass
        print("="*70)
        # 콘솔 닫히지 않게
        input("\n[엔터를 눌러 종료] >>> ")
    
    sys.excepthook = _global_excepthook
    
    print(f"[V80k v3] 시작 PID={os.getpid()} BASE_DIR={BASE_DIR}")
    print(f"[V80k v3] Python {sys.version.split()[0]} / 작업 폴더 안 파일 확인 중...")
    
    # 필수 파일 사전 체크
    REQUIRED_FILES = [
        "PautoV80_Regime_Model_v6.json",
        "PautoV80_TBM_BULL_v2.json",
        "PautoV80_TBM_BEAR_v2.json",
        "PautoV80_TBM_CHOP_v2.json",
        "PautoV80_Regime_ML.py",
        "R_ML_V80k_3balancedTBM_R001.py",
        "P_ML_V80k_3balancedTBM_R001.py",
        "E_ML_V80k_3balancedTBM_R001.py",
        "RautoV80k_DataEngine.py",
        "RautoV80k_BotManager.py",
        "RautoV80k_TradingEngine.py",
        "RautoV80k_UI_Components.py",
        "RautoV80k_Logger.py",
    ]
    missing = []
    for fn in REQUIRED_FILES:
        if not os.path.exists(os.path.join(BASE_DIR, fn)):
            missing.append(fn)
    if missing:
        print(f"\n🚨 누락된 파일:")
        for f in missing: print(f"   ❌ {f}")
        print(f"\n폴더 확인: {BASE_DIR}")
        input("[엔터를 눌러 종료] >>> ")
        sys.exit(1)
    print(f"[V80k v3] ✅ 필수 파일 13개 모두 확인됨")
    
    try:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        print("[V80k v3] PyQt6 QApplication 생성 완료")
        
        window = ChampionGUI_V80k()
        print("[V80k v3] GUI 생성 완료")
        
        window.show()
        print("[V80k v3] GUI 표시 완료. 이벤트 루프 진입 (이제 작동 중)")
        print("="*60)
        
        sys.exit(app.exec())
    except Exception as e:
        print(f"\n🚨 [V80k v3] 메인 스레드 예외:")
        _tb.print_exc()
        input("[엔터를 눌러 종료] >>> ")
        sys.exit(1)
