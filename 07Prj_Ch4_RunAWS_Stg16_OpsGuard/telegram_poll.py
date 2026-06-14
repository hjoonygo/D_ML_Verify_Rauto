# -*- coding: utf-8 -*-
# [파일명] telegram_poll.py — /status·/kill 미니 명령 폴링 (schtasks Telegram_Poll, 1분)
# 코드길이: 약 70줄 | 내부버전: stg16_telegram_poll_v1
# [공격면 최소화] 동일 chat_id 외 전부 거부·로그. /status·/kill 외 입력 무시.
#   kill은 단방향(flag 생성만) — 해제·재가동 명령 없음(자동복구 금지 원칙).
#   환경변수 없으면 NO-OP(개발 안전판).
import os, sys, json, urllib.request
import ops_common as oc
import alert_telegram as tg
from ops_status import build_status

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PSTATE = os.environ.get("RAUTO_POLL_STATE", os.path.join(oc.HERE, "ops_poll_state.json"))


def get_updates(tok, offset):
    url = f"https://api.telegram.org/bot{tok}/getUpdates?timeout=0&offset={offset}"
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.load(r)


def handle(text):
    t = (text or "").strip().lower()
    if t == "/status":
        tg.send("📊 상태\n" + build_status())
        return "status"
    if t == "/kill":
        with open(oc.KILL_FLAG, "w", encoding="utf-8") as f:
            f.write(f"telegram /kill {oc.now_utc()}\n")
        tg.send(f"🚨 kill.flag 생성됨 {oc.now_utc()} — Kill_Guard가 1분 내 태스크 비활성. "
                f"해제는 수동(flag 삭제+/ENABLE)")
        return "kill"
    return None                                      # 그 외 입력 전부 무시


def main():
    tok, chat = tg.creds()
    if not tok or not chat:
        oc.olog("poll NO-OP(미설정)")
        return 0
    st = {"offset": 0}
    if os.path.exists(PSTATE):
        st = json.load(open(PSTATE, encoding="utf-8"))
    try:
        data = get_updates(tok, st.get("offset", 0))
    except Exception as e:
        oc.olog(f"poll 불능({type(e).__name__})")
        return 0
    for u in data.get("result", []):
        st["offset"] = u["update_id"] + 1
        msg = u.get("message") or {}
        sender = str((msg.get("chat") or {}).get("id", ""))
        if sender != str(chat):
            oc.olog(f"poll 거부 chat_id={sender}")
            continue
        act = handle(msg.get("text"))
        if act:
            oc.olog(f"poll 명령처리 {act}")
    with open(PSTATE, "w", encoding="utf-8") as f:
        json.dump(st, f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
