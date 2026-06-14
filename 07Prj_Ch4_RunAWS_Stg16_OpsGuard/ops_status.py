# -*- coding: utf-8 -*-
# [파일명] ops_status.py — '돌고 있는지' 4축 즉답 (status_check.bat·/status 공용)
# 코드길이: 약 55줄 | 내부버전: stg16_ops_status_v1
# [4축] ①schtasks 두 태스크 상태·Last·Next ②Dauto 최근 행 시각
#   ③stg14_health 마지막 줄 ④scorecard 마지막 행
import os, sys, csv, io, glob, subprocess
import ops_common as oc

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def task_line(name):
    r = subprocess.run(["schtasks", "/Query", "/TN", name, "/V", "/FO", "CSV", "/NH"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        return f"{name}: 미등록"
    row = next(csv.reader(io.StringIO(r.stdout.strip().splitlines()[0])))
    # schtasks /V /FO CSV 고정 컬럼순(로캘 무관):
    # 0Host 1TaskName 2NextRun 3Status 4LogonMode 5LastRun 6LastResult ...
    return f"{name}: {row[3]} | Last {row[5]} (rc {row[6]}) | Next {row[2]}"


def _last_line(path):
    if not os.path.exists(path):
        return None
    body = open(path, encoding="utf-8").read().strip()
    return body.splitlines()[-1] if body else None


def build_status():
    lines = [task_line(t) for t in oc.TASKS]
    fs = sorted(glob.glob(os.path.join(oc.DAUTO_DIR, "BTCUSDT_1m_*.csv")))
    if fs:
        last = _last_line(fs[-1]) or "(빈파일)"
        lines.append(f"Dauto 최근행: {last.split(',')[0]} ({os.path.basename(fs[-1])})")
    else:
        lines.append(f"Dauto CSV 없음: {oc.DAUTO_DIR}")
    rd = oc.rauto_dir()
    lines.append("health: " + (_last_line(os.path.join(rd, "stg14_health.log")) or "없음"))
    sc = _last_line(os.path.join(rd, "scorecard_daily.csv"))
    lines.append("scorecard: " + (sc if sc and not sc.startswith("date,") else "빈파일/없음"))
    return "\n".join(lines)


if __name__ == "__main__":
    print(build_status())
