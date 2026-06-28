---
name: ml-root-multi-business-layout
description: D:\ML = 전 개발사업 루트. 00AI_SYS=AI/PC/AWS 공통인프라. 사업별 폴더 분리(Verify=Rauto). 공통규칙은 상위 CLAUDE.md, 사업별은 각 memory
metadata:
  type: project
---

캡틴 비전(2026-06-21 결정): **D:\ML 를 모든 개발사업의 루트(기본폴더)** 로 쓴다. 자동매매 퀀트투자를 섹터별로 확장 예정 — 국내주식·미국주식·해외자산 등(분할·정기 리밸런싱).

**폴더 레이아웃:**
```
D:\ML\
 ├ 00AI_SYS\        ← ★AI·PC·AWS 공통 인프라(어느 사업에도 비종속). 폴더명 캡틴확정 '00AI_SYS'.
 │   ├ claude_restore\  ssh_keys\  aws_inventory\  docs\   (=OS포맷 부활키트)
 ├ CLAUDE.md        ← (추후) 전사업 공통 규칙. 클로드가 상위 CLAUDE.md를 누적 자동로드하는 동작 활용.
 ├ Verify\          ← 사업1 Rauto (※추후 'Rauto' 등으로 개명 예정). .claude\·memory\·CLAUDE.md(Rauto특수)
 ├ KrEquity\ UsEquity\ GlobalAsset\  ← (미래) 섹터별 퀀트 사업
```

**설계 원칙 2:**
1. 공통 인프라(클로드설정·AWS키·OS부활)는 사업폴더 밖 `00AI_SYS`에. Verify 개명/정리에 안 휩쓸림.
2. 메모리·규칙 2층: **공통 행동노하우**(캡틴스타일·bat규칙·self-locating·저장위치)는 추후 상위 `D:\ML\CLAUDE.md`로, **사업별 기술사실**은 각 사업 `memory\`(autoMemoryDirectory)로 분리. 미국주식 작업 시 공통규칙만 상속, Rauto 비용/해시는 안 딸려옴.

**미결(추후 처리):**
- Verify→신규명 개명 시 `autoMemoryDirectory`(현 D:/ML/Verify/memory)와 CLAUDE.md 속 D:\ML\verify 절대경로 일괄 갱신 필요.
- 현재 CLAUDE.md는 공통+Rauto 혼재 → 사업 확장 시 공통부를 D:\ML\CLAUDE.md로 분리.

관련: [[claude-config-on-d-multiboot]]
