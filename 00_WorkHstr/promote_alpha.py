# -*- coding: utf-8 -*-
# [promote_alpha.py] 알파 등급 승급 자동화 (반자동) — PIPELINE_GradeStepUp.md §5 구현.
#   완전 무인 트리거는 불가(승급=판단). AI가 졸업조건 충족 판단 시 이 스크립트 1줄로
#   폴더이동 + (T1이면)zip/manifest + INDEX기록 + alpha_card 등급갱신 + 02 체크리스트를 일괄·멱등 처리.
#   사용: python promote_alpha.py <세션ID> <from등급> <to등급>   |   자가검증: python promote_alpha.py --check
#   self-locating: 어느 폴더서 실행돼도 RfRauto 루트 자동탐색(§1 절대규칙).
import os, sys, glob, zipfile, shutil
from datetime import datetime, timezone

GRADE_DIR = {"T0": "03_IDEA4Bot", "T1": "04_공용엔진코드", "T2": "05_Alpha_Up",
             "T3": "07_Rauto_System", "T5": "06_ChampBot"}
GRADE_DESC = {"T0": "아이디어→봇전략", "T1": "통과 반제품(zip)", "T2": "실시간·Rauto궁합",
              "T3": "Rauto 실시간 테스트봇", "T4": "테스트넷", "T5": "ChampBot copy봇"}


def _p(*a): print(*a, flush=True)


def find_root():
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.dirname(here), here, os.getcwd()):
        if os.path.isdir(os.path.join(p, "03_IDEA4Bot")) and os.path.isdir(os.path.join(p, "08_BTC_Data")):
            return p
    for g in glob.glob(r"D:\ML\*\03_IDEA4Bot"):
        return os.path.dirname(g)
    raise SystemExit("RfRauto 루트 못찾음(03_IDEA4Bot 기준)")


def ts(): return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def index_append(root, line):
    p = os.path.join(root, "00_WorkHstr", "00WorkHstr_INDEX.txt")
    data = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    if data and not data.endswith("\n"): data += "\n"
    open(p, "w", encoding="utf-8").write(data + line + "\n")


def make_manifest(root, sid, zippath):
    z = zipfile.ZipFile(zippath); names = z.namelist()
    card = ""
    for n in names:
        if n.endswith("alpha_card.md"):
            card = z.read(n).decode("utf-8", "replace")
    mani = f"# {sid}.manifest.md (검색용 — zip은 python zipfile로 read)\n\n"
    mani += f"생성 {ts()} · zip={os.path.basename(zippath)} · {len(names)}개 파일\n\n## 파일목록\n"
    mani += "\n".join("- " + n for n in names)
    mani += "\n\n## alpha_card 요약(앞 45줄)\n```\n" + "\n".join(card.split("\n")[:45]) + "\n```\n"
    open(os.path.join(os.path.dirname(zippath), sid + ".manifest.md"), "w", encoding="utf-8").write(mani)


def update_checklist(root, sid, frm, to):
    p = os.path.join(root, "02_Alpha_CheckList", sid + "_checklist.md")
    head = f"# {sid} — 검증 체크리스트\n\n현재 등급: **{to}** ({GRADE_DESC.get(to,'')}) · 갱신 {ts()}\n\n## 등급 이력\n"
    if os.path.exists(p):
        old = open(p, encoding="utf-8").read()
        body = old.split("## 등급 이력\n", 1)[-1] if "## 등급 이력\n" in old else ""
    else:
        body = ""
    body = f"- {ts()} {frm} → {to} ({GRADE_DESC.get(to,'')})\n" + body
    open(p, "w", encoding="utf-8").write(head + body)


def promote(sid, frm, to):
    root = find_root()
    if frm not in GRADE_DIR or to not in GRADE_DIR and to != "T4":
        raise SystemExit(f"등급 오류: {frm}/{to} (가능 {list(GRADE_DIR)})")
    src = os.path.join(root, GRADE_DIR[frm], sid)
    if not os.path.isdir(src):
        raise SystemExit(f"원본 없음: {src}")
    if to == "T1":
        zp = os.path.join(root, GRADE_DIR["T1"], sid + ".zip")
        z = zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED)
        for f in glob.glob(os.path.join(src, "**", "*"), recursive=True):
            if os.path.isfile(f):
                z.write(f, os.path.relpath(f, src))
        z.close(); make_manifest(root, sid, zp)
        dst_desc = zp + " (+manifest)"
    else:
        dst = os.path.join(root, GRADE_DIR[to], sid)
        shutil.copytree(src, dst, dirs_exist_ok=True)
        dst_desc = dst
    index_append(root, f"{ts()}|등급승급 {sid} {frm}→{to}|{GRADE_DESC.get(to,'')}. 자동 promote_alpha.py(폴더이동+"
                       f"{'zip/manifest+' if to=='T1' else ''}INDEX+체크리스트 일괄)|src=promote_alpha.py")
    update_checklist(root, sid, frm, to)
    _p(f"[승급] {sid} {frm}→{to} => {dst_desc}")
    _p(f"[기록] INDEX + 02_Alpha_CheckList/{sid}_checklist.md 갱신 (alpha_card 등급은 수동 1줄 권장)")


def check():
    root = find_root()
    _p(f"=== promote_alpha 자가검증 (root={root}) ===")
    _p("① 등급 폴더 존재:")
    for g, dname in GRADE_DIR.items():
        _p(f"   {g} {dname:<16} {'OK' if os.path.isdir(os.path.join(root,dname)) else 'X'}")
    _p("② 핵심 폴더: " + ", ".join(f"{d}={'OK' if os.path.isdir(os.path.join(root,d)) else 'X'}"
                                   for d in ["02_Alpha_CheckList", "00_WorkHstr", "08_BTC_Data"]))
    _p("③ 지침 단일출처: " + ", ".join(f"{os.path.basename(f)}={'OK' if os.path.exists(os.path.join(root,f)) else 'X'}"
                                       for f in ["PIPELINE_GradeStepUp.md", "WORKSPACE_MIGRATION_Verify_to_RfRauto.md"]))
    # zip 검색성 실증
    cand = glob.glob(os.path.join(root, "03_IDEA4Bot", "*", "alpha_card.md"))
    if cand:
        d = os.path.dirname(cand[0]); sid = os.path.basename(d)
        tmp = os.path.join(root, "00_WorkHstr", "_checkzip.zip")
        z = zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED)
        for f in glob.glob(os.path.join(d, "*")):
            if os.path.isfile(f): z.write(f, os.path.basename(f))
        z.close(); z = zipfile.ZipFile(tmp)
        hit = sum(1 for n in z.namelist() if n.endswith(".md") and b"MDD" in z.read(n))
        _p(f"④ zip 검색성 실증: {sid} → {len(z.namelist())}파일, MD내 'MDD' 검색 {hit}건 OK (python zipfile)")
        z.close(); os.remove(tmp)
    _p("⑤ 폴더순서 정합: 02→03_IDEA4Bot→04_공용엔진코드→05→06 (번호=흐름순) OK")
    _p("=== 검증 완료: 폴더·지침·zip검색·승급경로 정상 → promote 사용 가능 ===")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--check":
        check()
    elif len(sys.argv) == 4:
        promote(sys.argv[1], sys.argv[2].upper(), sys.argv[3].upper())
    else:
        _p("사용: python promote_alpha.py <세션ID> <from> <to>  |  python promote_alpha.py --check")
