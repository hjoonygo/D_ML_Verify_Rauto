# -*- coding: utf-8 -*-
# [파일명] alert_telegram.py — read-only 1방향 텔레그램 발신 (Stg16)
# 코드길이: 약 60줄 | 내부버전: stg16_alert_telegram_v2 (AWS 발신불능 패치 2026-06-13)
# [v2 — AWS 실측 URLError 수습, 캡틴 의심 4순위 전부 반영]
#   ① env 토큰 .strip()+따옴표 제거(setx 시 공백/따옴표 유입 → URL 오염 차단)
#   ② POST 인코딩 JSON → urlencode(form) 전환 + charset 명시(getMe GET과의 차이 최소화)
#   ③ ProxyHandler({}) 무프록시 오프너 우선, 실패 시 기본 경로(프록시 env) 재시도
#   ④ timeout 10→15 | 발신불능 로그에 URLError reason 원문 표기(원인 확정용)
# [원칙] 토큰·chat_id = OS 환경변수 전용(평문 금지). 미설정 시 NO-OP. 절대 raise 없음.
import os, urllib.request, urllib.error, urllib.parse
import ops_common as oc


def _clean(v):
    return v.strip().strip('"').strip("'").strip()


def creds():
    return (_clean(os.environ.get("TELEGRAM_BOT_TOKEN", "")),
            _clean(os.environ.get("TELEGRAM_CHAT_ID", "")))


def _urlopen(req, timeout):
    """③ 무프록시 우선 → 실패 시 기본(프록시 env 적용) 재시도. HTTPError는 그대로 위로."""
    try:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({})).open(req, timeout=timeout)
    except urllib.error.HTTPError:
        raise
    except Exception:
        return urllib.request.urlopen(req, timeout=timeout)


def send(text):
    """발신. 반환: HTTP 상태코드(200/4xx) / None(NO-OP 또는 네트워크 불능)."""
    tok, chat = creds()
    if not tok or not chat:
        oc.olog(f"NO-OP(미설정) | {text}")
        return None
    data = urllib.parse.urlencode(
        {"chat_id": chat, "text": f"{oc.MODE_TAG} {text}"}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{tok}/sendMessage", data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"})
    try:
        with _urlopen(req, 15) as r:
            code = r.getcode()
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception as e:
        oc.olog(f"발신불능({type(e).__name__}: {getattr(e, 'reason', e)}) | {text}")
        return None
    oc.olog(f"발신 HTTP {code} | {text}")
    return code
