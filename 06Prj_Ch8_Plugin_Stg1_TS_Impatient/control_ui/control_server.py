# -*- coding: utf-8 -*-
# [control_server.py] Rauto 제어 대시보드 미니 서버 (표준 라이브러리만, 의존성 0).
#   역할: ① control_dashboard.html 서빙 ② /state.json 제공(봇이 쓴 상태파일 중계)
#         ③ POST /cmd?action=killall|pause|resume|flat&slot= → 플래그 파일 기록(봇 Guard가 읽음)
#   ★보안(필수): localhost 또는 Tailscale/VPN 내부에서만 노출. 공인망 직접노출 금지(토큰 추가 전엔).
#   실행: python control_server.py   (기본 0.0.0.0:8787) → 폰 브라우저로 http://<PC_IP>:8787
import http.server, socketserver, json, os, glob, urllib.parse, datetime, threading, subprocess, time, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
# 봇이 매 배치 끝에 쓰는 상태파일(없으면 예시 사용). RAUTO_DIR 환경변수 우선.
STATE_SRC = os.environ.get("RAUTO_STATE_JSON", os.path.join(HERE, "state_example.json"))
# 슬롯 합치기: 여러 봇(C:\Rauto1,2,..)의 state.json을 한 화면으로 병합. 매칭 0개면 STATE_SRC(단일/데모)로 폴백.
STATE_GLOB = os.environ.get("RAUTO_STATE_GLOB", r"C:\Rauto*\state.json")
FLAG_DIR = os.environ.get("RAUTO_FLAG_DIR", os.environ.get("RAUTO_DAUTO_DIR", r"C:\BinanceData"))
PORT = int(os.environ.get("RAUTO_CTRL_PORT", "8787"))
# git auto-pull: RAUTO_GIT_PULL=1 + RAUTO_REPO=클론경로 → 서버가 180초마다 git pull(대시보드 자동갱신, RDP 불요)
REPO = os.environ.get("RAUTO_REPO", "")


_P = os.path.join(REPO, "06Prj_Ch8_Plugin_Stg1_TS_Impatient") if REPO else ""
BOT_SRC = os.path.join(_P, "rauto1", "test_Rauto1.py") if REPO else ""
BOT_DST = r"C:\Rauto1\test_Rauto1.py"
R2_SRC = os.path.join(_P, "rauto2", "test_Rauto2.py") if REPO else ""
R2_DST = r"C:\Rauto2\test_Rauto2.py"
R2_KING_SRC = os.path.join(_P, "rauto2", "bots", "bot_trendstack_impatient_king.py") if REPO else ""
DUAL_RUNNER_SRC = os.path.join(_P, "rauto3", "test_dual_runner.py") if REPO else ""
DUAL_BOTS_SRC = os.path.join(_P, "rauto3", "bots") if REPO else ""
# (폴더, DUAL_SLOT, 전략명, k, er, w) — R3 최적듀얼 / R4 최고Calmar듀얼. 둘 다 페이퍼·champ=0(챔피언은 R2)
DUAL_SLOTS = [("Rauto3", "R3", "최적듀얼", "1.1", "0.40", "0.0"),
              ("Rauto4", "R4", "최고Calmar듀얼", "1.4", "0.40", "0.0")]


def _changed(src, dst):
    # src가 dst와 다르면 복사(필요시 폴더생성) 후 True
    if not (src and os.path.exists(src)):
        return False
    a = open(src, "rb").read()
    b = open(dst, "rb").read() if os.path.exists(dst) else b""
    if a != b:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        return True
    return False


def _run(path):
    subprocess.run([sys.executable, os.path.basename(path)], cwd=os.path.dirname(path),
                   capture_output=True, timeout=180)


def _run_env(path, env):
    e = dict(os.environ); e.update(env)
    subprocess.run([sys.executable, os.path.basename(path)], cwd=os.path.dirname(path),
                   env=e, capture_output=True, timeout=240)


def _git_pull_loop():
    while True:
        time.sleep(180)
        try:
            subprocess.run(["git", "-C", REPO, "pull", "--ff-only"], capture_output=True, timeout=60)
            # Rauto1(성급): 러너 바뀌면 C:\Rauto1로 복사+실행(state.json 갱신)
            if _changed(BOT_SRC, BOT_DST):
                _run(BOT_DST)
            # Rauto2(성급왕 페이퍼): bots를 Rauto1에서 부트스트랩 + king봇·러너 동기화 후 실행 → 대시보드 R2 자동
            if R2_SRC and os.path.exists(R2_SRC):
                r2b = r"C:\Rauto2\bots"
                if not os.path.isdir(r2b) and os.path.isdir(r"C:\Rauto1\bots"):
                    shutil.copytree(r"C:\Rauto1\bots", r2b)
                ck = _changed(R2_KING_SRC, os.path.join(r2b, "bot_trendstack_impatient_king.py"))
                cr = _changed(R2_SRC, R2_DST)
                if ck or cr:
                    _run(R2_DST)
            # Rauto3/4(듀얼 페이퍼): repo rauto3/bots 부트스트랩 + 러너 동기화 후 env로 실행 → 대시보드 R3·R4 자동
            if DUAL_RUNNER_SRC and os.path.exists(DUAL_RUNNER_SRC):
                for folder, slot, strat, k, er, w in DUAL_SLOTS:
                    base = "C:\\" + folder; bots = os.path.join(base, "bots")
                    if not os.path.isdir(bots) and os.path.isdir(DUAL_BOTS_SRC):
                        shutil.copytree(DUAL_BOTS_SRC, bots)
                    rk = _changed(R2_KING_SRC, os.path.join(bots, "bot_trendstack_impatient_king.py"))
                    runner = os.path.join(base, "test_dual_runner.py")
                    cr2 = _changed(DUAL_RUNNER_SRC, runner)
                    if rk or cr2 or not os.path.exists(os.path.join(base, "state.json")):
                        _run_env(runner, {"DUAL_SLOT": slot, "DUAL_STRAT": strat, "DUAL_K": k,
                                          "DUAL_ER": er, "DUAL_W": w, "DUAL_CHAMP": "0"})
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
