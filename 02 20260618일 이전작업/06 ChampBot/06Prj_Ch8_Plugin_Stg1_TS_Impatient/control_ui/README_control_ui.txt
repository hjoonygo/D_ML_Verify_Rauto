Rauto 안드로이드 제어 UI — control_ui/  (2026-06-15, 06Prj_Ch8)
================================================================
[구성]
 control_dashboard.html  : 폰/브라우저 대시보드. ★실제 트레이딩뷰 라이브 차트(BINANCE:BTCUSDT.P)
                           + 총자산·합산노출·MDD + Risk Guard 상태 + 8슬롯 실시간 + 긴급버튼.
                           5초 폴링으로 /state.json 갱신. KILL/일시정지/슬롯청산 버튼 → /cmd POST.
 control_server.py       : 표준라이브러리만(의존성 0). 대시보드 서빙 + /state.json 중계 + /cmd 플래그 기록.
 state_example.json      : 상태파일 예시(스키마 참고).

[실행]
 1) 봇 배치가 매 사이클 끝에 현재 8슬롯 상태를 JSON으로 쓰게 한다(스키마=state_example.json).
    환경변수 RAUTO_STATE_JSON 로 그 파일 경로 지정.
 2) python control_server.py   (기본 0.0.0.0:8787)
 3) 폰 브라우저로 http://<PC또는AWS_IP>:8787  접속.

[제어 흐름]  대시보드 버튼 → /cmd?action=killall|pause|resume|flat&slot= (POST)
   → control_server가 FLAG_DIR(기본 C:\BinanceData)에 kill.flag / pause.flag / flat_<slot>.flag 기록
   → 봇의 Risk Guard / kill_guard(분당 태스크)가 그 플래그를 읽어 실제 시장가 청산·정지 수행.
   (이미 Rauto에 kill.flag 메커니즘 존재 — 그 위에 얹음.)

[★보안 — 반드시]
 · localhost 또는 Tailscale/VPN 내부에서만 노출. 공인 인터넷 직접노출 금지.
 · 실거래 전환 시: /cmd에 토큰/비밀번호 인증 추가, HTTPS, IP 화이트리스트.
 · 이 UI는 '모니터+보조제어'. 1차 방어는 봇 내부 Risk Guard(사람 없이도 자동), 2차는 텔레그램.
   웹 UI가 죽어도 텔레그램(/killall)·봇 자동가드는 독립 동작해야 한다(단일점 장애 금지).

[한계 / TODO]
 · 트레이딩뷰 무료 임베드는 '봇의 진입/청산 마커'를 차트에 직접 못 찍음(차팅 라이브러리=유료).
   대안: 본 대시보드에 캔들+마커를 자체 canvas로 그리기(목업 참고) 또는 TradingView Charting Library 도입.
 · 실시간 가격은 트레이딩뷰가 표시. 봇 체결가/슬리피지는 /state.json 수치로 병기.
================================================================
