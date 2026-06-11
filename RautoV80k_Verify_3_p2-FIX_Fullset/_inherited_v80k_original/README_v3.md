# V80k v3 응급 패치 — Silent Crash 방지

## 발생한 문제 (v1/v2 공통)

콘솔에 다음만 찍히고 프로세스 죽음:
```
✅ Regime v6 로드 완료
C:\Rauto>     ← 여기서 죽음
```

**증상**: 가격/장세 고정, 부하 0%, GUI 좀비 상태.
**원인**: try-except 부족 → R 모듈 첫 추론 중 silent crash → 스레드 종료.

## v3 응급 패치 5가지

1. **TradingEngine while 루프 전체 try-except** — 어떤 에러도 스레드 안 죽임
2. **봇별 try-except** — 한 봇 에러가 다른 봇에 영향 안 줌
3. **글로벌 예외 후크** — 처리 안 된 예외도 콘솔에 풀 traceback 표시
4. **단계별 print** — 어디서 죽었는지 실시간으로 보임
5. **WebSocket 갱신 모니터링** — 30초 이상 멈추면 콘솔에 경고
6. **CRASH.log 자동 생성** — 죽으면 traceback이 파일로 저장
7. **콘솔 자동 닫힘 방지** — 에러 시 "[엔터를 눌러 종료]" 대기

## v3 실행 방법

**기존 C:\Rauto 폴더 비우고 새 ZIP 풀기**:

```cmd
cd C:\Rauto
del /Q *.py *.json *.docx *.md *.csv *.log
[ZIP 압축 풀기]
python RautoV80k_ChampionGUI.py
```

또는 옛 명명 호환:
```cmd
python V80k_ChampionGUI.py
```

## 콘솔 출력으로 진단법

새 v3는 다음을 출력해야 정상:
```
[V80k v3] 시작 PID=...
[V80k v3] ✅ 필수 파일 13개 모두 확인됨
[V80k v3] PyQt6 QApplication 생성 완료
[V80k v3] GUI 생성 완료
[V80k v3] GUI 표시 완료. 이벤트 루프 진입
[Engine v3] 메인 루프 시작
[RautoV80k_DataEngine] 🔄 과거 데이터 예열 중...
[RautoV80k_DataEngine] ✅ 예열 완료 (총 4500봉)
[Engine v3] 🔔 새 봉 도착 $... (loop ...)
```

**콘솔에 `[V80k v3]` 또는 `[Engine v3]`가 안 보이면 옛 코드 돌고 있는 것.**

## 봇 1번 시작 시 정상 출력

```
[Engine v3] [Bot_1] 모듈 이식 완료
[Engine v3] [Bot_1] → RUNNING
[R_ML_V80k] 첫 추론 시작 — df 크기 4500봉, 4500봉 피처 산출 중 (10~60초 소요)
[R_ML_V80k] compute_features 시작...
[R_ML_V80k] compute_features 완료 (X.X초)
[R_ML_V80k] ✅ 첫 추론 완료 — pred=BULL/BEAR/CHOP conf=0.XXXX
```

## 죽으면 다음 중 하나가 보임

**A. R 모듈에서 죽음**:
```
[R_ML_V80k] ❌ 피처 산출 오류:
Traceback (most recent call last):
  ...
```

**B. 메인 루프에서 죽음**:
```
[Engine v3] 🚨 메인 루프 에러 #1: ...
Traceback ...
```

**C. 글로벌 미처리 예외**:
```
🚨 [V80k v3] 처리되지 않은 예외 발생 — 시스템 정지
Traceback ...
[엔터를 눌러 종료] >>>
```

콘솔 안 닫히고 대기. 선장이 캡처하거나 traceback을 복사해서 알려달라.

## CRASH.log 확인

죽으면 `RautoV80k_CRASH.log`가 생성됨:
```cmd
notepad RautoV80k_CRASH.log
```

여기에 정확한 에러 위치 + 줄번호 + 원인 모두 기록.
