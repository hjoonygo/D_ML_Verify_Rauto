# ==============================================================================
# 파일명: RautoV80k_UI_Components.py
# 코드길이: 약 380줄 / 내부버전: V8.0k v2 (크로스헤어 + 강화 마커)
# 작성일: 2026-04-29
# ==============================================================================
# [v2 패치]
#   1. 크로스헤어: 마우스 위치에 십자선 + 시간(아래) + 가격(좌측)
#   2. 마커 강화:
#      - LONG 진입: 녹색 위쪽 삼각형 + L1/L2/L3 (분할 진입 대비)
#      - SHORT 진입: 적색 아래쪽 삼각형 + S1/S2/S3
#      - LONG 익절(pnl>0): 녹색 ○
#      - LONG 손절(pnl<0): 녹색 ✕
#      - SHORT 익절(pnl>0): 적색 ○
#      - SHORT 손절(pnl<0): 적색 ✕
# ==============================================================================
import numpy as np
import pyqtgraph as pg
from datetime import datetime
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QFrame, QWidget, QTableWidget,
                             QTableWidgetItem, QHeaderView, QSplitter)
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QColor, QFont, QPainter, QPicture


# ==============================================================================
# CandlestickItem
# ==============================================================================
class CandlestickItem(pg.GraphicsObject):
    def __init__(self, data):
        pg.GraphicsObject.__init__(self)
        self.data = data
        self.generatePicture()

    def generatePicture(self):
        self.picture = QPicture()
        p = QPainter(self.picture)
        p.setPen(pg.mkPen('w'))
        w = 40
        for t, open_p, close_p, low_p, high_p in self.data:
            if open_p > close_p:
                p.setBrush(pg.mkBrush('#FF3131'))
                p.setPen(pg.mkPen('#FF3131'))
            else:
                p.setBrush(pg.mkBrush('#00FF41'))
                p.setPen(pg.mkPen('#00FF41'))
            p.drawLine(pg.QtCore.QPointF(t, low_p), pg.QtCore.QPointF(t, high_p))
            p.drawRect(pg.QtCore.QRectF(t - w/2, open_p, w, close_p - open_p))
        p.end()

    def paint(self, p, *args):
        p.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return QRectF(self.picture.boundingRect())


# ==============================================================================
# HUDWidget (변경 없음)
# ==============================================================================
class HUDWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #1E222D; border: 1px solid #2B313F; border-radius: 5px;")
        layout = QHBoxLayout(self)
        font = QFont("Malgun Gothic", 11, QFont.Weight.Bold)
        self.lbl_price = QLabel("1. BTC: $0.00")
        # ★ V80k_Verify_2: '장세' → 시장 객관 지표 (모듈 무관)
        self.lbl_market = QLabel("2. 시장: ATR --, Vol↑--")
        self.lbl_load = QLabel("3. 부하: 0%")
        self.lbl_status = QLabel("4. 상태: 준비")
        self.lbl_alert = QLabel("5. 알림: 정상")
        for lbl in [self.lbl_price, self.lbl_market, self.lbl_load, self.lbl_status, self.lbl_alert]:
            lbl.setFont(font)
            lbl.setStyleSheet("color: #E0E0E0; border: none;")
            layout.addWidget(lbl)

    def update_hud(self, price, regime, load, status, alert_msg, alert_lv="INFO",
                   market_atr_pct=None, market_vol_trend=None, market_crsi=None):
        """V80k_Verify_2: regime 파라미터는 호환 위해 유지하되 메인 표시는 시장 객관 지표.
        
        market_atr_pct: 15m ATR % (변동성)
        market_vol_trend: 1시간 평균 거래량 변화율 % (↑/↓)
        market_crsi: cRSI (옵션, 0~100, 사이클 강도)
        """
        self.lbl_price.setText(f"1. BTC: ${price:,.2f}")
        
        # 시장 객관 지표 — 가용한 것만 표시
        market_parts = []
        if market_atr_pct is not None:
            market_parts.append(f"ATR15m {market_atr_pct:.2f}%")
        if market_vol_trend is not None:
            arrow = '↑' if market_vol_trend >= 0 else '↓'
            market_parts.append(f"Vol{arrow}{abs(market_vol_trend):.0f}%")
        if market_crsi is not None:
            market_parts.append(f"cRSI{int(market_crsi)}")
        
        if market_parts:
            self.lbl_market.setText(f"2. 시장: {' | '.join(market_parts)}")
        else:
            # 폴백: 기존 regime 표시 (호환)
            self.lbl_market.setText(f"2. 장세(R모듈): {regime}")
        
        self.lbl_load.setText(f"3. 부하: {load}%")
        self.lbl_status.setText(f"4. 상태: {status}")
        self.lbl_alert.setText(f"5. 알림: {alert_msg}")
        if alert_lv == "WARNING":
            self.lbl_alert.setStyleSheet("color: #FFA500; font-weight: bold;")
        elif alert_lv == "CRITICAL":
            self.lbl_alert.setStyleSheet("color: #FF0000; font-weight: bold;")
        else:
            self.lbl_alert.setStyleSheet("color: #E0E0E0;")


# ==============================================================================
# DetailChartDialog v2 — 크로스헤어 + 강화 마커
# ==============================================================================
class DetailChartDialog(QDialog):
    def __init__(self, bot, title_text, df):
        super().__init__()
        self.bot = bot
        self.setWindowTitle(f"[{bot.bot_id}] V8.0k 실시간 매매 대시보드 (3일치 1분봉)")
        self.resize(1400, 850)
        self.setStyleSheet("background-color: #0A0A0A; color: white;")
        
        main_layout = QVBoxLayout(self)
        
        # 상단: 봇 상태 패널
        self.info_panel = self._build_info_panel()
        main_layout.addWidget(self.info_panel)
        
        # 중간 + 하단 분할
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 차트
        pg.setConfigOptions(antialias=True)
        self.date_axis = pg.DateAxisItem(orientation='bottom')
        self.plot_widget = pg.PlotWidget(
            background='#050505',
            axisItems={'bottom': self.date_axis}
        )
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self.plot_widget.setLabel('left', 'Price (USD)')
        splitter.addWidget(self.plot_widget)
        
        # 거래 로그 테이블
        self.trade_table = self._build_trade_table()
        splitter.addWidget(self.trade_table)
        
        splitter.setSizes([550, 250])
        main_layout.addWidget(splitter)
        
        # 마커 (진입/청산)
        self.marker_items = pg.ScatterPlotItem(size=14, pxMode=True)
        self.plot_widget.addItem(self.marker_items)
        
        # 마커별 텍스트 (L1/L2/L3, S1/S2/S3) — 별도 TextItem 리스트
        self.marker_texts = []
        
        # ★ v2: 크로스헤어 설정
        self._setup_crosshair()
        
        self.refresh_chart(df)

    def _setup_crosshair(self):
        """크로스헤어 십자선 + 가격/시간 라벨."""
        # 수직선
        self.vline = pg.InfiniteLine(angle=90, movable=False,
                                      pen=pg.mkPen('#88C0D0', width=1, style=Qt.PenStyle.DashLine))
        # 수평선
        self.hline = pg.InfiniteLine(angle=0, movable=False,
                                      pen=pg.mkPen('#88C0D0', width=1, style=Qt.PenStyle.DashLine))
        self.plot_widget.addItem(self.vline, ignoreBounds=True)
        self.plot_widget.addItem(self.hline, ignoreBounds=True)
        
        # 가격 라벨 (좌측 상단)
        self.price_label = pg.TextItem(anchor=(0, 0.5),
                                        color='#EBCB8B',
                                        fill=pg.mkBrush(0, 0, 0, 200))
        self.price_label.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.plot_widget.addItem(self.price_label, ignoreBounds=True)
        
        # 시간 라벨 (하단)
        self.time_label = pg.TextItem(anchor=(0.5, 1.0),
                                       color='#EBCB8B',
                                       fill=pg.mkBrush(0, 0, 0, 200))
        self.time_label.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.plot_widget.addItem(self.time_label, ignoreBounds=True)
        
        # 마우스 이벤트 연결
        self.proxy = pg.SignalProxy(
            self.plot_widget.scene().sigMouseMoved,
            rateLimit=60,
            slot=self._on_mouse_moved
        )
    
    def _on_mouse_moved(self, evt):
        pos = evt[0]
        vb = self.plot_widget.getPlotItem().vb
        if self.plot_widget.sceneBoundingRect().contains(pos):
            mouse_point = vb.mapSceneToView(pos)
            x_ts = mouse_point.x()
            y_price = mouse_point.y()
            
            # 십자선 위치
            self.vline.setPos(x_ts)
            self.hline.setPos(y_price)
            
            # 가격 라벨 (좌측, y는 마우스 위치)
            x_range = vb.viewRange()[0]
            y_range = vb.viewRange()[1]
            self.price_label.setText(f" ${y_price:,.2f} ")
            self.price_label.setPos(x_range[0], y_price)
            
            # 시간 라벨 (하단, x는 마우스 위치)
            try:
                time_str = datetime.fromtimestamp(x_ts).strftime('%m/%d %H:%M')
            except (ValueError, OSError):
                time_str = "-"
            self.time_label.setText(f" {time_str} ")
            self.time_label.setPos(x_ts, y_range[0])

    def _build_info_panel(self):
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #1C2833;
                border: 1px solid #2B313F;
                border-radius: 6px;
                padding: 8px;
            }
            QLabel { color: #E0E0E0; font-size: 12px; }
        """)
        layout = QHBoxLayout(panel)
        
        left = QVBoxLayout()
        self.lbl_bot_status = QLabel("🤖 봇: -- | 상태: --")
        self.lbl_bot_status.setStyleSheet("font-size: 14px; font-weight: bold; color: #88C0D0;")
        self.lbl_modules = QLabel("R: -- / P: -- / E: --")
        self.lbl_position = QLabel("💼 포지션: -- | 진입가: -- | 레버리지: --")
        self.lbl_sltp = QLabel("🎯 SL: -- | TP: -- | 1R: --")
        left.addWidget(self.lbl_bot_status)
        left.addWidget(self.lbl_modules)
        left.addWidget(self.lbl_position)
        left.addWidget(self.lbl_sltp)
        layout.addLayout(left)
        
        mid = QVBoxLayout()
        self.lbl_acct_title = QLabel("💰 선물 계좌")
        self.lbl_acct_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #A3BE8C;")
        self.lbl_capital = QLabel("자본: $10,000.00")
        self.lbl_unrealized = QLabel("미실현 PnL: $+0.00")
        self.lbl_realized = QLabel("실현 PnL: $+0.00")
        self.lbl_wallet = QLabel("현물 지갑: $0.00")
        mid.addWidget(self.lbl_acct_title)
        mid.addWidget(self.lbl_capital)
        mid.addWidget(self.lbl_unrealized)
        mid.addWidget(self.lbl_realized)
        mid.addWidget(self.lbl_wallet)
        layout.addLayout(mid)
        
        right = QVBoxLayout()
        self.lbl_price = QLabel("💲 BTC: $0.00")
        self.lbl_price.setStyleSheet("font-size: 16px; font-weight: bold; color: #EBCB8B;")
        self.lbl_regime = QLabel("📊 장세: --")
        self.lbl_trade_count = QLabel("📈 총 거래: 0")
        right.addWidget(self.lbl_price)
        right.addWidget(self.lbl_regime)
        right.addWidget(self.lbl_trade_count)
        layout.addLayout(right)
        
        return panel

    def _build_trade_table(self):
        tbl = QTableWidget(0, 7)
        tbl.setStyleSheet("""
            QTableWidget {
                background-color: #1E222D;
                gridline-color: #2B313F;
                color: #E0E0E0;
            }
            QHeaderView::section {
                background-color: #121419;
                color: #8B94A5;
                padding: 6px;
                border: none;
                font-weight: bold;
            }
        """)
        tbl.setHorizontalHeaderLabels(["시각", "액션", "가격", "PnL", "환경", "레버리지", "사유"])
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tbl.verticalHeader().setVisible(False)
        return tbl

    def refresh_chart(self, df):
        if df is None or df.empty: return
        
        self.plot_widget.clear()
        # 크로스헤어 재추가
        self.plot_widget.addItem(self.vline, ignoreBounds=True)
        self.plot_widget.addItem(self.hline, ignoreBounds=True)
        self.plot_widget.addItem(self.price_label, ignoreBounds=True)
        self.plot_widget.addItem(self.time_label, ignoreBounds=True)
        self.plot_widget.addItem(self.marker_items)
        
        # 기존 텍스트 마커 제거
        for txt in self.marker_texts:
            self.plot_widget.removeItem(txt)
        self.marker_texts.clear()
        
        # 3일치 (4320봉) 캔들
        df_view = df.iloc[-4320:]
        data = []
        for _, row in df_view.iterrows():
            ts = row['timestamp'] if 'timestamp' in df.columns else row.name
            if isinstance(ts, (int, float)) and ts > 1e11:
                ts = ts / 1000.0
            elif hasattr(ts, 'timestamp'):
                ts = ts.timestamp()
            data.append((ts, row['open'], row['close'], row['low'], row['high']))
        
        item = CandlestickItem(data)
        self.plot_widget.addItem(item)
        
        # ★ v2: 마커 강화
        spots = []
        long_entry_idx = 0   # L1/L2/L3 카운터
        short_entry_idx = 0  # S1/S2/S3 카운터
        
        for trade in self.bot.trade_history[-100:]:
            ts = trade['time']
            price = trade['price']
            action = trade.get('action', '')
            
            if action == 'OPEN_LONG':
                long_entry_idx += 1
                spots.append({
                    'pos': (ts, price), 'symbol': 't1',  # 위쪽 삼각형
                    'brush': pg.mkBrush('#00FF41'),
                    'pen': pg.mkPen('w', width=1),
                    'size': 18
                })
                # L1/L2/L3 텍스트
                txt = pg.TextItem(text=f"L{long_entry_idx}",
                                   color='#00FF41', anchor=(0.5, 1.5))
                txt.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
                txt.setPos(ts, price)
                self.plot_widget.addItem(txt)
                self.marker_texts.append(txt)
                
            elif action == 'OPEN_SHORT':
                short_entry_idx += 1
                spots.append({
                    'pos': (ts, price), 'symbol': 't',  # 아래쪽 삼각형
                    'brush': pg.mkBrush('#FF3131'),
                    'pen': pg.mkPen('w', width=1),
                    'size': 18
                })
                txt = pg.TextItem(text=f"S{short_entry_idx}",
                                   color='#FF3131', anchor=(0.5, -0.5))
                txt.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
                txt.setPos(ts, price)
                self.plot_widget.addItem(txt)
                self.marker_texts.append(txt)
                
            elif action in ['CLOSE_ALL', 'CLOSE_HALF']:
                pnl = trade.get('pnl', 0)
                side_was = trade.get('side_was', 'LONG')  # 청산 직전 방향
                is_profit = pnl > 0
                
                # 색상: side에 따라 (LONG=녹색, SHORT=적색)
                color = '#00FF41' if side_was == 'LONG' else '#FF3131'
                
                # 마커: 익절=○ (o), 손절=✕ (x)
                # 추가로 반익절은 다이아몬드로 구분
                if action == 'CLOSE_HALF':
                    symbol = 'd'  # 다이아몬드 (반익절)
                else:
                    symbol = 'o' if is_profit else 'x'
                
                spots.append({
                    'pos': (ts, price), 'symbol': symbol,
                    'brush': pg.mkBrush(color),
                    'pen': pg.mkPen(color, width=2),
                    'size': 16
                })
        
        self.marker_items.setData(spots=spots)
        self._refresh_trade_table()

    def _refresh_trade_table(self):
        recent = self.bot.trade_history[-30:][::-1]
        self.trade_table.setRowCount(len(recent))
        
        for r, t in enumerate(recent):
            ts_str = datetime.fromtimestamp(t['time']).strftime('%m/%d %H:%M:%S')
            action = t.get('action', '')
            price = t.get('price', 0)
            pnl = t.get('pnl', None)
            env = t.get('env', '-')
            lev = t.get('leverage', '-')
            reason = t.get('reason', '')[:60]
            
            cells = [
                ts_str, action, f"${price:,.2f}",
                f"${pnl:+,.2f}" if pnl is not None else "-",
                env, str(lev), reason
            ]
            for c, val in enumerate(cells):
                item = QTableWidgetItem(val)
                if c == 1:
                    if 'LONG' in action:
                        item.setForeground(QColor('#00FF41'))
                    elif 'SHORT' in action:
                        item.setForeground(QColor('#FF3131'))
                    elif 'CLOSE' in action:
                        item.setForeground(QColor('#EBCB8B'))
                if c == 3 and pnl is not None:
                    item.setForeground(QColor('#00FF41' if pnl >= 0 else '#FF3131'))
                self.trade_table.setItem(r, c, item)

    def update_realtime(self, price, bot, regime_str=""):
        state_map = ["대기", "실행 중", "익손절 처리 중", "강제종료/잠금"]
        state_color = ["#8B94A5", "#A3BE8C", "#EBCB8B", "#BF616A"]
        cur_state = state_map[bot.state.value] if hasattr(bot, 'state') else "N/A"
        cur_color = state_color[bot.state.value] if hasattr(bot, 'state') else "#FFFFFF"
        
        self.lbl_bot_status.setText(f"🤖 봇: {bot.bot_id} | 상태: {cur_state}")
        self.lbl_bot_status.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {cur_color};")
        
        r_mod = bot.modules.get('regime', '-') or '-'
        p_mod = bot.modules.get('predict', '-') or '-'
        e_mod = bot.modules.get('execute', '-') or '-'
        r_short = r_mod.replace('R_ML_V80k_', '') if r_mod else '-'
        p_short = p_mod.replace('P_ML_V80k_', '') if p_mod else '-'
        e_short = e_mod.replace('E_ML_V80k_', '') if e_mod else '-'
        self.lbl_modules.setText(f"R: {r_short} / P: {p_short} / E: {e_short}")
        
        side = bot.position.get('side', 'WAIT')
        side_color = '#00FF41' if side == 'LONG' else ('#FF3131' if side == 'SHORT' else '#8B94A5')
        entry = bot.position.get('entry_price', 0)
        lev = bot.position.get('leverage', 1)
        pos_str = f"💼 포지션: <span style='color:{side_color};'>{side}</span> | 진입가: ${entry:,.2f} | 레버리지: {lev}x"
        self.lbl_position.setText(pos_str)
        self.lbl_position.setTextFormat(Qt.TextFormat.RichText)
        
        sl = bot.position.get('sl_price', 0)
        tp = bot.position.get('tp_price', 0)
        one_r = bot.position.get('one_r_dist', 0)
        self.lbl_sltp.setText(f"🎯 SL: ${sl:,.2f} | TP: ${tp:,.2f} | 1R: ${one_r:,.2f}")
        
        capital = getattr(bot, 'capital', 10000.0)
        unr = getattr(bot, 'unrealized_pnl', 0.0)
        rea = getattr(bot, 'realized_pnl', 0.0)
        wal = getattr(bot, 'wallet_balance', 0.0)
        
        self.lbl_capital.setText(f"자본: ${capital:,.2f}")
        unr_color = '#00FF41' if unr >= 0 else '#FF3131'
        self.lbl_unrealized.setText(f"미실현 PnL: <span style='color:{unr_color};'>${unr:+,.2f}</span>")
        self.lbl_unrealized.setTextFormat(Qt.TextFormat.RichText)
        rea_color = '#00FF41' if rea >= 0 else '#FF3131'
        self.lbl_realized.setText(f"실현 PnL: <span style='color:{rea_color};'>${rea:+,.2f}</span>")
        self.lbl_realized.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_wallet.setText(f"현물 지갑: ${wal:,.2f}")
        
        self.lbl_price.setText(f"💲 BTC: ${price:,.2f}")
        self.lbl_regime.setText(f"📊 장세: {regime_str if regime_str else getattr(bot, 'current_regime', '-')}")
        
        n = len(bot.trade_history)
        self.lbl_trade_count.setText(f"📈 총 거래: {n}회")


def get_step_style(step_val):
    styles = {
        0: ("대기", "#2B313F", "#FFFFFF"),
        1: ("실행", "#104221", "#FFFFFF"),
        2: ("익손절중", "#8C5B00", "#FFFFFF"),
        3: ("강제종료", "#6A1818", "#FFFFFF")
    }
    return styles.get(step_val, ("오류", "#000000", "#FFFFFF"))
