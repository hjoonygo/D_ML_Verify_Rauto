# -*- coding: utf-8 -*-
# [파일명] ops_common.py — Stg17 ImpatientFork 격리본 (Stg16 ops_common 1:1 + 태그만 변경)
# [분기 변경] MODE_TAG의 PAPER 태그를 "[PAPER·IMP]"로 변경 → 같은 텔레그램 챗에서 라이브(기존)와 구분.
#   그 외(경로해석 rauto_dir/olog/now_utc) Stg16과 동일. 봇 본체 무수정 — 외장 레이어.
# [격리 주의] run_daily.bat이 RAUTO_DIR=분기폴더·RAUTO_OPS_STATE=분기폴더로 강제하므로
#   rauto_dir()는 분기 폴더의 scorecard를 읽고, 라이브(C:\run_Rauto)를 절대 안 건드린다.
import os, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
DAUTO_DIR = os.environ.get("RAUTO_DAUTO_DIR", r"C:\BinanceData")
KILL_FLAG = os.environ.get("RAUTO_KILL_FLAG", os.path.join(DAUTO_DIR, "kill.flag"))
OPS_LOG = os.environ.get("RAUTO_OPS_LOG", os.path.join(HERE, "ops_alert.log"))
MODE_TAG = "[LIVE]" if os.environ.get("RAUTO_MODE", "PAPER").upper() == "LIVE" else "[PAPER·IMP]"
TASKS = ["Rauto_Impatient", "Dauto_Collector"]


def rauto_dir():
    """Stg17 분기 산출물(원장·health·scorecard) 폴더 — env RAUTO_DIR 우선(분기 격리), 그 다음 HERE."""
    cands = [os.environ.get("RAUTO_DIR", ""), HERE]
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
