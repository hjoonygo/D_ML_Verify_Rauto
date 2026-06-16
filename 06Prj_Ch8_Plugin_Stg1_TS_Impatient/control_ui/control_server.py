# -*- coding: utf-8 -*-
# [control_server.py] Rauto 제어 대시보드 미니 서버 (표준 라이브러리만, 의존성 0).
#   역할: ① control_dashboard.html 서빙 ② /state.json 제공(봇이 쓴 상태파일 중계)
#         ③ POST /cmd?action=killall|pause|resume|flat&slot= → 플래그 파일 기록(봇 Guard가 읽음)
#   ★보안(필수): localhost 또는 Tailscale/VPN 내부에서만 노출. 공인망 직접노출 금지(토큰 추가 전엔).
#   실행: python control_server.py   (기본 0.0.0.0:8787) → 폰 브라우저로 http://<PC_IP>:8787
import http.server, socketserver, json, os, glob, urllib.parse, datetime, threading, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
# 봇이 매 배치 끝에 쓰는 상태파일(없으면 예시 사용). RAUTO_DIR 환경변수 우선.
STATE_SRC = os.environ.get("RAUTO_STATE_JSON", os.path.join(HERE, "state_example.json"))
# 슬롯 합치기: 여러 봇(C:\Rauto1,2,..)의 state.json을 한 화면으로 병합. 매칭 0개면 STATE_SRC(단일/데모)로 폴백.
STATE_GLOB = os.environ.get("RAUTO_STATE_GLOB", r"C:\Rauto*\state.json")
FLAG_DIR = os.environ.get("RAUTO_FLAG_DIR", os.environ.get("RAUTO_DAUTO_DIR", r"C:\BinanceData"))
PORT = int(os.environ.get("RAUTO_CTRL_PORT", "8787"))
# git auto-pull: RAUTO_GIT_PULL=1 + RAUTO_REPO=클론경로 → 서버가 180초마다 git pull(대시보드 자동갱신, RDP 불요)
REPO = os.environ.get("RAUTO_REPO", "")


def _git_pull_loop():
    while True:
        time.sleep(180)
        try:
            subprocess.run(["git", "-C", REPO, "pull", "--ff-only"], capture_output=True, timeout=60)
        except Exception:
            pass


def aggregate_state():
    """C:\\Rauto*\\state.json 전부 읽어 slots 병합. 상위필드는 가장 신선한(데이터 끊김 적은) 봇 기준."""
    parts = []
    for fp in sorted(glob.glob(STATE_GLOB)):
        try:
            parts.append(json.load(open(fp, encoding="utf-8")))
        except Exception:
            pass
    if not parts:                                   # 매칭 0개 → 단일/데모 폴백
        try:
            return open(STATE_SRC, encoding="utf-8").read()
        except Exception:
            return json.dumps({"error": "no state", "slots": []})
    slots = []
    for d in parts:
        slots.extend(d.get("slots", []))
    fresh = min(parts, key=lambda d: d.get("dauto_stale_min", 1e9))   # 가장 최근 데이터 봇
    merged = dict(fresh)                              # 상위필드 기본 = 신선한 봇
    merged["slots"] = slots
    merged["dauto_ok"] = bool(fresh.get("dauto_ok", False))           # 데이터 흐름 = 최신봇 기준
    merged["live"] = any(d.get("live", False) for d in parts)         # 하나라도 실거래면 live
    ups = [d.get("updated") for d in parts if d.get("updated")]
    if ups:
        merged["updated"] = max(ups)
    return json.dumps(merged, ensure_ascii=False)
# champ_stop_graceful = 챔피언 현재 거래 정상종료 후 실계좌 자격취소 / champ_stop_force = 즉시 시장가 청산 후 자격취소
# resume = 긴급해제 → 챔피언 자동지정·매매재개 (실거래 미연결 시 가상만)
ALLOWED = {"killall", "pause", "resume", "flat", "champ_stop_graceful", "champ_stop_force"}


class H(http.server.SimpleHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path in ("/", "/index.html", "/control_dashboard.html"):
            fp = os.path.join(HERE, "control_dashboard.html")
            return self._send(200, open(fp, "rb").read(), "text/html; charset=utf-8")
        if p.path.startswith("/state.json"):
            return self._send(200, aggregate_state())
        # ── PWA 정적자산(앱 설치용) ──
        STATIC = {"/manifest.json": "application/manifest+json",
                  "/sw.js": "application/javascript",
                  "/icon-192.png": "image/png", "/icon-512.png": "image/png"}
        if p.path in STATIC:
            fp = os.path.join(HERE, p.path.lstrip("/"))
            if os.path.exists(fp):
                return self._send(200, open(fp, "rb").read(), STATIC[p.path])
        return self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        p = urllib.parse.urlparse(self.path)
        if p.path != "/cmd":
            return self._send(404, json.dumps({"error": "not found"}))
        q = urllib.parse.parse_qs(p.query)
        action = (q.get("action", [""])[0]).lower()
        slot = q.get("slot", [""])[0]
        if action not in ALLOWED:
            return self._send(400, json.dumps({"error": "bad action"}))
        # 플래그 파일 기록 — 봇 Guard/kill_guard가 이 파일을 읽어 실제 청산/정지 수행
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        fname = {"killall": "kill.flag", "pause": "pause.flag",
                 "resume": "resume.flag", "flat": f"flat_{slot}.flag",
                 "champ_stop_graceful": "champ_stop_graceful.flag",
                 "champ_stop_force": "champ_stop_force.flag"}[action]
        os.makedirs(FLAG_DIR, exist_ok=True)
        with open(os.path.join(FLAG_DIR, fname), "w", encoding="utf-8") as f:
            f.write(f"{action} {slot} | requested {ts} via control_server\n")
        print(f"[CMD] {action} {slot} -> {fname} @ {FLAG_DIR}")
        return self._send(200, json.dumps({"ok": True, "action": action, "slot": slot, "flag": fname, "ts": ts}))

    def log_message(self, *a):  # 조용히
        pass


if __name__ == "__main__":
    print(f"[control_server] http://0.0.0.0:{PORT}  | glob={STATE_GLOB} | fallback={STATE_SRC} | flags={FLAG_DIR}")
    print("  ★localhost/Tailscale 내부에서만. 공인망 노출 시 토큰인증 추가 필수.")
    if os.environ.get("RAUTO_GIT_PULL") == "1" and REPO:
        threading.Thread(target=_git_pull_loop, daemon=True).start()
        print(f"[git] auto-pull every 180s from {REPO}")
    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), H) as httpd:
        httpd.serve_forever()
