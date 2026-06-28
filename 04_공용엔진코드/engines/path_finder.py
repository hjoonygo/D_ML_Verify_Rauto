# -*- coding: utf-8 -*-
# [path_finder.py] ★폴더 길찾기 도우미 (내비게이션) — Rauto 매매 본체 아님(매매 로직 0줄).
#   하는 일 = '내 위치(engines)에서 위로 올라가며 RfRauto 루트를 스스로 찾고', engines·research 폴더를 sys.path에 넣어
#            모듈끼리 하드코딩 절대경로(D:\...) 없이 서로 import 하게 함(§1 self-locating 절대규칙). 검증엔진 본문 무수정.
import os
import sys

_ENG_SUB = os.path.join("04_공용엔진코드", "engines")
_RESEARCH_SUB = os.path.join("03_IDEA4Bot", "260623_07_RfRautoAlphaUp")
_REFORM1_SUB = os.path.join("07_Rauto_System", "260625_01_Rauto_Sys_Reform")


def repo_root():
    """RfRauto 루트 절대경로. env RAUTO_REPO 우선 → 자기위치서 위로 marker(CLAUDE.md/03_IDEA4Bot) 탐색 → 폴백."""
    r = os.environ.get("RAUTO_REPO")
    if r and os.path.isdir(r):
        return r
    here = os.path.dirname(os.path.abspath(__file__))
    d = here
    for _ in range(6):
        if os.path.isfile(os.path.join(d, "CLAUDE.md")) or os.path.isdir(os.path.join(d, "03_IDEA4Bot")):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return os.path.dirname(os.path.dirname(here))   # 폴백: engines의 두 단계 위


def engines_dir():
    return os.path.join(repo_root(), _ENG_SUB)


def research_dir():
    return os.path.join(repo_root(), _RESEARCH_SUB)


def reform1_dir():
    return os.path.join(repo_root(), _REFORM1_SUB)


def ensure_paths():
    """engines·research를 sys.path 앞에 넣는다(중복 방지). 루트 반환.
       ★reform1(옛 session폴더)은 넣지 않는다 — 신호/결정 모듈이 engines로 승급됐으므로
         engines의 새 모듈이 우선되게 한다(옛 모듈이 먼저 잡히는 충돌 방지)."""
    root = repo_root()
    for sub in (_RESEARCH_SUB, _ENG_SUB):   # engines를 마지막에 넣어 sys.path 최우선(pos 0)
        p = os.path.join(root, sub)
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)
    return root
