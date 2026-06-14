# -*- coding: utf-8 -*-
# [파일명] daily_health.py — Stg14 공식 1주 무인 일일점검 (캡틴 지시 2026-06-12 2)항)
# 코드길이: 약 65줄 | 내부버전: stg14_daily_health_v2 (v1 + ★RAUTO 미러, 캡틴 지시 2026-06-12 4)항)
# [역할] test 재관통 직후 실행. stg14_result.txt + scorecard_daily.csv를 파싱해
#   ①예외 ②갭 ③동치 3개 플래그를 점검, stg14_health.log에 1줄 append.
#   하나라도 깨지면 줄 머리에 ★긴급 표기(캡틴: 매일 자동 점검 항목).
# [v2 추가] 긴급 시 C:\BinanceData\dauto_health.log에도 '★RAUTO' 태그 줄 미러 append —
#   캡틴이 Dauto health 한 줄 확인으로 Rauto 이상까지 같이 감지. 정상(OK)일 땐 미러 안 씀.
import os, sys, datetime as dt
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "stg14_result.txt")
SCD = os.path.join(HERE, "scorecard_daily.csv")
LOG = os.path.join(HERE, "stg14_health.log")
DAUTO_HEALTH = r"C:\BinanceData\dauto_health.log"


def main():
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    probs = []
    txt = open(RES, encoding="utf-8").read() if os.path.exists(RES) else ""
    if "예외 0" not in txt:
        probs.append("예외발생")
    if "라이브≡리플레이: True" not in txt:
        probs.append("동치깨짐")
    gap_today = -1
    if os.path.exists(SCD):
        scd = pd.read_csv(SCD)
        if len(scd):
            last = scd.iloc[-1]
            gap_today = int(last.get("gap_n", 0))
            if gap_today > 0:
                probs.append(f"갭{gap_today}건")
            tail = (f"date={last['date']} bars={int(last['bars_in'])} "
                    f"bal_ts={last['bal_ts']} bal_sw={last['bal_sw']} "
                    f"oi_z={last.get('oi_z_cover', '')}% atr={last.get('atr_cover', '')}% "
                    f"damp={int(last.get('er_damp_n', 0))} blk={int(last.get('flt_blk_n', 0))}")
        else:
            probs.append("스코어카드 빈파일"); tail = ""
    else:
        probs.append("스코어카드 없음"); tail = ""
    head = "★긴급 " if probs else "OK "
    line = f"{head}{stamp} | {'·'.join(probs) if probs else '예외0·갭0·동치True'} | {tail}"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    if probs and os.path.isdir(os.path.dirname(DAUTO_HEALTH)):
        with open(DAUTO_HEALTH, "a", encoding="utf-8") as f:
            f.write(f"★RAUTO {line}\n")
    print(line)
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
