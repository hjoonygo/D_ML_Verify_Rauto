# -*- coding: utf-8 -*-
# [260626_02_Rauto2_Sys_server.py] ★Rauto2 제어 서버 — 옛 b32 control_server 개조 (세션 260626_02_Rauto2_Sys).
#   ★무엇이 바뀌었나(개조 핵심):
#     [옛 b32] C:\Rauto*\state.json (외부 슬롯 러너 subprocess가 각자 기록) 을 aggregate_state로 병합.
#              → 봇마다 자기 px(캔들)를 따로 적어 '봇별 차트 상이' 버그.
#     [Rauto2] rauto_live(Rauto2Live)를 ★인프로세스로 구동 → 중앙 1m(DataHub) 단일출처에서
#              state(now)를 직접 생성. px는 state 최상위 1개(전 봇 공유) = 차트버그 구조해소.
#              매매 수치는 검증 batch 원장 그대로(무손상) — 리플레이는 '시간순 드러내기'(실시간 백테).
#   ★역할분담(캡틴): 봇=신호/진입/청산(원장) · Rauto=체결·비용(CEX)·데이터교신(DataHub)·사이징 · 서버=관제/표시.
#   ★유지(b32 호환): 표준라이브러리만·self-locating·RBAC(admin/view)·PWA·/cmd·대시보드 서빙.
#   실행: set PYTHONIOENCODING=utf-8 & python 260626_02_Rauto2_Sys_server.py  → 폰 http://<PC_IP>:8788
import http.server
import socketserver
import json
import os
import sys
import urllib.parse
import datetime
import threading
import time

# 콘솔 인코딩 무관 출력(서비스/리다이렉트서 한글 print 크래시 방지)
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))                # 07_Rauto_System/<세션> → RfRauto 루트
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
from path_finder import ensure_paths                                  # noqa: E402
ensure_paths()
import pandas as pd                                                   # noqa: E402
from fib_replay_1m import load_1m, load_funding                       # noqa: E402
from REVoi_bot import REVoiBot                                        # noqa: E402
from rauto_live import Rauto2Live                                     # noqa: E402
import rauto_datafeed as DF                                           # noqa: E402 라이브 바이낸스 교신

# ── ★버전·정체성(옛 Rauto b32와 100% 구분 — 캡틴 지적 2026-06-26) ──
APP_NAME = "Rauto2"                                                   # 옛="Rauto Control" / 신="Rauto2"
APP_VER = "r1.0"                                                      # Rauto2 첫 릴리스
APP_BUILD = "260626_02"                                               # 세션ID(빌드 식별)
APP_TAG = f"{APP_NAME} {APP_VER} · {APP_BUILD}"                       # 화면·로그 공통 표식
PORT = int(os.environ.get("RAUTO2_PORT", "8788"))                     # ★옛 b32(8787)와 다른 포트 → 동시구동·혼동방지
DASH = os.path.join(HERE, "260626_02_Rauto2_Sys_dashboard.html")
WINNERS = os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")
PX_WIN_MIN = int(os.environ.get("RAUTO2_PXWIN_MIN", str(45 * 1440))) # state.px 최상위 윈도우(분, 기본45일·다운샘플~8000점). 과거 더 보이게(수정1)
# ── ★운영/개발 모드 (캡틴 개념정정 2026-06-26: 36개월=개발용 / 폰·서버=워밍업+실시간) ──
MODE = os.environ.get("RAUTO2_MODE", "replay")                       # replay(개발·36개월 리플레이) | live(운영·워밍업+forward)
WARMUP_DAYS = int(os.environ.get("RAUTO2_WARMUP_DAYS", "60"))        # 운영 워밍업 일수(Dauto 5월~ 포함 위해 60일·거래 표시 확장)
REBUILD_SEC = float(os.environ.get("RAUTO2_REBUILD_SEC", "600"))     # 운영 forward 재계산 주기(초, 기본10분; REVoi=4H봉이라 충분)
CHAMP_MODE = os.environ.get("RAUTO2_CHAMP_MODE", "recent")           # ★챔피언 자동선발: recent(최근2주)|regime(레짐전환)|maxret. 7/1까지 다듬음.
CHAMP_PIN = os.environ.get("RAUTO2_CHAMP_PIN", "REVoi@ETF")          # ★인증봇 고정(캡틴 지시1 260628): 천장봇 자동선발 회피. ""면 자동선발.

# ── 봇 레지스트리: 이름 → (winners config key, 레버, 증거금%). REVoi 변형들(같은 봇·다른 사이징/파라미터). ──
#   ★전 슬롯이 '중앙 px 1개'를 공유 → 캔들 동일·거래만 상이(차트버그 해소 실증). MDD 4단게이트 비교에도 사용.
# ★멀티봇 fleet (260626_02 검증, 캡틴 선정 8종 = #1·#2·#10 제외). 전부 강제청산0(lev≤16). 같은 중앙 px 공유.
#   봇 알파파라미터(tp_frac·regime_factor·gate)=REVoiBot / 사이징·리스크(lev·sz·dd_cut)=슬롯(§25).
#   "mdd" = 검증(36mo) MDD(%) — ★챔피언 자동선발 풀 자격(M20 tier=MDD≥-22)의 정적 기준(§26 인증, 워밍업 변동 무관).
BOT_REGISTRY = [
    {"name": "REVoi@ETF",            "key": "REV_MDD25_36mo", "lev": 3.0,  "sz": 75.0,  "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0, "mdd": -11.2, "desc": "★OOS인증챔피언(캡틴 채택 260628)·예상 월복리 12.29%(held-out OOS 2025+·현실슬립10bp·lev3)·역추세+조기익절COMBO·강제청산0·MDD-11.2%"},  # ★OOS 인증봇(veri_edge.nameplate)
    {"name": "COMBO청산(조기익절1%)",   "key": "REV_MDD25_36mo", "lev": 5.0,  "sz": 75.0,  "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0, "mdd": -19.8, "desc": "★조기익절+구조익절 결합·레짐균형(상승/횡보↑)·held-out강건(260627_02 채택)"},  # ★COMBO M20 챔피언후보
    {"name": "M20챔피언(R+P70)",       "key": "REV_MDD25_36mo", "lev": 6.0,  "sz": 55.0,  "tp_frac": 0.7, "regime_factor": 1.4, "mdd": -20.0, "desc": "실거래자격(MDD-20)·하락장 강"},   # #6 실거래자격
    {"name": "R+P70단순",             "key": "REV_MDD25_36mo", "lev": 6.0,  "sz": 55.0,  "tp_frac": 0.7, "mdd": -19.9, "desc": "의존성0·R+P70 단순"},                         # #7 의존성0
    {"name": "M25고수익",             "key": "REV_MDD25_36mo", "lev": 5.0,  "sz": 85.0,  "tp_frac": 0.7, "regime_factor": 1.4, "mdd": -25.2, "desc": "중위험 공격용(MDD-25)"},   # #5 중위험·공격용
    {"name": "M30",                  "key": "REV_MDD25_36mo", "lev": 8.0,  "sz": 65.0,  "tp_frac": 0.7, "regime_factor": 1.4, "mdd": -30.0, "desc": "고위험 공격용(MDD-30)"},   # #4 고위험·공격용
    {"name": "M0천장(R+P70)",         "key": "REV_MDD25_36mo", "lev": 16.0, "sz": 100.0, "tp_frac": 0.7, "regime_factor": 1.4, "mdd": -70.1, "desc": "공격 천장(고레버·고위험)"},   # #3 공격천장
    {"name": "M4b(DD컷·M20최고)",     "key": "REV_MDD25_36mo", "lev": 6.0,  "sz": 55.0,  "tp_frac": 0.7, "dd_cut": [-0.08, 0.5], "mdd": -15.9, "desc": "robust·DD컷(MDD 최저)"}, # #8 robust
    {"name": "M5게이트(음수월최소)",     "key": "REV_MDD25_36mo", "lev": 6.0,  "sz": 55.0,  "tp_frac": 0.7, "gate": True, "mdd": -20.8, "desc": "음수월 최소·추세역행 차단"},           # #9 음수월 최소
    {"name": "결합R+P80(방어수익)",     "key": "REV_MDD25_36mo", "lev": 6.0,  "sz": 75.0,  "tp_frac": 0.8, "gate": True, "dd_cut": [-0.08, 0.5], "mdd": -18.6, "desc": "방어+수익 결합"},  # #11 방어+수익
]
M20_TIER_THR = -22.0   # 챔피언 풀 자격 = 검증 MDD ≥ 이 값(M20급 같은 위험등급)
# ★36개월 레짐별(7일추세) 월수익(%) — 챔피언선정Sys '기대수익률'의 정적 기준(reg_monthly.py 산출, 36mo 상한·참고).
REG_MONTHLY = {
    "REVoi@ETF": {"up": 10.4, "down": 28.3, "range": 12.4},   # ★OOS인증봇(260628)·레짐별=post-2024 28mo in-sample 패턴(하락 n=1 노이즈·횡보 robust 12.4·헤드라인 12.29%=OOS)
    "COMBO청산(조기익절1%)": {"up": 30.7, "down": 42.6, "range": 29.5},   # ★260627_02 Stg11 산출(산출법 검증 ±1%p)
    "M20챔피언(R+P70)": {"up": 4.5, "down": 28.7, "range": 10.5},
    "R+P70단순":       {"up": 4.5, "down": 29.4, "range": 11.0},
    "M25고수익":       {"up": 5.6, "down": 37.7, "range": 13.4},
    "M30":            {"up": 6.5, "down": 47.0, "range": 16.3},
    "M0천장(R+P70)":   {"up": 6.6, "down": 169.9, "range": 43.3},
    "M4b(DD컷·M20최고)": {"up": 3.5, "down": 23.6, "range": 9.6},
    "M5게이트(음수월최소)": {"up": 5.1, "down": 19.5, "range": 9.8},
    "결합R+P80(방어수익)": {"up": 4.3, "down": 19.5, "range": 11.1},
}
DEFAULT_LOAD = [b["name"] for b in BOT_REGISTRY]   # ★기본 = 8봇 전부 로딩(캡틴: 만든 8개를 바로 보이게). /remove로 빼기 가능.
_BOTKEYS = ("tp_frac", "regime_factor", "gate", "gate_lo", "gate_hi", "early_tp_pct", "early_frac")   # REVoiBot로 가는 알파파라미터(★early_tp 추가 260627_02)


class ReplayEngine:
    """리플레이 클록 + Rauto2Live 보유. now_ms를 전진시키며 state(now)를 만든다(실시간 백테).
       라이브 모드(Dauto)로 확장 시: now=실시각, append_1m+rebuild_slot 주기실행."""

    def __init__(self):
        self.lock = threading.Lock()
        self.cfg = json.load(open(WINNERS, encoding="utf-8"))
        self.mode = MODE                                             # replay | live
        if self.mode == "live":
            print(f"[Rauto2] 운영모드(live) — 워밍업 {WARMUP_DAYS}일 로딩(Dauto 우선/바이낸스 폴백)...", flush=True)
            self.d1m, self.fund, wmeta = DF.build_warmup(WARMUP_DAYS)
            print(f"[Rauto2] 워밍업 src={wmeta['src']} · {wmeta['rows']}행 · {wmeta['from']}~{wmeta['to']} · oi유효{wmeta['oi_valid']}", flush=True)
        else:
            print("[Rauto2] 개발 리플레이(replay) — 36개월 중앙 1m 로딩...", flush=True)
            self.d1m = load_1m()
            self.fund = load_funding()
        self.live = Rauto2Live(self.d1m, self.fund, px_window_min=PX_WIN_MIN, champ_mode=CHAMP_MODE, champ_pin=(CHAMP_PIN or None))
        self.data_start = int(self.live._idx_ms[0])
        self.data_end = int(self.live._idx_ms[-1])
        # now: 운영=최신봉(실시간), 개발=워밍업 후 시작점(리플레이)
        self.now_ms = self.data_end if self.mode == "live" else (self.data_start + PX_WIN_MIN * 60_000)
        self.step_min = int(os.environ.get("RAUTO2_STEP_MIN", "240"))  # (개발) 1틱 전진(분, 기본 4H=신호봉)
        self.tick_sec = float(os.environ.get("RAUTO2_TICK_SEC", "0.4"))  # (개발) 틱 간격(초)
        self.paused = False
        self.emergency = False                                       # ★긴급중지(챔피언 실거래 중단) 플래그
        self.loaded = []                                             # 로딩된 봇 이름들
        # ── 라이브 데이터 교신(바이낸스 공개REST/Dauto) — '실시장' 캔들·현재가. REVoi 신호는 OI파이프라인 연결 후(브리지). ──
        self.live_px = []                                            # 최근 1일 실시장 1m [[ms,o,h,l,c],...]
        self.price = None                                           # 현재가
        self.live_src = None
        self.live_fetch_sec = float(os.environ.get("RAUTO2_LIVE_SEC", "15"))
        for nm in DEFAULT_LOAD:
            self.load_bot(nm)
        print(f"[Rauto2] 모드={self.mode} · 데이터 {len(self.d1m):,}행 · {pd.Timestamp(self.data_start, unit='ms')} ~ "
              f"{pd.Timestamp(self.data_end, unit='ms')} · 기본봇 {self.loaded}", flush=True)
        threading.Thread(target=self._clock, daemon=True).start()
        threading.Thread(target=self._live_feed, daemon=True).start()
        if self.mode == "live":
            threading.Thread(target=self._forward, daemon=True).start()

    def _forward(self):
        """★운영 forward(실시간 백테): 주기적으로 워밍업 재빌드(새 봉·OI 반영) → 봇 재계산 → now=최신.
           REVoi=4H봉이라 REBUILD_SEC(기본10분)면 충분. 실패해도 기존 상태 유지(서버 안 죽음)."""
        while True:
            time.sleep(REBUILD_SEC)
            if self.mode != "live":
                continue
            try:
                d1m, fund, meta = DF.build_warmup(WARMUP_DAYS)
                nl = Rauto2Live(d1m, fund, px_window_min=PX_WIN_MIN, champ_mode=CHAMP_MODE, champ_pin=(CHAMP_PIN or None))
                for nm in list(self.loaded):
                    b = next((x for x in BOT_REGISTRY if x["name"] == nm), None)
                    if b:
                        pp = dict(self.cfg[b["key"]]["p"])
                        for k in _BOTKEYS:
                            if k in b: pp[k] = b[k]
                        nl.add_bot(nm, REVoiBot(pp), b["sz"], b["lev"], dd_cut=b.get("dd_cut"),
                                   m20=(b.get("mdd", -99) >= M20_TIER_THR), reg_monthly=REG_MONTHLY.get(nm))
                with self.lock:
                    self.live = nl
                    self.d1m, self.fund = d1m, fund
                    self.data_start = int(nl._idx_ms[0])
                    self.data_end = int(nl._idx_ms[-1])
                    self.now_ms = self.data_end
                print(f"[Rauto2 forward] 재빌드 OK · {meta['rows']}행 · ~{meta['to']}", flush=True)
            except Exception as e:
                print(f"[Rauto2 forward] 재빌드 실패(기존 유지): {e}", flush=True)

    def _live_feed(self):
        """라이브 데이터 교신: 최근 1일 실시장 1m + 현재가를 주기 갱신(Dauto CSV 우선, 없으면 REST).
           ★실패해도 서버는 계속(리플레이는 무관). REVoi 라이브 신호는 OI파이프라인 브리지 과제."""
        while True:
            try:
                df, src = DF.live_1m_df(1440)
                px = DF.fetch_price()
                rows = []
                if df is not None and len(df):
                    im = (df.index.astype("int64") // 1_000_000).tolist()
                    o, h, l, c = df["open"].tolist(), df["high"].tolist(), df["low"].tolist(), df["close"].tolist()
                    rows = [[int(im[i]), round(o[i], 1), round(h[i], 1), round(l[i], 1), round(c[i], 1)]
                            for i in range(len(im))]
                with self.lock:
                    if rows:
                        self.live_px = rows
                    self.price = px
                    self.live_src = src
            except Exception:
                pass
            time.sleep(self.live_fetch_sec)

    def load_bot(self, name):
        b = next((x for x in BOT_REGISTRY if x["name"] == name), None)
        if not b:
            return False, "unknown bot"
        if name in self.loaded:
            return False, "already loaded"
        with self.lock:
            p = dict(self.cfg[b["key"]]["p"])
            for k in _BOTKEYS:                          # ★봇 알파파라미터 주입(tp_frac·regime_factor·gate…)
                if k in b: p[k] = b[k]
            self.live.add_bot(name, REVoiBot(p), b["sz"], b["lev"], dd_cut=b.get("dd_cut"),
                              m20=(b.get("mdd", -99) >= M20_TIER_THR),    # ★검증MDD 기반 M20 자격(정적)
                              reg_monthly=REG_MONTHLY.get(name))          # ★36mo 레짐별 월수익(기대수익률)
            self.loaded.append(name)
        return True, "loaded"

    def remove_bot(self, name):
        with self.lock:
            idx = next((i for i, s in enumerate(self.live.slots) if s.name == name), None)
            if idx is None:
                return False, "not loaded"
            del self.live.slots[idx]
            self.loaded.remove(name)
        return True, "removed"

    def _clock(self):
        while True:
            time.sleep(self.tick_sec)
            if self.paused or self.mode != "replay":
                continue
            with self.lock:
                if self.now_ms < self.data_end:
                    self.now_ms = min(self.data_end, self.now_ms + self.step_min * 60_000)

    def control(self, action, v=None):
        with self.lock:
            if action == "replay_pause":
                self.paused = True
            elif action == "replay_resume":
                self.paused = False
            elif action == "replay_restart":
                self.now_ms = self.data_start + PX_WIN_MIN * 60_000
                self.paused = False
            elif action == "replay_end":
                self.now_ms = self.data_end
            elif action == "replay_speed" and v is not None:
                self.step_min = max(1, int(float(v)))                # 1틱 전진 분(클수록 빠름)
            elif action == "replay_seek" and v is not None:
                frac = max(0.0, min(1.0, float(v)))
                self.now_ms = int(self.data_start + (self.data_end - self.data_start) * frac)
            elif action in ("champ_stop_graceful", "champ_stop_force"):
                self.emergency = True               # ★긴급중지 = 챔피언 실거래 자격 중단(페이퍼=상징·라이브=주문중단)
            elif action == "resume":
                self.emergency = False
            else:
                return False
            return True

    def state(self):
        with self.lock:
            st = self.live.state(self.now_ms, with_px=True)
            span = max(1, self.data_end - self.data_start)
            st["replay"] = {
                "mode": self.mode,
                "paused": self.paused,
                "step_min": self.step_min,
                "tick_sec": self.tick_sec,
                "progress": round((self.now_ms - self.data_start) / span * 100.0, 1),
                "now": str(pd.Timestamp(self.now_ms, unit="ms")),
                "at_end": self.now_ms >= self.data_end,
            }
            st["registry"] = [b["name"] for b in BOT_REGISTRY]
            st["loaded"] = list(self.loaded)
            st["live_px"] = self.live_px                              # ★실시장 캔들(라이브 데이터피드)
            st["price"] = self.price                                  # 현재가
            st["live_src"] = self.live_src
            st["ver"] = APP_TAG                                       # ★버전 표식(폰서 옛/신 구분)
            st["port"] = PORT
            st["emergency"] = self.emergency                         # ★긴급중지 상태
        return st


ENG = None   # 서버 시작 시 생성(무거운 로딩 1회)

# ── RBAC(b32 호환, 기본 OFF=open). RAUTO2_TOKENS="tok:admin,tok2:view" ──
def _load_tokens():
    d = {}
    for pair in os.environ.get("RAUTO2_TOKENS", "").strip().split(","):
        parts = [x.strip() for x in pair.split(":")]
        if len(parts) >= 2 and parts[0] and parts[1].lower() in ("admin", "view"):
            d[parts[0]] = parts[1].lower()
    return d
TOKENS = _load_tokens()
AUTH_ON = bool(TOKENS)
ALLOWED = {"replay_pause", "replay_resume", "replay_restart", "replay_end",
           "replay_speed", "replay_seek", "killall", "pause", "resume",
           "champ_stop_graceful", "champ_stop_force"}              # ★긴급중지(수정3)


# ── 이메일/텔레그램 성과리포트(수정4 — b32 복원). 시크릿 = env 우선, 없으면 rauto_secrets.txt(코드 옆) ──
def _secret(key, default=""):
    v = os.environ.get(key, "")
    if v:
        return v
    try:
        for ln in open(os.path.join(HERE, "rauto_secrets.txt"), encoding="utf-8"):
            ln = ln.strip()
            if "=" in ln and not ln.startswith("#"):
                k, val = ln.split("=", 1)
                if k.strip() == key:
                    return val.strip()
    except Exception:
        pass
    return default


def _send_gmail(to_addr, subject, body):
    import smtplib, ssl
    from email.mime.text import MIMEText
    user = _secret("RAUTO_GMAIL_USER", "hjoonygo@gmail.com"); pw = _secret("RAUTO_GMAIL_APP_PW", "")
    if not pw:
        return False, "RAUTO_GMAIL_APP_PW 미설정(rauto_secrets.txt 또는 env)"
    msg = MIMEText(body, "plain", "utf-8"); msg["Subject"] = subject; msg["From"] = user; msg["To"] = to_addr
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=30) as s:
            s.login(user, pw); s.sendmail(user, [to_addr], msg.as_string())
        return True, "sent"
    except Exception as e:
        return False, str(e)


def _send_telegram(text):
    import urllib.request
    tok = _secret("TELEGRAM_BOT_TOKEN", "").strip(); chat = _secret("TELEGRAM_CHAT_ID", "").strip()
    if not tok or not chat:
        return False, "TELEGRAM_BOT_TOKEN/CHAT_ID 미설정"
    try:
        for i in range(0, len(text), 3900):
            data = urllib.parse.urlencode({"chat_id": chat, "text": text[i:i + 3900]}).encode("utf-8")
            urllib.request.urlopen("https://api.telegram.org/bot%s/sendMessage" % tok, data=data, timeout=20)
        return True, "sent"
    except Exception as e:
        return False, str(e)


def _champ_report():
    """현재 챔피언(자동선발) 성과 요약 리포트(이메일·텔레그램 본문)."""
    st = ENG.state()
    champ = next((s for s in st["slots"] if s.get("champ")), None)
    if not champ:
        return None
    reg = st.get("regime", "?")
    L = []
    L.append("[Rauto2 챔피언 성과] %s" % APP_TAG)
    L.append("  시각 %s · 현 레짐 %s · 챔피언선정 %s" % (str((st.get("replay") or {}).get("now", st.get("updated", "")))[:16], reg, st.get("champ_mode")))
    L.append("  챔피언 = %s  (실거래 %s)" % (champ["name"], "중단(긴급)" if st.get("emergency") else ("OFF/페이퍼" if not st.get("live") else "ON")))
    L.append("  수익률 %+.1f%% · MDD %.1f%% · 거래 %d · 승률 %d%% · PF %s" % (
        champ.get("ret", 0), champ.get("mdd", 0), champ.get("trades", 0), champ.get("winrate", 0), champ.get("pf")))
    wk = champ.get("wk", {})
    L.append("  최근1주: 거래 %s · 승률 %s%% · 수익률 %s%%" % (wk.get("trades"), wk.get("winrate"), wk.get("ret")))
    L.append("  현재가 BTC %s" % (round(st.get("price")) if st.get("price") else "—"))
    L.append("  로딩 슬롯: " + ", ".join(st.get("loaded", [])))
    return "\n".join(L)


class H(http.server.SimpleHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _token(self):
        h = self.headers.get("Authorization", "")
        if h.startswith("Bearer "):
            return h[7:].strip()
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        return (q.get("token", [""])[0]).strip()

    def _role(self):
        if not AUTH_ON:
            return "admin"
        return TOKENS.get(self._token())   # admin/view/None

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path in ("/", "/index.html", "/control_dashboard.html", "/260626_02_Rauto2_Sys_dashboard.html"):
            try:
                return self._send(200, open(DASH, "rb").read(), "text/html; charset=utf-8")
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)}))
        if p.path == "/whoami":
            return self._send(200, json.dumps({"role": self._role(), "auth": AUTH_ON}))
        if p.path == "/bots":
            if self._role() is None:
                return self._send(401, json.dumps({"error": "unauthorized"}))
            avail = [{"name": b["name"], "loaded": (b["name"] in ENG.loaded),
                      "lev": b["lev"], "sz": b["sz"], "mdd": b.get("mdd"),
                      "desc": b.get("desc", ""), "reg_monthly": REG_MONTHLY.get(b["name"])} for b in BOT_REGISTRY]
            return self._send(200, json.dumps({"bots": avail}, ensure_ascii=False))
        if p.path.startswith("/state.json"):
            if self._role() is None:
                return self._send(401, json.dumps({"error": "unauthorized"}))
            return self._send(200, json.dumps(ENG.state(), ensure_ascii=False))
        STATIC = {"/manifest.json": "application/manifest+json", "/sw.js": "application/javascript",
                  "/icon-192.png": "image/png", "/icon-512.png": "image/png"}
        if p.path in STATIC:
            fp = os.path.join(HERE, p.path.lstrip("/"))
            if os.path.exists(fp):
                return self._send(200, open(fp, "rb").read(), STATIC[p.path])
        return self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        p = urllib.parse.urlparse(self.path)
        if p.path in ("/cmd", "/load", "/remove", "/email") and self._role() != "admin":
            return self._send(403, json.dumps({"error": "forbidden (admin only)"}))
        q = urllib.parse.parse_qs(p.query)
        if p.path == "/email":      # ★수정4: 챔피언 성과를 이메일+텔레그램으로(크루 공유)
            rep = _champ_report()
            if not rep:
                return self._send(200, json.dumps({"ok": False, "error": "no champion"}))
            to_addr = q.get("to", [_secret("RAUTO_GMAIL_USER", "hjoonygo@gmail.com")])[0]
            eok, einfo = _send_gmail(to_addr, "Rauto2 챔피언 성과", rep)
            tok2, tinfo = _send_telegram(rep)
            return self._send(200, json.dumps({"ok": (eok or tok2), "email": eok, "telegram": tok2,
                                               "err_email": None if eok else einfo, "err_tg": None if tok2 else tinfo},
                                              ensure_ascii=False))
        if p.path == "/load":
            ok, info = ENG.load_bot(q.get("bot", [""])[0])
            return self._send(200, json.dumps({"ok": ok, "info": info}, ensure_ascii=False))
        if p.path == "/remove":
            ok, info = ENG.remove_bot(q.get("bot", [""])[0])
            return self._send(200, json.dumps({"ok": ok, "info": info}, ensure_ascii=False))
        if p.path == "/cmd":
            action = (q.get("action", [""])[0]).lower()
            v = q.get("v", [None])[0]
            if action not in ALLOWED:
                return self._send(400, json.dumps({"error": "bad action"}))
            ok = ENG.control(action, v) if (action.startswith("replay_") or
                 action in ("champ_stop_graceful", "champ_stop_force", "resume")) else True
            return self._send(200, json.dumps({"ok": ok, "action": action, "v": v}))
        return self._send(404, json.dumps({"error": "not found"}))

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"[{APP_TAG}] 시작 — http://0.0.0.0:{PORT}  (옛 Rauto b32(8787)와 다른 포트·서비스명=혼동방지)", flush=True)
    ENG = ReplayEngine()
    print(f"  [RBAC] {'ON' if AUTH_ON else 'OFF(open)'} · 리플레이 {ENG.step_min}분/틱·{ENG.tick_sec}초 · px윈도우 {PX_WIN_MIN//1440}일", flush=True)
    print("  ★폰: 같은 와이파이/테일스케일에서 http://<PC_IP>:%d 접속. 공개망 노출 시 RAUTO2_TOKENS 설정." % PORT, flush=True)
    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), H) as httpd:
        httpd.serve_forever()
