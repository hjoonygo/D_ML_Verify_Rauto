# -*- coding: utf-8 -*-
# [ops_common.py] 슬롯1(R1) 격리본. 태그 [R1] · 경로·kill.flag 모두 C:\Rauto1로 격리(기존 인스턴스 무영향).
import os, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
DAUTO_DIR = os.environ.get("RAUTO_DAUTO_DIR", r"C:\BinanceData")
KILL_FLAG = os.environ.get("RAUTO_KILL_FLAG", os.path.join(HERE, "kill.flag"))   # ★자체 kill.flag(전역 아님)
OPS_LOG = os.environ.get("RAUTO_OPS_LOG", os.path.join(HERE, "ops_alert.log"))
MODE_TAG = os.environ.get("RAUTO_MODE", "[R1]")
TASKS = ["Rauto1", "Dauto_Collector"]


def rauto_dir():
    cands = [os.environ.get("RAUTO_DIR", ""), HERE]
    for c in cands:
        if c and os.path.exists(os.path.join(c, "state.json")):
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
