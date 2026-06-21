# -*- coding: utf-8 -*-
# [파일명] test_07Prj_Ch4_RunAWS_Stg16_OpsGuard.py — OpsGuard 8시나리오 사전실행
# 코드길이: 약 200줄 | 내부버전: stg16_test_v1
# [원칙] 전부 샌드박스(temp 경로·mock HTTP·schtasks 미호출) — 실제 발송·태스크 변경 없음.
#   실제 발송 1회는 캡틴이 토큰 입력 후 AWS에서 수행(지시서).
# [시나리오]
#  S1 alert_telegram 환경변수 없음 → NO-OP 안전 종료(예외 0)
#  S2 더미 환경변수+mock HTTP 200 → JSON 페이로드(chat_id·[PAPER] 태그) 검증
#  S3 mock HTTPError 404 → 404 반환·raise 없음 (4xx 분기)
#  S4 alert_check 신규이벤트 diff → 시작1+거래7건x2장=15건, 재실행 0건(중복방지)
#  S5 오류·KILL 알림 → ★긴급 1회만·kill.flag 1회만(중복방지)
#  S6 kill_guard → ★KILL 1줄(health append)+marker, 재실행 무동작·자동복구 없음
#  S7 telegram_poll → 타 chat_id 거부 / /status 4축 회신 / /kill flag 생성 / 그외 무시
#  S8 봇 본체 무수정 — Stg14 bots 해시 10종 = §8 상수 일치
import os, sys, io, json, csv, shutil, tempfile, traceback
import importlib.util
import urllib.request, urllib.error, urllib.parse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))


def find_stg14():
    """Stg14 산출물 폴더 — PC·AWS 동일 코드 (E항 통일: env RAUTO_DIR → C:\\run_Rauto
    → PC 상대경로 → 자기 폴더). dirname(HERE) 고정 상수 금지 — AWS에서 C:\\07Prj... 오류."""
    cands = [os.environ.get("RAUTO_DIR", ""), r"C:\run_Rauto",
             os.path.join(os.path.dirname(HERE), "07Prj_Ch4_RunAWS_Stg14_LivePaperWarmup"),
             HERE]
    for c in cands:
        if c and os.path.exists(
                os.path.join(c, "check_07Prj_Ch4_RunAWS_Stg14_LivePaperWarmup.py")):
            return c
    raise FileNotFoundError("Stg14 폴더 미발견 — setx RAUTO_DIR 또는 C:\\run_Rauto 설치 필요")


STG14 = find_stg14()
TMP = tempfile.mkdtemp(prefix="stg16_")
os.environ["RAUTO_OPS_LOG"] = os.path.join(TMP, "ops_alert.log")   # 로그 샌드박스

sys.path.insert(0, HERE)
import ops_common as oc
import alert_telegram as tg
import alert_check as ac
import kill_guard as kg
import telegram_poll as tp

RESULTS, SAMPLES = [], {}


def run(name, fn):
    try:
        fn()
        RESULTS.append((name, True, ""))
    except Exception as e:
        RESULTS.append((name, False, f"{type(e).__name__}: {e}"))
        traceback.print_exc()


# ── S1 NO-OP ────────────────────────────────────────────────────────────────
def s1():
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        os.environ.pop(k, None)
    assert tg.send("S1 무환경 테스트") is None, "NO-OP여야 함"
    assert "NO-OP" in open(oc.OPS_LOG, encoding="utf-8").read()


# ── S2/S3 mock HTTP ─────────────────────────────────────────────────────────
def s2():
    # v2: 토큰 따옴표/공백 오염 케이스 포함(① strip 검증) + form 인코딩(②) 검증
    os.environ["TELEGRAM_BOT_TOKEN"] = ' "DUMMY_TOKEN" '
    os.environ["TELEGRAM_CHAT_ID"] = "123456"
    captured = {}

    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def getcode(self): return 200

    def fake_open(req, timeout=15):
        captured["url"] = req.full_url
        captured["body"] = urllib.parse.parse_qs(req.data.decode("utf-8"))
        captured["ctype"] = req.headers.get("Content-type", "")
        return FakeResp()

    orig = tg._urlopen
    tg._urlopen = fake_open
    try:
        code = tg.send("S2 페이로드 검증")
    finally:
        tg._urlopen = orig
    assert code == 200, f"200 기대, got {code}"
    assert captured["body"]["chat_id"] == ["123456"]
    assert captured["body"]["text"][0].startswith("[PAPER] "), captured["body"]
    assert "/botDUMMY_TOKEN/sendMessage" in captured["url"], f"strip 실패: {captured['url']}"
    assert "x-www-form-urlencoded" in captured["ctype"]


def s3():
    def fake_404(req, timeout=15):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", None, io.BytesIO(b""))
    orig = tg._urlopen
    tg._urlopen = fake_404
    try:
        code = tg.send("S3 4xx 분기")
    finally:
        tg._urlopen = orig
    assert code == 404, f"404 기대, got {code}"


# ── S4/S5 alert_check 샌드박스 ───────────────────────────────────────────────
SENT = []


def recorder(text):
    SENT.append(text)
    return 200


def make_sandbox():
    rd = os.path.join(TMP, "rauto")
    os.makedirs(rd, exist_ok=True)
    shutil.copy(os.path.join(STG14, "paper_ledger.csv"), rd)
    shutil.copy(os.path.join(STG14, "scorecard_daily.csv"), rd)
    with open(os.path.join(rd, "stg14_health.log"), "w", encoding="utf-8") as f:
        f.write("OK 2026-06-13 00:11 UTC | 예외0·갭0·동치True | date=2026-06-12 "
                "bars=1440 bal_ts=11365.23 bal_sw=10000.0 oi_z=100.0% atr=100.0% damp=0 blk=0\n")
    os.environ["RAUTO_DIR"] = rd
    return rd


def s4():
    rd = make_sandbox()
    ac.STATE = os.path.join(TMP, "ops_state.json")
    oc.KILL_FLAG = os.path.join(TMP, "kill.flag")    # 미존재 상태
    tg_orig, tg.send = tg.send, recorder
    try:
        SENT.clear()
        ac.main()
        n_led = sum(1 for _ in csv.DictReader(open(os.path.join(rd, "paper_ledger.csv"),
                                                   encoding="utf-8-sig")))
        want = 1 + n_led * 2 + 1                     # 시작1 + 거래x2 + 하트비트1(v2)
        assert len(SENT) == want, f"{want}건 기대, got {len(SENT)}"
        assert SENT[-1].startswith("✅ 일일요약"), SENT[-1]
        SAMPLES["start"] = SENT[0]
        SAMPLES["open"] = SENT[1]
        SAMPLES["close"] = SENT[2]
        SAMPLES["heartbeat"] = SENT[-1]
        SENT.clear()
        ac.main()                                    # 재실행 — 중복 0(하트비트도 같은 날 1회)
        assert len(SENT) == 0, f"중복방지 실패: {len(SENT)}건 재발신"
    finally:
        tg.send = tg_orig


def s5():
    rd = os.environ["RAUTO_DIR"]
    with open(os.path.join(rd, "stg14_health.log"), "a", encoding="utf-8") as f:
        f.write("★긴급 2026-06-13 00:12 UTC | 동치깨짐 | date=2026-06-12\n")
    tg_orig, tg.send = tg.send, recorder
    try:
        SENT.clear()
        ac.main()
        assert len(SENT) == 1 and SENT[0].startswith("🚨 오류"), SENT
        SAMPLES["error"] = SENT[0]
        SENT.clear()
        ac.main()                                    # 같은 ★긴급 재알림 금지
        assert len(SENT) == 0
        with open(oc.KILL_FLAG, "w", encoding="utf-8") as f:
            f.write("test\n")
        SENT.clear()
        ac.main()
        assert len(SENT) == 1 and "KILL" in SENT[0], SENT
        SENT.clear()
        ac.main()
        assert len(SENT) == 0, "kill 재알림 금지"
        os.remove(oc.KILL_FLAG)
    finally:
        tg.send = tg_orig


# ── S6 kill_guard ───────────────────────────────────────────────────────────
def s6():
    os.environ["RAUTO_KILL_TEST"] = "1"              # 실 schtasks 미호출
    oc.KILL_FLAG = os.path.join(TMP, "kill2.flag")
    rd = os.environ["RAUTO_DIR"]
    hl = os.path.join(rd, "stg14_health.log")
    n0 = len(open(hl, encoding="utf-8").read().splitlines())
    assert kg.main() == 0 and not os.path.exists(oc.KILL_FLAG + ".handled")  # flag 없음=무동작
    with open(oc.KILL_FLAG, "w", encoding="utf-8") as f:
        f.write("manual\n")
    tg_orig, tg.send = tg.send, recorder
    try:
        SENT.clear()
        kg.main()
        lines = open(hl, encoding="utf-8").read().splitlines()
        assert len(lines) == n0 + 1 and lines[-1].startswith("★KILL"), lines[-1]
        assert os.path.exists(oc.KILL_FLAG + ".handled")
        assert len(SENT) == 1 and "★KILL" in SENT[0]
        SAMPLES["kill"] = SENT[0]
        SENT.clear()
        kg.main()                                    # 재실행 — 무동작(재알림 0)
        assert len(SENT) == 0
        assert os.path.exists(oc.KILL_FLAG), "자동복구(flag 삭제) 금지"
    finally:
        tg.send = tg_orig
        os.environ.pop("RAUTO_KILL_TEST", None)


# ── S7 telegram_poll ────────────────────────────────────────────────────────
def s7():
    tp.PSTATE = os.path.join(TMP, "poll_state.json")
    oc.KILL_FLAG = os.path.join(TMP, "kill3.flag")
    fake_updates = {"ok": True, "result": [
        {"update_id": 11, "message": {"chat": {"id": 999999}, "text": "/status"}},   # 타인 거부
        {"update_id": 12, "message": {"chat": {"id": 123456}, "text": "/start"}},    # 무시
        {"update_id": 13, "message": {"chat": {"id": 123456}, "text": "/status"}},
        {"update_id": 14, "message": {"chat": {"id": 123456}, "text": "/kill"}},
    ]}
    gu_orig, tp.get_updates = tp.get_updates, lambda tok, off: fake_updates
    tg_orig, tg.send = tg.send, recorder
    try:
        SENT.clear()
        tp.main()
        assert len(SENT) == 2, f"status+kill확인 2건 기대, got {len(SENT)}: {SENT}"
        assert SENT[0].startswith("📊 상태") and len(SENT[0].splitlines()) >= 5
        assert os.path.exists(oc.KILL_FLAG), "/kill → flag 생성돼야 함"
        st = json.load(open(tp.PSTATE, encoding="utf-8"))
        assert st["offset"] == 15, st
        SAMPLES["status"] = SENT[0]
    finally:
        tp.get_updates, tg.send = gu_orig, tg_orig
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_CHAT_ID", None)
        os.environ.pop("RAUTO_DIR", None)


# ── S8 봇 본체 무수정 ────────────────────────────────────────────────────────
def s8():
    spec = importlib.util.spec_from_file_location(
        "c14", os.path.join(STG14, "check_07Prj_Ch4_RunAWS_Stg14_LivePaperWarmup.py"))
    c14 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(c14)
    bad = [rel for rel, want in c14.HASHES.items()
           if c14.sha(os.path.join(STG14, rel)) != want]
    assert not bad, f"봇 해시 불일치: {bad}"


def main():
    for name, fn in [("S1_NO-OP", s1), ("S2_HTTP200페이로드", s2), ("S3_HTTP404분기", s3),
                     ("S4_diff중복방지", s4), ("S5_오류KILL알림", s5), ("S6_kill_guard", s6),
                     ("S7_poll인증명령", s7), ("S8_봇무수정해시", s8)]:
        run(name, fn)
    n = sum(1 for _, ok, _ in RESULTS if ok)
    v = (f"VERDICT Stg16 OpsGuard | {n}/{len(RESULTS)} {'PASS' if n == len(RESULTS) else 'FAIL'}"
         f" — KillSwitch(단방향·자동복구금지)+Telegram(env전용·NO-OP안전판·중복방지 diff)"
         f"+가시성(status 4축·/status·/kill) | 봇 본체 무수정(S8 해시 10종) | 실발송 0(전부 mock)")
    body = [v, ""] + [f"[{'PASS' if ok else 'FAIL'}] {nm} | {er}" for nm, ok, er in RESULTS]
    body += ["", "[메시지 샘플 — 실발송 양식(머리에 [PAPER]/[LIVE] 태그 부착됨)]"]
    for k, label in [("start", "① 시작"), ("open", "② 진입"), ("close", "③ 청산"),
                     ("error", "④ 오류"), ("kill", "④ KILL"), ("heartbeat", "⑤ 하트비트"),
                     ("status", "/status 회신")]:
        if k in SAMPLES:
            body += [f"--- {label} ---", SAMPLES[k]]
    with open(os.path.join(HERE, "stg16_result.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(body) + "\n")
    print("\n".join(body))
    return 0 if n == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
