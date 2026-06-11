# [파일명] rauto_ingest.py
# 코드길이: 약 210줄 / 내부버전: rauto_ingest_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 라이브 데이터 수집 서비스(헤드리스). Binance 선물 WS(@kline_1m·@forceOrder·@depth·@aggTrade)
#        를 받아 정규화→아카이브하고, OI·롱숏비율은 REST로 폴링한다. 호가는 OrderBook으로 유지하며
#        갭 감지 시 재동기화(스냅샷 재요청). BTCUSDT 1분봉이 봇의 기본피드, 나머지는 백업.
# [중요] 컨테이너는 Binance 접근이 막혀 실접속 불가 → 본 모듈의 '로직'(정규화/시퀀스/아카이브/폴링)은
#        모의 피드로 검증하고, 실제 WS/REST 접속(start_live)은 PC/AWS에서 검증한다.
#        WS 라우팅은 handle_raw()로 분리되어 소켓 없이도 주입 테스트 가능.
# [경고] WS 라우팅 경로(2026-04-23 이후 /public 등)·정확한 URL은 라이브 전 Binance 문서로 확인할 것.
# [Lookahead] 해당 없음(실시간 수집).
# ── 사용 파일 ── rauto_orderbook.py(OrderBook) / rauto_archiver.py(Archiver)
#                 (옵션) websocket-client: 실접속(start_live) 시에만 필요
# ── 함수 In/Out ──
#  normalize_kline/force/trade/depth/oi/lsr(data)  In: Binance data → Out: 평탄 record dict
#  RestPoller(archiver,fetch_oi,fetch_lsr,...)  .poll_oi_once()/.poll_lsr_once()/.run(stop)
#  WSIngestor(service,base,symbol)  .url() / .handle_raw(raw) / .route(msg) / .start_live()
#  IngestService(root,retention_days)
#    .on_kline/on_force/on_trade/on_depth(data)  수집·정규화·아카이브(+호가)
#    .set_book_snapshot(snap) / .feed_mock(raws) / .flush_archive() / .status()
#    .start_live(fetch_snapshot,fetch_oi,fetch_lsr)  실접속(PC/AWS)
# ── 상수 ── WS_BASE / STREAMS / 폴링주기
# ─────────────────────────────────────────────────────────────────────────
import json
import threading
import time
from rauto_orderbook import OrderBook
from rauto_archiver import Archiver

WS_BASE = "wss://fstream.binance.com/stream"   # ⚠️ 라이브 전 라우팅 경로 확인(/public 등)
SYMBOL = "btcusdt"
STREAMS = [f"{SYMBOL}@kline_1m", f"{SYMBOL}@forceOrder", f"{SYMBOL}@depth", f"{SYMBOL}@aggTrade"]


# ---------- 정규화 (Binance data → 평탄 record) ----------
def normalize_kline(data):
    k = data['k']
    return {"ts_open": int(k['t']), "ts_close": int(k['T']), "o": float(k['o']), "h": float(k['h']),
            "l": float(k['l']), "c": float(k['c']), "v": float(k['v']), "closed": bool(k['x'])}


def normalize_force(data):
    o = data['o']
    return {"ts": int(o['T']), "side": o['S'], "qty": float(o['q']), "price": float(o['p']),
            "avg_price": float(o.get('ap', o['p']))}


def normalize_trade(data):
    return {"ts": int(data['T']), "price": float(data['p']), "qty": float(data['q']),
            "is_buyer_maker": bool(data['m'])}


def normalize_depth(data):
    return {"ts_event": int(data.get('E', 0)), "ts_tx": int(data.get('T', 0)),
            "U": int(data['U']), "u": int(data['u']),
            "pu": int(data['pu']) if data.get('pu') is not None else None,
            "n_bids": len(data.get('b', [])), "n_asks": len(data.get('a', []))}


def normalize_oi(rec):
    return {"ts": int(rec.get('time', 0)), "symbol": rec.get('symbol', SYMBOL.upper()),
            "open_interest": float(rec['openInterest'])}


def normalize_lsr(rec):
    return {"ts": int(rec.get('timestamp', 0)), "symbol": rec.get('symbol', SYMBOL.upper()),
            "long_short_ratio": float(rec['longShortRatio']),
            "long_account": float(rec.get('longAccount', 'nan')) if rec.get('longAccount') else None,
            "short_account": float(rec.get('shortAccount', 'nan')) if rec.get('shortAccount') else None}


# ---------- REST 폴링 (OI/롱숏비율) ----------
class RestPoller:
    def __init__(self, archiver, fetch_oi, fetch_lsr, oi_interval=6.0, lsr_interval=300.0):
        self.archiver = archiver
        self.fetch_oi = fetch_oi
        self.fetch_lsr = fetch_lsr
        self.oi_interval = oi_interval
        self.lsr_interval = lsr_interval
        self.n_oi = 0
        self.n_lsr = 0

    def poll_oi_once(self):
        self.archiver.add('oi', normalize_oi(self.fetch_oi()))
        self.n_oi += 1

    def poll_lsr_once(self):
        self.archiver.add('lsr', normalize_lsr(self.fetch_lsr()))
        self.n_lsr += 1

    def run(self, stop_event):          # 라이브 루프(PC/AWS)
        next_oi = next_lsr = 0.0
        while not stop_event.is_set():
            now = time.time()
            if now >= next_oi:
                try:
                    self.poll_oi_once()
                except Exception:
                    pass
                next_oi = now + self.oi_interval
            if now >= next_lsr:
                try:
                    self.poll_lsr_once()
                except Exception:
                    pass
                next_lsr = now + self.lsr_interval
            stop_event.wait(0.5)


# ---------- WS 수집 ----------
class WSIngestor:
    def __init__(self, service, base=WS_BASE, symbol=SYMBOL):
        self.service = service
        self.base = base
        self.symbol = symbol
        self.streams = [f"{symbol}@kline_1m", f"{symbol}@forceOrder", f"{symbol}@depth", f"{symbol}@aggTrade"]
        self.n_msg = 0

    def url(self):
        return f"{self.base}?streams={'/'.join(self.streams)}"

    def route(self, msg: dict):
        stream = msg.get('stream', '')
        data = msg.get('data', msg)
        self.n_msg += 1
        if '@kline' in stream:
            self.service.on_kline(data)
        elif '@forceOrder' in stream:
            self.service.on_force(data)
        elif '@depth' in stream:
            self.service.on_depth(data)
        elif '@aggTrade' in stream:
            self.service.on_trade(data)

    def handle_raw(self, raw: str):     # 주입/테스트 경로(소켓 없이)
        self.route(json.loads(raw))

    def start_live(self, on_open=None):  # 실접속(PC/AWS) — 컨테이너 차단
        import websocket  # websocket-client
        def _on_message(ws, message):
            try:
                self.route(json.loads(message))
            except Exception:
                pass
        app = websocket.WebSocketApp(self.url(), on_message=_on_message,
                                     on_open=on_open or (lambda ws: None))
        # 서버 ping 3분/응답 10분 → keepalive + 자동 재접속
        app.run_forever(ping_interval=180, ping_timeout=30, reconnect=5)
        return app


# ---------- 수집 서비스 ----------
class IngestService:
    def __init__(self, archive_root, retention_days=7):
        self.book = OrderBook()
        self.archiver = Archiver(archive_root, retention_days)
        self.ws = WSIngestor(self)
        self.counts = {"kline_1m": 0, "liquidation": 0, "agg_trade": 0, "depth": 0}
        self.resyncs = 0
        self._fetch_snapshot = None

    def on_kline(self, data):
        self.archiver.add('kline_1m', normalize_kline(data)); self.counts["kline_1m"] += 1

    def on_force(self, data):
        self.archiver.add('liquidation', normalize_force(data)); self.counts["liquidation"] += 1

    def on_trade(self, data):
        self.archiver.add('agg_trade', normalize_trade(data)); self.counts["agg_trade"] += 1

    def on_depth(self, data):
        st = self.book.apply_diff(data)
        self.archiver.add('depth', normalize_depth(data)); self.counts["depth"] += 1
        if st == 'gap':
            self.resyncs += 1
            if self._fetch_snapshot is not None:     # 라이브: 스냅샷 재요청
                try:
                    self.set_book_snapshot(self._fetch_snapshot())
                except Exception:
                    pass
        return st

    def set_book_snapshot(self, snap):
        self.book.set_snapshot(snap)

    def feed_mock(self, raws):
        for raw in raws:
            self.ws.handle_raw(raw)

    def flush_archive(self):
        return self.archiver.flush()

    def status(self):
        return {"counts": dict(self.counts), "resyncs": self.resyncs,
                "book": self.book.status(), "ws_url": self.ws.url(),
                "archive": self.archiver.stats()}

    def start_live(self, fetch_snapshot, fetch_oi, fetch_lsr):  # PC/AWS
        self._fetch_snapshot = fetch_snapshot
        stop = threading.Event()
        poller = RestPoller(self.archiver, fetch_oi, fetch_lsr)
        threading.Thread(target=poller.run, args=(stop,), daemon=True).start()
        self.set_book_snapshot(fetch_snapshot())
        self.ws.start_live()
        return stop
