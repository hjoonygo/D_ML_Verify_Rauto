# [파일명] api_server.py
# 코드길이: 약 95줄 / 내부버전: api_server_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 헤드리스 엔진(EngineService)을 얇은 REST API로 노출(의존성 0, stdlib http.server).
#        PC GUI·향후 안드로이드가 이 API로 붙는다(엔진을 클라이언트가 직접 생성하지 않음).
#        ※ 1차는 REST 폴링. WS 실시간 푸시는 라이브 단계에서 추가.
# [엔드포인트] GET /status /slots /account /champion /scores
#             POST /load{slot,module} /unload{slot} /run /kill /reset
# [Lookahead] 해당 없음(엔진 상태 중계).
# ── 사용 파일 ── engine_service.py(EngineService)
# ── 함수 In/Out ──
#  make_handler(engine)   In: 엔진 → Out: 요청핸들러 클래스
#  start_server(engine,host,port) In: 엔진·호스트·포트(0=자동) → Out: (server, 실제포트)  ※ 데몬스레드 서빙
#  stop_server(server)    In: server → Out: 종료
# ── 상수 ── 없음
# ─────────────────────────────────────────────────────────────────────────
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def make_handler(engine):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return  # 조용히

        def _send(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self):
            n = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(n) if n > 0 else b'{}'
            return json.loads(raw or b'{}')

        def do_GET(self):
            routes = {'/status': engine.get_status, '/slots': engine.list_slots,
                      '/account': engine.get_account, '/champion': engine.get_champion,
                      '/scores': engine.get_scores}
            fn = routes.get(self.path)
            if fn is None:
                return self._send({'error': 'not found', 'path': self.path}, 404)
            try:
                self._send(fn())
            except Exception as e:
                self._send({'error': str(e)}, 500)

        def do_POST(self):
            try:
                if self.path == '/load':
                    d = self._read_json()
                    self._send(engine.load_bot(d['slot'], d['module'], d.get('class_name')))
                elif self.path == '/unload':
                    d = self._read_json()
                    self._send({'unloaded': engine.unload_bot(d['slot'])})
                elif self.path == '/run':
                    self._send(engine.run_replay())
                elif self.path == '/kill':
                    self._send(engine.trip_kill())
                elif self.path == '/reset':
                    self._send(engine.reset_safety())
                else:
                    self._send({'error': 'not found', 'path': self.path}, 404)
            except Exception as e:
                self._send({'error': str(e)}, 500)

    return Handler


def start_server(engine, host='127.0.0.1', port=0):
    srv = ThreadingHTTPServer((host, port), make_handler(engine))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, srv.server_address[1]


def stop_server(srv):
    srv.shutdown()
    srv.server_close()
