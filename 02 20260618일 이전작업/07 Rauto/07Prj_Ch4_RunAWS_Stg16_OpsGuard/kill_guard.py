# -*- coding: utf-8 -*-
# [파일명] kill_guard.py — Kill Switch 단방향 (schtasks Kill_Guard, 1분 간격)
# 코드길이: 약 55줄 | 내부버전: stg16_kill_guard_v1
# [동작] C:\BinanceData\kill.flag 존재 시 1회만:
#   ①자동기동 태스크(Rauto_Daily·Dauto_Collector) /DISABLE
#   ②미체결취소·전량청산 = stub(현 단계 페이퍼 — 로깅만, 실거래 전환 시 활성)
#   ③stg14_health.log·텔레그램에 ★KILL 1줄.
# [원칙] 해제는 캡틴 수동(flag 삭제 + 태스크 /ENABLE) — 자동복구 금지.
#   재처리방지: kill.flag.handled 마커(매분 재알림 방지). 마커는 flag와 같이 삭제.
import os, sys, subprocess
import ops_common as oc
import alert_telegram as tg

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def disable_task(name):
    if os.environ.get("RAUTO_KILL_TEST"):           # 사전실행 샌드박스: 실 schtasks 미호출
        return "TEST-SKIP"
    r = subprocess.run(["schtasks", "/Change", "/TN", name, "/DISABLE"],
                       capture_output=True, text=True)
    return "OK" if r.returncode == 0 else f"실패rc{r.returncode}"


def main():
    flag = oc.KILL_FLAG
    marker = flag + ".handled"
    if not os.path.exists(flag):
        return 0
    if os.path.exists(marker):
        return 0                                     # 이미 처리됨 — 매분 재알림 방지
    res = [f"{t}:{disable_task(t)}" for t in oc.TASKS]
    oc.olog("KILL stub: 미체결취소·전량청산 — 페이퍼 단계라 로깅만(실거래 전환 시 활성)")
    line = (f"★KILL {oc.now_utc()} | kill.flag 감지 | 태스크비활성 {' '.join(res)}"
            f" | 해제=수동(flag삭제+/ENABLE)")
    hl = os.path.join(oc.rauto_dir(), "stg14_health.log")
    with open(hl, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    tg.send(f"🚨 {line}")
    with open(marker, "w", encoding="utf-8") as f:
        f.write(oc.now_utc() + "\n")
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
