# -*- coding: utf-8 -*-
# [파일명] ops_common.py — Stg16 OpsGuard 공통(경로해석·로그·모드태그)
# 코드길이: 약 40줄 | 내부버전: stg16_ops_common_v1
# [원칙] 봇 본체 무수정 — 외장 레이어. 경로는 env 우선 → AWS(C:\run_Rauto) → PC(Stg14 폴더).
import os, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
DAUTO_DIR = os.environ.get("RAUTO_DAUTO_DIR", r"C:\BinanceData")
KILL_FLAG = os.environ.get("RAUTO_KILL_FLAG", os.path.join(DAUTO_DIR, "kill.flag"))
OPS_LOG = os.environ.get("RAUTO_OPS_LOG", os.path.join(HERE, "ops_alert.log"))
MODE_TAG = "[LIVE]" if os.environ.get("RAUTO_MODE", "PAPER").upper() == "LIVE" else "[PAPER]"
TASKS = ["Rauto_Daily", "Dauto_Collector"]


def rauto_dir():
    """Stg14 산출물(원장·health·scorecard) 폴더 — env RAUTO_DIR → AWS → PC 순."""
    cands = [os.environ.get("RAUTO_DIR", ""), r"C:\run_Rauto",
             os.path.join(os.path.dirname(HERE), "07Prj_Ch4_RunAWS_Stg14_LivePaperWarmup"),
             HERE]
    for c in cands:
        if c and os.path.exists(os.path.join(c, "scorecard_daily.csv")):
            return c
    return HERE


def now_utc():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def olog(msg):
    line = f"{now_utc()} | {msg}"
    with open(OPS_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)
    return line
