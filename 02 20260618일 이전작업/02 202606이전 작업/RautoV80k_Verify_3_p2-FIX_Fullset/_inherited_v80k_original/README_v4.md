# V80k v4 — WebSocket SUBSCRIBE 패치

## 진단 확정

테스트 결과로 정확한 원인 발견:
```
연결 성공                              ← TCP/TLS OK
TimeoutError: read operation timed out   ← 데이터 안 옴
```
대비:
```
ws.send(SUBSCRIBE 메시지)
RECV: {"result":null,"id":1}             ← 정상 응답!
```

**바이낸스가 URL 자동구독 deprecate**. 명시적 SUBSCRIBE JSON 송신 필수.

## v4 핵심 변경 — DataEngine

| 항목 | v3 (실패) | v4 (수정) |
|---|---|---|
| URL | `wss://fstream.binance.com/ws/btcusdt@kline_1m` | `wss://fstream.binance.com/ws` |
| 구독 | 없음 (자동 가정) | **`on_open`에서 SUBSCRIBE JSON 송신** |
| ping | 없음 | 60초 ping (연결 유지) |
| 응답 처리 | kline만 가정 | `{"result":null,"id":1}` 응답도 처리 |

## 정상 작동 시 콘솔 출력

```
[RautoV80k_DataEngine] 🔄 과거 데이터 예열 중... (BTCUSDT, 4500봉)
[RautoV80k_DataEngine]   페이지 1/3: 1500봉
[RautoV80k_DataEngine]   페이지 2/3: 1500봉
[RautoV80k_DataEngine]   페이지 3/3: 1500봉
[RautoV80k_DataEngine] ✅ 예열 완료 (총 4500봉)
[Engine v3] 메인 루프 시작
[RautoV80k_DataEngine] 🔗 WS 연결 성공 — SUBSCRIBE 송신: btcusdt@kline_1m   ← v4 신규
[RautoV80k_DataEngine] ✅ 구독 요청 전송 완료 — 데이터 수신 대기              ← v4 신규
[RautoV80k_DataEngine] ✅ 구독 응답 수신: id=1 (이제 데이터 시작)            ← v4 신규
[Engine v3] 🔔 새 봉 도착 $XXXXX.XX (loop ...)                              ← 가격 변화!
```

**핵심 차이**: v3은 `🔗 WS 연결 성공` 메시지가 안 떴음. v4는 떠야 정상.

## PC 사용

```cmd
1. C:\Rauto의 .py/.json/.docx/.md 파일 모두 삭제
2. ZIP 풀어 V80k_v4_subfix 폴더 안 21개 파일을 C:\Rauto에 복사
3. cd C:\Rauto
4. python RautoV80k_ChampionGUI.py
   (또는 옛 명명: python V80k_ChampionGUI.py)
```

## 봇 1번 시작 시 정상 출력

```
[V80k v3] 시작 PID=...
[V80k v3] ✅ 필수 파일 13개 모두 확인됨
[V80k v3] PyQt6 QApplication 생성 완료
[V80k v3] GUI 표시 완료. 이벤트 루프 진입
[Engine v3] 메인 루프 시작
[RautoV80k_DataEngine] 🔗 WS 연결 성공 — SUBSCRIBE 송신: btcusdt@kline_1m
[RautoV80k_DataEngine] ✅ 구독 응답 수신: id=1 (이제 데이터 시작)
[Engine v3] 🔔 새 봉 도착 $XXXXX.XX (loop 30)        ← 1분 안에 첫 봉
```

이후 1분마다 `🔔 새 봉 도착` 출력 + 가격 갱신.

봇 1번 활성화 후:
```
[Engine v3] [Bot_1] 모듈 이식 완료
[Engine v3] [Bot_1] → RUNNING
[R_ML_V80k] 첫 추론 시작 — df 크기 4500봉
[R_ML_V80k] compute_features 완료 (X.X초)
[R_ML_V80k] ✅ 첫 추론 완료 — pred=BULL/BEAR/CHOP conf=0.XXXX
```

## 봉 마감마다 자취

매 봉 마감 시 `RautoV80k_BotState_Bot_1.csv`에 1줄씩 기록:
- regime conf 변화 추적
- TBM action / conf 추적
- price/capital/PnL 변화

**0.44 → 0.43 → 0.46 식으로 conf 변하면 정상**.

## 빠른 검증 (PC에서 1분)

새 v4 풀고 다음 1줄로 확인:
```cmd
cd C:\Rauto
python -c "import websocket, json; ws=websocket.create_connection('wss://fstream.binance.com/ws'); ws.send(json.dumps({'method':'SUBSCRIBE','params':['btcusdt@kline_1m'],'id':1})); print(ws.recv()); print(ws.recv())"
```

응답:
```
{"result":null,"id":1}
{"e":"kline","E":...}      ← kline 데이터! 받으면 v4 코드도 작동 보장
```
