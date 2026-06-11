# ==============================================================================
# 파일명: PastBackTest_PautoV75.py
# 역할: Pauto V7.5 통합 오프라인 관제탑 (Load & Play 상태 전광판 탑재)
# ==============================================================================

import sys
import os
import subprocess
import time
import requests
import json
import pandas as pd
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QComboBox, 
                             QFileDialog, QDateEdit, QProgressBar, QMessageBox, QGroupBox, QCheckBox, QLineEdit)
from PyQt6.QtCore import QDate, Qt

# [수정 완료]: 하드코딩된 경로 제거 및 현재 실행 파일 위치 동적 감지
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
if not os.path.exists(WORK_DIR):
    os.makedirs(WORK_DIR)
os.chdir(WORK_DIR)

class PastBackTestUI_PautoV75(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pauto V7.5 Master Control Tower (Load & Play Edition)")
        self.setGeometry(100, 100, 780, 580)
        self.setStyleSheet("background-color: #1e1e2e; color: #cdd6f4; font-family: Arial;")
        
        self.selected_files = []
        self.merged_data_path = os.path.join(WORK_DIR, "Merged_Data.csv")
        self.ai_model_path = os.path.join(WORK_DIR, "PautoV75_XGB_1to3_Predictor.json")
        self.params_path = os.path.join(WORK_DIR, "Pauto_Best_Params.json")
        
        self.init_ui()
        self.scan_pauto_modules()
        self.check_system_status() # 프로그램 시작 시 AI 장착 상태 확인

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 🌟 [신규 추가] 시스템 상태 전광판 (현재 장착된 AI 뇌와 훈련 데이터 표시)
        status_group = QGroupBox("🤖 현재 시스템 메모리 상태")
        status_group.setStyleSheet("QGroupBox { border: 1px dashed #f9e2af; padding: 5px; margin-top: 5px; } QGroupBox::title { color: #f9e2af; font-weight: bold; }")
        status_layout = QVBoxLayout(status_group)
        self.lbl_system_status = QLabel("시스템 상태 스캔 중...")
        self.lbl_system_status.setStyleSheet("color: #a6e3a1; font-size: 13px;")
        status_layout.addWidget(self.lbl_system_status)
        main_layout.addWidget(status_group)

        # [1. 데이터 전처리 및 최적화 구역]
        data_group = QGroupBox("1. 과거 데이터 통합 및 엔진 학습")
        data_group.setStyleSheet("QGroupBox { border: 1px solid #89b4fa; margin-top: 10px; padding: 10px; } QGroupBox::title { color: #89b4fa; font-weight: bold; }")
        data_layout = QVBoxLayout(data_group)

        file_layout = QHBoxLayout()
        self.btn_select_files = QPushButton("과거 CSV 파일 추가")
        self.btn_select_files.clicked.connect(self.select_files)
        self.lbl_file_count = QLabel("선택된 파일: 0개")
        file_layout.addWidget(self.btn_select_files)
        file_layout.addWidget(self.lbl_file_count)
        
        date_layout = QHBoxLayout()
        self.date_start = QDateEdit(QDate.currentDate().addYears(-1))
        self.date_end = QDateEdit(QDate.currentDate())
        date_layout.addWidget(QLabel("시작일:"))
        date_layout.addWidget(self.date_start)
        date_layout.addWidget(QLabel("종료일:"))
        date_layout.addWidget(self.date_end)

        oi_layout = QHBoxLayout()
        self.chk_fetch_oi = QCheckBox("🌐 바이낸스 미결제약정(OI) 자동 수집")
        self.chk_fetch_oi.setChecked(True)
        self.chk_fetch_oi.setStyleSheet("color: #f9e2af; font-weight: bold;")
        self.input_symbol = QLineEdit("BTCUSDT")
        self.input_symbol.setFixedWidth(100)
        oi_layout.addWidget(self.chk_fetch_oi)
        oi_layout.addStretch()
        oi_layout.addWidget(QLabel("심볼:"))
        oi_layout.addWidget(self.input_symbol)

        btn_action_layout = QHBoxLayout()
        self.btn_merge = QPushButton("1️⃣ 데이터 병합 및 OI 최적화 실행")
        self.btn_merge.setStyleSheet("background-color: #89b4fa; color: #1e1e2e; font-weight: bold; padding: 8px;")
        self.btn_merge.clicked.connect(self.merge_data)

        self.btn_optimize = QPushButton("3️⃣ ⚙️ 수익 최적화 설정 (Optuna)")
        self.btn_optimize.setStyleSheet("background-color: #cba6f7; color: #1e1e2e; font-weight: bold; padding: 8px;")
        self.btn_optimize.clicked.connect(self.run_optimizer)

        btn_action_layout.addWidget(self.btn_merge)
        btn_action_layout.addWidget(self.btn_optimize)

        data_layout.addLayout(file_layout)
        data_layout.addLayout(date_layout)
        data_layout.addLayout(oi_layout)
        data_layout.addLayout(btn_action_layout)
        main_layout.addWidget(data_group)

        # [2. Pauto 모듈 장착 구역]
        module_group = QGroupBox("2. Pauto V7.5 엔진 모듈")
        module_group.setStyleSheet("QGroupBox { border: 1px solid #a6e3a1; margin-top: 10px; padding: 10px; } QGroupBox::title { color: #a6e3a1; font-weight: bold; }")
        module_layout = QHBoxLayout(module_group)

        self.cb_regime = QComboBox()
        self.cb_predict = QComboBox()
        self.cb_exec = QComboBox()

        module_layout.addWidget(QLabel("장세:"))
        module_layout.addWidget(self.cb_regime)
        module_layout.addWidget(QLabel("타점:"))
        module_layout.addWidget(self.cb_predict)
        module_layout.addWidget(QLabel("청산:"))
        module_layout.addWidget(self.cb_exec)
        main_layout.addWidget(module_group)

        # [3. 실행 구역]
        btn_run_layout = QHBoxLayout()
        self.btn_ai_train = QPushButton("2️⃣ 🧠 AI 딥-패턴 학습 시작")
        self.btn_ai_train.setStyleSheet("background-color: #f9e2af; color: #1e1e2e; font-weight: bold; padding: 10px;")
        self.btn_ai_train.clicked.connect(self.run_ai_training) 
        
        self.btn_run_test = QPushButton("4️⃣ ▶️ Pauto 백테스트 실전 가동")
        self.btn_run_test.setStyleSheet("background-color: #a6e3a1; color: #1e1e2e; font-weight: bold; padding: 10px;")
        self.btn_run_test.clicked.connect(self.run_backtest) 

        btn_run_layout.addWidget(self.btn_ai_train)
        btn_run_layout.addWidget(self.btn_run_test)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)

        main_layout.addLayout(btn_run_layout)
        main_layout.addWidget(self.progress_bar)

    def check_system_status(self):
        """프로그램 구동 시 또는 파일 생성 후, 현재 장착된 AI 뇌의 상태를 표시합니다."""
        status_text = ""
        has_brain = os.path.exists(self.ai_model_path)
        has_params = os.path.exists(self.params_path)

        if has_brain and has_params:
            try:
                with open(self.params_path, "r", encoding="utf-8") as f:
                    p = json.load(f)
                period = p.get('optimized_period', '정보 없음 (구버전)')
                updated = p.get('updated_at', '알 수 없음')
                
                status_text = f"✅ [시스템 준비 완료] 언제든 [4번 실전 가동]이 가능합니다.\n"
                status_text += f"🧠 훈련된 데이터: {period} | ⚙️ 갱신일시: {updated}\n"
                status_text += f"🔥 장착된 설정: 레버리지 {p.get('leverage',1)}x | AI 임계값 {p.get('ml_long_threshold',0.8)*100}% | 피보나치 락인 {p.get('fib_ext_pct', 0.618)}"
            except Exception as e:
                status_text = f"⚠️ AI 파일은 있으나, 파라미터 읽기 오류: {e}"
        elif has_brain:
            status_text = "⚠️ [AI 가중치 있음] 그러나 수익 최적화 설정(.json)이 없습니다. 3번 최적화를 진행해 주세요."
        else:
            status_text = "❌ [AI 뇌 없음] 1번부터 차례대로 시스템을 학습시켜야 합니다."
            
        self.lbl_system_status.setText(status_text)

    # --- 기존 기능들 (스캔, 병합 등)은 동일하게 유지 ---
    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "CSV 선택", "", "CSV Files (*.csv)")
        if files:
            self.selected_files = files
            self.lbl_file_count.setText(f"선택된 파일: {len(self.selected_files)}개")
            try:
                min_date, max_date = None, None
                for f in files:
                    df_temp = pd.read_csv(f, usecols=lambda c: c.lower() in ['timestamp', 'open_time'], on_bad_lines='skip')
                    if not df_temp.empty:
                        col_name = df_temp.columns[0]
                        if pd.api.types.is_numeric_dtype(df_temp[col_name]): df_temp[col_name] = pd.to_datetime(df_temp[col_name], unit='ms')
                        else: df_temp[col_name] = pd.to_datetime(df_temp[col_name])
                        curr_min, curr_max = df_temp[col_name].min(), df_temp[col_name].max()
                        if min_date is None or curr_min < min_date: min_date = curr_min
                        if max_date is None or curr_max > max_date: max_date = curr_max
                if min_date and max_date:
                    self.date_start.setDate(QDate(min_date.year, min_date.month, min_date.day))
                    self.date_end.setDate(QDate(max_date.year, max_date.month, max_date.day))
            except: pass

    def fetch_binance_oi(self, symbol, start_ts, end_ts):
        url = "https://fapi.binance.com/futures/data/openInterestHist"
        all_data = []
        current_start = int(start_ts.timestamp() * 1000)
        end_time_ms = int(end_ts.timestamp() * 1000)
        headers = {'User-Agent': 'Mozilla/5.0'}
        while current_start < end_time_ms:
            params = {"symbol": symbol.upper(), "period": "5m", "limit": 500, "startTime": current_start, "endTime": end_time_ms}
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=10)
                data = resp.json()
                if isinstance(data, dict) and 'msg' in data: break
                if not isinstance(data, list) or len(data) == 0: break
                all_data.extend(data)
                current_start = data[-1]['timestamp'] + 1 
                time.sleep(0.3) 
                QApplication.processEvents()
            except: break
        if not all_data: return pd.DataFrame()
        oi_df = pd.DataFrame(all_data)
        oi_df['timestamp'] = pd.to_datetime(oi_df['timestamp'], unit='ms')
        oi_df.set_index('timestamp', inplace=True)
        oi_df = oi_df[['sumOpenInterest']].rename(columns={'sumOpenInterest': 'open_interest'})
        oi_df['open_interest'] = oi_df['open_interest'].astype(float)
        return oi_df

    def merge_data(self):
        if not self.selected_files: return
        try:
            self.btn_merge.setText("1단계: CSV 병합 중...")
            QApplication.processEvents()
            df_list = []
            for f in self.selected_files:
                df = pd.read_csv(f)
                df.columns = [col.lower() for col in df.columns]
                if 'timestamp' in df.columns:
                    if pd.api.types.is_numeric_dtype(df['timestamp']): df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    else: df['timestamp'] = pd.to_datetime(df['timestamp'])
                elif 'open_time' in df.columns: df['timestamp'] = pd.to_datetime(df['open_time'], unit='ms')
                df.set_index('timestamp', inplace=True)
                df_list.append(df)
            merged_df = pd.concat(df_list).drop_duplicates().sort_index()
            start_str, end_str = self.date_start.date().toString("yyyy-MM-dd"), self.date_end.date().toString("yyyy-MM-dd")
            
            # [수정 완료]: SettingWithCopyWarning 방지를 위해 명시적으로 .copy() 호출
            filtered_df = merged_df.loc[start_str:end_str].copy()
            
            if filtered_df.empty:
                QMessageBox.warning(self, "경고", "해당 기간의 데이터가 없습니다.")
                return
            if self.chk_fetch_oi.isChecked():
                self.btn_merge.setText("2단계: OI API 수집 중...")
                QApplication.processEvents()
                symbol = self.input_symbol.text().strip()
                start_ts, end_ts = filtered_df.index.min(), filtered_df.index.max()
                oi_df = self.fetch_binance_oi(symbol, start_ts, end_ts)
                if not oi_df.empty:
                    filtered_df = filtered_df.join(oi_df, how='left')
                    filtered_df['open_interest'] = filtered_df['open_interest'].ffill().bfill()
                else:
                    buy_pressure = (filtered_df['close'] - filtered_df['low']) / (filtered_df['high'] - filtered_df['low'] + 1e-8)
                    delta_vol = filtered_df['volume'] * (buy_pressure * 2 - 1)
                    filtered_df['open_interest'] = delta_vol.cumsum()
                    filtered_df['open_interest'] = filtered_df['open_interest'] - filtered_df['open_interest'].min() + 1000
            filtered_df.to_csv(self.merged_data_path)
            QMessageBox.information(self, "완료", f"Merged_Data.csv 생성 완료!\n총 {len(filtered_df):,} 캔들")
        except Exception as e: QMessageBox.critical(self, "오류", str(e))
        finally: self.btn_merge.setText("1️⃣ 데이터 병합 및 OI 최적화 실행")

    def scan_pauto_modules(self):
        for cb in [self.cb_regime, self.cb_predict, self.cb_exec]: cb.clear()
        for file in os.listdir(WORK_DIR):
            if file.endswith("_PautoV75.py"):
                name = file[:-3]
                if name.startswith("Regime_"): self.cb_regime.addItem(name)
                elif name.startswith("Predict_"): self.cb_predict.addItem(name)
                elif name.startswith("Exec_"): self.cb_exec.addItem(name)

    def run_ai_training(self):
        if not os.path.exists(self.merged_data_path):
            QMessageBox.warning(self, "경고", "먼저 [1️⃣ 데이터 병합]을 실행해주세요.")
            return
        subprocess.Popen(["python", "ML_Predictor_Pipeline_PautoV75.py"], cwd=WORK_DIR)
        QMessageBox.information(self, "안내", "AI 학습 창이 열렸습니다. 작업이 끝나면 검은 창이 닫힙니다.\n이후 우측 상단의 '시스템 상태'를 새로고침하기 위해 프로그램을 껐다 켜주세요.")

    def run_optimizer(self):
        if not os.path.exists(self.merged_data_path) or not os.path.exists(self.ai_model_path):
            QMessageBox.warning(self, "경고", "먼저 1번(데이터 준비)과 2번(AI 학습)을 완료해야 최적화가 가능합니다.")
            return
        reply = QMessageBox.question(self, "수익 최적화 시작", "머신러닝 수익 최적화(Optuna)를 시작합니다.\n\n약 30~40분이 소요되며, 1위 황금 파라미터는\n자동으로 저장됩니다. 진행하시겠습니까?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            subprocess.Popen(["python", "Optimizer_PautoV75.py"], cwd=WORK_DIR)
            QMessageBox.information(self, "안내", "최적화 창이 열렸습니다. 완료 후 프로그램을 껐다 켜시면\n[현재 시스템 메모리 상태]에 최적화된 값이 반영됩니다.")

    # 🌟 [개선] 파일만 있으면 1,2,3번을 안 누르고 곧바로 점프 가능하도록 유연한 백테스트 실행
    def run_backtest(self):
        # 1번부터 차례대로 안 눌러도, 폴더에 파일만 존재하면 곧장 실행 허용! (Load & Play)
        if not os.path.exists(self.merged_data_path) or not os.path.exists(self.ai_model_path):
            QMessageBox.warning(self, "실행 불가", "데이터 파일(Merged_Data.csv) 또는 AI 모델(json)이 없습니다.\n초기 설정(1,2번)이 필요합니다.")
            return
            
        try:
            self.btn_run_test.setEnabled(False)
            from Backtest_Engine_PautoV75 import Backtest_Engine_PautoV75
            engine = Backtest_Engine_PautoV75(self.cb_regime.currentText(), self.cb_predict.currentText(), self.cb_exec.currentText(), 
                                           self.date_start.date().toString("yyyy-MM-dd"), self.date_end.date().toString("yyyy-MM-dd"))
            engine.run_simulation(progress_callback=lambda p: (self.progress_bar.setValue(p), QApplication.processEvents()))
            QMessageBox.information(self, "완료", "백테스트가 완료되었습니다.\n상세 리포트 창이 열립니다.")
        except Exception as e: 
            QMessageBox.critical(self, "오류", f"실행 에러:\n{str(e)}")
        finally: 
            self.btn_run_test.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PastBackTestUI_PautoV75()
    window.show()
    sys.exit(app.exec())