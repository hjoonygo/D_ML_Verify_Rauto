# -*- coding: utf-8 -*-
# [control_server.py] Rauto 제어 대시보드 미니 서버 (표준 라이브러리만, 의존성 0).
#   역할: ① control_dashboard.html 서빙 ② /state.json 제공(봇이 쓴 상태파일 중계)
#         ③ POST /cmd?action=killall|pause|resume|flat&slot= → 플래그 파일 기록(봇 Guard가 읽음)
#   ★보안(필수): localhost 또는 Tailscale/VPN 내부에서만 노출. 공인망 직접노출 금지(토큰 추가 전엔).
#   실행: python control_server.py   (기본 0.0.0.0:8787) → 폰 브라우저로 http://<PC_IP>:8787
import http.server, socketserver, json, os, glob, urllib.parse, datetime, threading, subprocess, time, shutil, sys
import smtplib, ssl
from email.mime.text import MIMEText

HERE = os.path.dirname(os.path.abspath(__file__))

# ── 시크릿 로딩: 환경변수 우선, 없으면 로컬 시크릿파일(rauto_secrets.txt, KEY=VALUE) ──
#   ★setx/프로세스상속 함정(부팅자동시작·다른cmd·SYSTEM이 env 못물림) 영구회피: env가 비면 파일에서 읽음.
#   파일 위치 = control_server.py 옆(C:\RautoControl\rauto_secrets.txt). ★git/zip에 절대 포함 금지(캡틴이 런타임폴더에 직접 생성).
SECRETS_FILE = os.environ.get("RAUTO_SECRETS_FILE", os.path.join(HERE, "rauto_secrets.txt"))
def _load_secret_file(path):
    d = {}
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if (not ln) or ln.startswith("#") or ("=" not in ln):
                    continue
                k, v = ln.split("=", 1)
                d[k.strip()] = v.strip()
    except Exception:
        pass
    return d
_SECRETS = _load_secret_file(SECRETS_FILE)
def _secret(key, default=""):
    v = os.environ.get(key, "")        # env 우선(기존 setx 그대로 작동)
    return v if v else _SECRETS.get(key, default)

# Gmail 성과리포트 전송(앱비밀번호는 env 또는 시크릿파일로만 — 평문 코드/로그/깃 금지, §1)
GMAIL_USER = _secret("RAUTO_GMAIL_USER", "hjoonygo@gmail.com")
GMAIL_APP_PW = _secret("RAUTO_GMAIL_APP_PW", "")
# 봇이 매 배치 끝에 쓰는 상태파일(없으면 예시 사용). RAUTO_DIR 환경변수 우선.
STATE_SRC = os.environ.get("RAUTO_STATE_JSON", os.path.join(HERE, "state_example.json"))
# 슬롯 합치기: 여러 봇(C:\Rauto1,2,..)의 state.json을 한 화면으로 병합. 매칭 0개면 STATE_SRC(단일/데모)로 폴백.
STATE_GLOB = os.environ.get("RAUTO_STATE_GLOB", r"C:\Rauto*\state.json")
FLAG_DIR = os.environ.get("RAUTO_FLAG_DIR", os.environ.get("RAUTO_DAUTO_DIR", r"C:\BinanceData"))
PORT = int(os.environ.get("RAUTO_CTRL_PORT", "8787"))
# git auto-pull: RAUTO_GIT_PULL=1 + RAUTO_REPO=클론경로 → 서버가 180초마다 git pull(대시보드 자동갱신, RDP 불요)
REPO = os.environ.get("RAUTO_REPO", "")

# ── RBAC + Bearer 인증 (지인 배포용, §보안) ──
#   RAUTO_TOKENS="tok1:admin,tok2:view,tok3:view" (env). ★미설정 = 인증 OFF = 기존 동작 호환(캡틴 접속 안깨짐).
#   admin = 전권(제어/이메일). view = 읽기만(상태조회·절대금액 마스킹, /cmd·/email 호출시 서버 403).
def _load_tokens():
    # 형식: "토큰:역할" 또는 "토큰:역할:만료일(YYYY-MM-DD)". 만료일 지나면 자동 무효(접근불능).
    d = {}
    for pair in _secret("RAUTO_TOKENS", "").strip().split(","):
        parts = [x.strip() for x in pair.strip().split(":")]
        if len(parts) < 2:
            continue
        t, r = parts[0], parts[1].lower()
        exp = parts[2] if (len(parts) >= 3 and parts[2]) else None   # None = 무기한
        if t and r in ("admin", "view"):
            d[t] = {"role": r, "exp": exp}
    return d
TOKENS = _load_tokens()
AUTH_ON = bool(TOKENS)
AUDIT_LOG = os.environ.get("RAUTO_AUDIT_LOG", os.path.join(HERE, "audit.log"))


def _audit(ip, who, action, result):
    """감사로그 1줄(JSON): 시각·IP·주체(토큰앞4자)·명령·결과. 90일 보존 권장."""
    try:
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": ts, "ip": ip, "who": who, "action": action, "result": result}, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _mask_state(js):
    """viewer용 PII 마스킹: 절대금액($) 숨김, 수익률(%)·MDD·승률·PF는 유지(수익률 공개·금액 비공개)."""
    try:
        d = json.loads(js)
    except Exception:
        return js
    for s in d.get("slots", []):
        if "bal" in s:
            s["bal"] = None          # 슬롯 잔고($) 숨김 (ret%·mdd%는 유지)
    ac = d.get("acct")
    if isinstance(ac, dict):
        for k in ("fut_seed", "profit_net", "balance"):
            if k in ac:
                ac[k] = None          # 실계좌 금액 숨김
    d["masked"] = True
    return json.dumps(d, ensure_ascii=False)


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

# ★자동로딩 게이트: 0이면 자동로딩 폐지(수동 Bot로딩만). 기본 1=현행 유지(picker 검증 후 0으로 전환).
AUTOLOAD = os.environ.get("RAUTO_AUTOLOAD", "1") != "0"

# ── 봇 레지스트리: Bot로딩 목록(이름→러너+env). 실거래 인증 = 러너 첫 5줄의 # RAUTO_LIVE_CERTIFIED=날짜 마커 ──
_DUAL_R = "06Prj_Ch8_Plugin_Stg1_TS_Impatient/rauto3/test_dual_runner.py"
_CVD_R = os.environ.get("RAUTO_CVD_RUNNER", "07Prj_TS_AdaptiveReopt_Stg1_RegimeDetect/test_Rauto_cvd.py")
BOT_REGISTRY = [
    {"name": "성급",          "runner": "06Prj_Ch8_Plugin_Stg1_TS_Impatient/rauto1/test_Rauto1.py", "env": {}},
    {"name": "성급왕TS",      "runner": "06Prj_Ch8_Plugin_Stg1_TS_Impatient/rauto2/test_Rauto2.py", "env": {}},
    {"name": "최적듀얼",      "runner": _DUAL_R, "env": {"DUAL_SLOT": "R3", "DUAL_K": "1.1"}},
    {"name": "최고Calmar듀얼", "runner": _DUAL_R, "env": {"DUAL_SLOT": "R4", "DUAL_K": "1.4"}},
    {"name": "TS_CvdBoth",    "runner": _CVD_R, "env": {"CVD_SLOT": "R5", "CVD_VARIANT": "both"}},
    {"name": "TS_CvdRcBoth",  "runner": _CVD_R, "env": {"CVD_SLOT": "R6", "CVD_VARIANT": "rc_both"}},
    {"name": "TS_CvdLong",    "runner": _CVD_R, "env": {"CVD_SLOT": "R7", "CVD_VARIANT": "long"}},
]


def _runner_path(rel):
    base = REPO if REPO else os.path.dirname(HERE)
    return os.path.join(base, rel.replace("/", os.sep))


def _cert_of(name):
    """러너 첫 5줄에서 RAUTO_LIVE_CERTIFIED=값 읽기 → 인증값(날짜) 또는 '' (미인증)."""
    import re
    b = next((x for x in BOT_REGISTRY if x["name"] == name), None)
    if not b:
        return ""
    try:
        with open(_runner_path(b["runner"]), encoding="utf-8") as f:
            head = "".join(f.readline() for _ in range(5))
        m = re.search(r"RAUTO_LIVE_CERTIFIED\s*=\s*(\S+)", head)
        return m.group(1) if m else ""
    except Exception:
        return ""


def _bots_list():
    return [{"name": b["name"], "cert": _cert_of(b["name"]),
             "exists": os.path.exists(_runner_path(b["runner"]))} for b in BOT_REGISTRY]


# 슬롯 R번호 → 봇이름 (슬롯명 "R5·TS_CvdBoth" 형식이라 이름 직매칭 불가 → R번호로 매핑)
_SLOT_BOT = {"R1": "성급", "R2": "성급왕TS"}
for _b in BOT_REGISTRY:
    _sid = _b["env"].get("DUAL_SLOT") or _b["env"].get("CVD_SLOT")
    if _sid:
        _SLOT_BOT[_sid] = _b["name"]


def _cert_for_slot(slot_name):
    import re
    m = re.search(r"R(\d+)", slot_name or "")
    return _cert_of(_SLOT_BOT.get("R" + m.group(1), "")) if m else ""


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
            if not AUTOLOAD:        # 자동로딩 폐지 모드 = 코드만 pull, 봇 실행은 수동 Bot로딩으로
                continue
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
    # ★챔피언 자동지정: 최근30일 수익률 최고 슬롯 (캡틴 2026-06-19). trd(거래) pnl% 복리.
    _now = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
    def _r30(s):
        r = 1.0
        for t in (s.get("trd", []) or []):
            if (t.get("xt") or 0) >= _now - 30 * 86400000:
                r *= (1.0 + float(t.get("pnl", 0)) / 100.0)
        return r
    if slots:
        bi = max(range(len(slots)), key=lambda i: _r30(slots[i]))
        for i, s in enumerate(slots):
            s["champ"] = (i == bi)
    for s in slots:                                   # ★실거래 인증(녹색 R): 슬롯R번호→봇→러너 첫줄 마커
        s["cert"] = _cert_for_slot(s.get("name", ""))
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
def _slot_dir(n):
    # 슬롯 폴더 = STATE_GLOB 디렉터리부의 *를 슬롯번호로 치환 (예 C:\Rauto*\state.json → C:\Rauto5)
    return os.path.dirname(STATE_GLOB).replace("*", str(n))


def _empty_slots():
    import re
    used = set()
    for fp in glob.glob(STATE_GLOB):
        m = re.search(r"Rauto(\d+)", fp)
        if m:
            used.add(int(m.group(1)))
    return [n for n in range(1, 9) if n not in used]


def _champ_folder():
    """챔피언 슬롯의 폴더번호(없으면 None). aggregate와 동일 최근30일수익률 기준을 폴더별로 적용."""
    import re
    _now = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
    best = (None, -1.0)
    for fp in glob.glob(STATE_GLOB):
        m = re.search(r"Rauto(\d+)", fp)
        if not m:
            continue
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        for s in d.get("slots", []):
            r = 1.0
            for t in (s.get("trd", []) or []):
                if (t.get("xt") or 0) >= _now - 30 * 86400000:
                    r *= (1.0 + float(t.get("pnl", 0)) / 100.0)
            if r > best[1]:
                best = (int(m.group(1)), r)
    return best[0]


def _champ_live_active():
    """챔피언이 실거래 중 + 긴급중지 안 된 상태인가."""
    try:
        if not json.loads(aggregate_state()).get("live"):
            return False
    except Exception:
        return False
    for fn in ("champ_stop_graceful.flag", "champ_stop_force.flag"):
        if os.path.exists(os.path.join(FLAG_DIR, fn)):
            return False
    return True


def _load_bot(name, slot_n):
    """레지스트리 봇을 C:\\Rauto{n}에 로딩+실행 → state.json 생성. (실행 검증은 Dauto 데이터 있는 AWS에서)"""
    b = next((x for x in BOT_REGISTRY if x["name"] == name), None)
    if not b:
        return False, "unknown bot"
    src = _runner_path(b["runner"])
    if not os.path.exists(src):
        return False, "runner missing: " + src
    base = _slot_dir(slot_n)
    try:
        os.makedirs(base, exist_ok=True)
        srcbots = os.path.join(os.path.dirname(src), "bots")
        botd = os.path.join(base, "bots")
        if not os.path.isdir(botd) and os.path.isdir(srcbots):
            shutil.copytree(srcbots, botd)
        dst = os.path.join(base, os.path.basename(src))
        shutil.copy2(src, dst)
        _run_env(dst, b["env"])
        return True, "loaded into Rauto%d" % slot_n
    except Exception as e:
        return False, str(e)


def _remove_slot(slot_n):
    """슬롯제거(언로드)=그 폴더 state.json 삭제→대시보드서 사라짐. 챔피언+실거래중이면 차단(긴급중지 먼저)."""
    if slot_n < 1 or slot_n > 8:
        return False, "bad slot"
    if slot_n == _champ_folder() and _champ_live_active():
        return False, "champion is live-trading; press emergency stop (실계좌거래중지) first"
    sj = os.path.join(_slot_dir(slot_n), "state.json")
    try:
        if os.path.exists(sj):
            os.remove(sj)
        return True, "removed Rauto%d" % slot_n
    except Exception as e:
        return False, str(e)


ALLOWED = {"killall", "pause", "resume", "flat", "champ_stop_graceful", "champ_stop_force"}


def _stats(pn):
    pn = [float(x) for x in pn]; n = len(pn)
    if not n: return dict(n=0, wr=0, payoff="-", pf="-", ret=0.0, consec=0)
    w = [x for x in pn if x > 0]; l = [x for x in pn if x < 0]
    payoff = round((sum(w) / len(w)) / abs(sum(l) / len(l)), 1) if (w and l) else "-"
    pf = round(sum(w) / abs(sum(l)), 2) if l else "-"
    r = 1.0
    for x in pn: r *= (1.0 + x / 100.0)
    cc = mx = 0
    for x in pn:
        cc = cc + 1 if x < 0 else 0; mx = max(mx, cc)
    return dict(n=n, wr=round(len(w) / n * 100), payoff=payoff, pf=pf, ret=round((r - 1) * 100, 1), consec=mx)


def _champ_report(full=True):
    """챔피언 종합분석표(전체·30일·7일) + 거래내역표. 실거래 여부 열: 페이퍼=수익금공란·수익률만 / 실거래=계좌 $ 전부."""
    try:
        merged = json.loads(aggregate_state())
    except Exception:
        return None
    slots = merged.get("slots", [])
    champ = next((s for s in slots if s.get("champ")), slots[0] if slots else None)
    if not champ:
        return None
    live = bool(merged.get("live"))
    now_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
    trd = champ.get("trd", []) or []
    def win(days): return [float(t.get("pnl", 0)) for t in trd if (t.get("xt") or 0) >= now_ms - days * 86400000]
    s_all, s30, s7 = _stats([float(t.get("pnl", 0)) for t in trd]), _stats(win(30)), _stats(win(7))
    L = []
    L.append(f"■ Rauto 챔피언 성과 리포트 — {champ.get('name')}")
    L.append(f"  {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | 실거래: {'ON (실계좌)' if live else 'OFF (페이퍼/가상)'}")
    L.append(f"  계좌 수익률 {champ.get('ret')}% · MDD {champ.get('mdd')}% · 잔고 ${champ.get('bal'):,}")
    if live:
        ac = merged.get("acct", {}) or {}
        fs, pnn, bal = ac.get("fut_seed"), ac.get("profit_net"), ac.get("balance")
        tn = champ.get("trades") or 0
        per = round(pnn / tn, 2) if (isinstance(pnn, (int, float)) and tn) else "-"
        L.append(f"  [실계좌] 시작선물시드 ${fs if fs is not None else '-'} -> 총수익금 ${pnn if pnn is not None else '-'} -> 현재잔고 ${bal if bal is not None else '-'} (회당 ${per})")
    else:
        L.append("  ※ 페이퍼(가상): 수익금($) 공란, 수익률(%)만 표시")
    L.append("")
    L.append("[표1] 종합 분석표")
    L.append(f"  {'구분':<7}{'거래':>5}{'승률':>6}{'손익비':>7}{'PF':>6}{'수익률':>9}{'연패':>5}")
    for nm, s in (("전체", s_all), ("최근30일", s30), ("최근7일", s7)):
        L.append(f"  {nm:<7}{s['n']:>5}{str(s['wr'])+'%':>6}{str(s['payoff']):>7}{str(s['pf']):>6}{('%+.1f' % s['ret'])+'%':>9}{s['consec']:>5}")
    L.append("")
    N = 40 if full else 12
    L.append(f"[표2] 거래내역 (최신 {N}건)" + (" · 손익금$ 포함" if live else " · 손익%만(페이퍼)"))
    hdr = f"  {'진입(UTC)':>13}{'청산(UTC)':>13}{'방향':>5}{'손익%':>8}"
    if live: hdr += f"{'손익금$':>9}"
    L.append(hdr)
    for t in trd[-N:][::-1]:
        et = datetime.datetime.fromtimestamp((t.get('et') or 0) / 1000, datetime.timezone.utc).strftime('%m-%d %H:%M')
        xt = datetime.datetime.fromtimestamp((t.get('xt') or 0) / 1000, datetime.timezone.utc).strftime('%m-%d %H:%M')
        row = f"  {et:>13}{xt:>13}{str(t.get('side')):>5}{('%+.1f' % float(t.get('pnl', 0))):>8}"
        if live: row += f"{'-':>9}"   # 회당 손익금 = 실계좌 연결+포지션$ 추적 후 채움
        L.append(row)
    return "\n".join(L)


def _send_gmail(to_addr, subject, body):
    if not GMAIL_APP_PW:
        return False, "RAUTO_GMAIL_APP_PW 미설정(AWS에 Gmail 앱비밀번호 환경변수 필요)"
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject; msg["From"] = GMAIL_USER; msg["To"] = to_addr
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=30) as s:
            s.login(GMAIL_USER, GMAIL_APP_PW)
            s.sendmail(GMAIL_USER, [to_addr], msg.as_string())
        return True, "sent"
    except Exception as e:
        return False, str(e)


def _send_telegram(text):
    """기존 ops 텔레그램 봇 재사용(env TELEGRAM_BOT_TOKEN/CHAT_ID). 4096자 초과 시 분할. 실패해도 raise 없음."""
    import urllib.request
    tok = _secret("TELEGRAM_BOT_TOKEN", "").strip()
    chat = _secret("TELEGRAM_CHAT_ID", "").strip()
    if not tok or not chat:
        return False, "TELEGRAM_BOT_TOKEN/CHAT_ID 미설정"
    try:
        for i in range(0, len(text), 3900):
            data = urllib.parse.urlencode({"chat_id": chat, "text": text[i:i + 3900]}).encode("utf-8")
            urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", data=data, timeout=20)
        return True, "sent"
    except Exception as e:
        return False, str(e)


class H(http.server.SimpleHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def _token(self):
        h = self.headers.get("Authorization", "")
        if h.startswith("Bearer "):
            return h[7:].strip()
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        return (q.get("token", [""])[0]).strip()

    def _role(self):
        # 역할: admin/view/None. ★인증 OFF(토큰 미설정)면 admin = 기존 동작 호환. 만료 토큰 = None(무효).
        if not AUTH_ON:
            return "admin"
        info = TOKENS.get(self._token())
        if not info:
            return None
        exp = info.get("exp")
        if exp:   # 만료일(YYYY-MM-DD) 문자열 비교(정렬순) — 오늘이 만료일보다 크면 무효
            today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
            if today > exp:
                return None
        return info["role"]

    def _who(self):
        t = self._token()
        return (t[:4] + "..") if t else "(none)"

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path in ("/", "/index.html", "/control_dashboard.html"):
            fp = os.path.join(HERE, "control_dashboard.html")
            return self._send(200, open(fp, "rb").read(), "text/html; charset=utf-8")
        if p.path == "/whoami":   # 대시보드 JS가 역할 확인(admin만 제어버튼 노출)
            return self._send(200, json.dumps({"role": self._role(), "auth": AUTH_ON}))
        if p.path == "/bots":     # Bot로딩 목록: 등록봇(이름·인증·존재) + 빈 슬롯번호
            if self._role() is None:
                return self._send(401, json.dumps({"error": "unauthorized"}))
            return self._send(200, json.dumps({"bots": _bots_list(), "empty": _empty_slots()}, ensure_ascii=False))
        if p.path.startswith("/state.json"):
            role = self._role()
            if role is None:      # 인증 ON인데 토큰 없음/오류
                return self._send(401, json.dumps({"error": "unauthorized"}))
            js = aggregate_state()
            return self._send(200, _mask_state(js) if role == "view" else js)
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
        ip = self.client_address[0]
        # ★서버단 RBAC: /email·/cmd 는 admin 전용. view/무토큰 = 403 (버튼숨김은 보조, 이게 진짜 경계).
        if p.path in ("/email", "/cmd", "/load", "/remove") and self._role() != "admin":
            _audit(ip, self._who(), p.path + p.query, "403_forbidden")
            return self._send(403, json.dumps({"error": "forbidden (admin only)"}))
        if p.path == "/load":     # Bot로딩: bot=<이름> [slot=<n>] → 빈슬롯에 로딩+실행
            q = urllib.parse.parse_qs(p.query)
            name = q.get("bot", [""])[0]
            try:
                sn = int(q.get("slot", ["0"])[0])
            except Exception:
                sn = 0
            if sn <= 0:
                em = _empty_slots(); sn = em[0] if em else 0
            if sn <= 0:
                return self._send(200, json.dumps({"ok": False, "error": "no empty slot"}))
            ok, info = _load_bot(name, sn)
            _audit(ip, self._who(), "load:%s->Rauto%d" % (name, sn), "ok" if ok else info)
            return self._send(200, json.dumps({"ok": ok, "slot": sn, "info": info}, ensure_ascii=False))
        if p.path == "/remove":   # 슬롯제거(언로드): slot=<n> (챔피언+실거래중이면 차단)
            q = urllib.parse.parse_qs(p.query)
            try:
                sn = int(q.get("slot", ["0"])[0])
            except Exception:
                sn = 0
            ok, info = _remove_slot(sn)
            _audit(ip, self._who(), "remove:Rauto%d" % sn, "ok" if ok else info)
            return self._send(200, json.dumps({"ok": ok, "info": info}, ensure_ascii=False))
        if p.path == "/email":
            q = urllib.parse.parse_qs(p.query)
            to_addr = q.get("to", [GMAIL_USER])[0]
            rep = _champ_report(full=True); tg = _champ_report(full=False)   # 이메일=풀 / 텔레그램=요약
            if not rep:
                return self._send(200, json.dumps({"ok": False, "error": "no champion state"}))
            eok, einfo = _send_gmail(to_addr, "Rauto 챔피언 성과 리포트", rep)
            tok2, tinfo = _send_telegram(tg)
            _audit(ip, self._who(), "email", f"email={eok} tg={tok2}")
            return self._send(200, json.dumps({"ok": (eok or tok2), "email": eok, "telegram": tok2,
                                               "to": to_addr, "err_email": None if eok else einfo,
                                               "err_tg": None if tok2 else tinfo}))
        if p.path != "/cmd":
            return self._send(404, json.dumps({"error": "not found"}))
        q = urllib.parse.parse_qs(p.query)
        action = (q.get("action", [""])[0]).lower()
        slot = q.get("slot", [""])[0]
        if action not in ALLOWED:
            _audit(ip, self._who(), "cmd:" + action, "400_bad_action")
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
        _audit(ip, self._who(), f"cmd:{action} {slot}", "ok")
        return self._send(200, json.dumps({"ok": True, "action": action, "slot": slot, "flag": fname, "ts": ts}))

    def log_message(self, *a):  # 조용히
        pass


if __name__ == "__main__":
    print(f"[control_server] http://0.0.0.0:{PORT}  | glob={STATE_GLOB} | fallback={STATE_SRC} | flags={FLAG_DIR}")
    print(f"  [secrets] file={'FOUND' if _SECRETS else 'none'} ({SECRETS_FILE}) | GMAIL_PW={'set' if GMAIL_APP_PW else 'MISSING'} | TG={'set' if _secret('TELEGRAM_BOT_TOKEN') else 'missing'} | keys={sorted(_SECRETS.keys())}")
    print(f"  [RBAC] auth={'ON' if AUTH_ON else 'OFF(open)'} | tokens={len(TOKENS)} (admin={sum(1 for v in TOKENS.values() if v['role']=='admin')}/view={sum(1 for v in TOKENS.values() if v['role']=='view')}) | exp={[v['exp'] for v in TOKENS.values() if v['exp']]} | audit={AUDIT_LOG}")
    print("  ★localhost/Tailscale 내부에서만. 공인망 노출 시 RAUTO_TOKENS 설정 필수.")
    if os.environ.get("RAUTO_GIT_PULL") == "1" and REPO:
        threading.Thread(target=_git_pull_loop, daemon=True).start()
        print(f"[git] auto-pull every 180s from {REPO}")
    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), H) as httpd:
        httpd.serve_forever()
