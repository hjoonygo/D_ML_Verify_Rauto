# -*- coding: utf-8 -*-
# [rauto2_autopull.py] AWS 무인 자동배포 (캡틴 지시 2026-06-28).
#   스케줄 태스크 Rauto2Deploy가 N분마다 SYSTEM으로 호출 → git(rfrauto) 변경 감지 시:
#     ① git reset --hard origin/rfrauto (코드만 갱신·시크릿/데이터는 .gitignore로 보존)
#     ② 문법검증(py_compile) — ★깨진 커밋이면 재시작 '안 함'(기존 서버 유지 = AWS 안전)
#     ③ 통과 시 Rauto2Server 태스크 재시작
#   self-locating(§1): ROOT = 이 파일 기준 3단계 위(=C:\Rauto2). 하드코딩 절대경로 의존 최소.
import subprocess
import os
import py_compile
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))   # ...\Rauto2\07_Rauto_System\260626_02_Rauto2_Sys → C:\Rauto2
LOG = os.path.join(ROOT, "rauto2_deploy.log")


def log(m):
    line = "%s  %s" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), m)
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def git(*a):
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")


def main():
    git("fetch", "origin", "rfrauto")
    local = git("rev-parse", "HEAD").stdout.strip()
    remote = git("rev-parse", "origin/rfrauto").stdout.strip()
    if not remote:
        log("FETCH FAIL (origin/rfrauto 없음) — PAT/네트워크 점검")
        return
    if local == remote:
        return   # 변경 없음(조용히 종료)
    log("change %s -> %s : pull 시작" % (local[:8], remote[:8]))
    r = git("reset", "--hard", "origin/rfrauto")
    if r.returncode != 0:
        log("reset 실패: %s" % r.stderr.strip()[:200])
        return
    # ★문법검증 — 깨진 커밋이면 재시작 보류(기존 서버 유지)
    targets = [
        os.path.join(ROOT, "07_Rauto_System", "260626_02_Rauto2_Sys", "260626_02_Rauto2_Sys_server.py"),
        os.path.join(ROOT, "04_공용엔진코드", "engines", "rauto_live.py"),
    ]
    for f in targets:
        if os.path.exists(f):
            try:
                py_compile.compile(f, doraise=True)
            except Exception as e:
                log("SYNTAX FAIL %s: %s — 재시작 보류(기존 유지)" % (os.path.basename(f), str(e)[:160]))
                return
    subprocess.run(["schtasks", "/End", "/TN", "Rauto2Server"], capture_output=True)
    subprocess.run(["schtasks", "/Run", "/TN", "Rauto2Server"], capture_output=True)
    log("DEPLOYED %s + Rauto2Server 재시작 완료" % remote[:8])


if __name__ == "__main__":
    main()
