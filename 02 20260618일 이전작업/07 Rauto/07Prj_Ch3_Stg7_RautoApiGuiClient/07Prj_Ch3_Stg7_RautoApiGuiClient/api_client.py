# [파일명] api_client.py
# 코드길이: 약 70줄 / 내부버전: api_client_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 엔진 REST API를 호출하는 얇은 클라이언트(의존성 0, stdlib urllib).
#        PC PyQt6 GUI와 향후 안드로이드가 '같은' API에 이 방식으로 붙는다.
# [Lookahead] 해당 없음.
# ── 사용 파일 ── 없음(서버 api_server.py와 엔드포인트 규약 공유)
# ── 함수 In/Out ──
#  RautoAPIClient(base_url)   In: 엔진 주소 → Out: 클라이언트
#   .get_status()/list_slots()/get_account()/get_champion()/get_scores()  In: - → Out: dict(JSON)
#   .load_bot(slot,module,class_name)  In: 슬롯·모듈 → Out: META
#   .unload_bot(slot)/run_replay()/trip_kill()/reset_safety()  In: - → Out: dict
# ── 상수 ── 없음
# ─────────────────────────────────────────────────────────────────────────
import json
import urllib.request


class RautoAPIClient:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base = base_url.rstrip('/')
        self.timeout = timeout

    def _get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=self.timeout) as r:
            return json.loads(r.read().decode('utf-8'))

    def _post(self, path, payload=None):
        data = json.dumps(payload or {}).encode('utf-8')
        req = urllib.request.Request(self.base + path, data=data,
                                     headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode('utf-8'))

    def get_status(self):
        return self._get('/status')

    def list_slots(self):
        return self._get('/slots')

    def get_account(self):
        return self._get('/account')

    def get_champion(self):
        return self._get('/champion')

    def get_scores(self):
        return self._get('/scores')

    def load_bot(self, slot, module, class_name=None):
        return self._post('/load', {'slot': slot, 'module': module, 'class_name': class_name})

    def unload_bot(self, slot):
        return self._post('/unload', {'slot': slot})

    def run_replay(self):
        return self._post('/run')

    def trip_kill(self):
        return self._post('/kill')

    def reset_safety(self):
        return self._post('/reset')
