# Rauto2 git 무인 자동배포 — 설정·사용법 (캡틴 지시 2026-06-28)

> 목적: **매번 파일별 복붙 노가다 끝.** PC `git push` → AWS가 5분마다 알아서 당겨서(코드만) 재시작. 깨진 커밋이면 재시작 안 함(안전).

## 구조
- PC: `deploy.bat` = `git add → commit → push origin rfrauto` (1클릭/1줄)
- AWS: 스케줄 태스크 `Rauto2Deploy` = `rauto2_autopull.py`를 5분마다 SYSTEM으로 실행 → git 변경 시 `reset --hard origin/rfrauto` + **문법검증** + 통과 시 `Rauto2Server` 재시작
- 시크릿(`rauto_secrets.txt`)·런타임상태·대용량데이터 = `.gitignore` 제외 → **자동pull이 안 건드림**(보존)

---

## ★최초 1회만 (AWS RDP PowerShell · 그 후 영원히 무인)
아래를 **PAT·PY 두 값만 채워** 한 번에 붙여넣기:

```powershell
$PAT = "ghp_여기에_GitHub토큰"      # github.com/settings/tokens → 'repo' 권한 classic 토큰
$PY  = "C:\Users\Administrator\AppData\Local\Programs\Python\Python310\python.exe"   # ← run_aws.bat의 python 전체경로와 동일하게

cd C:\Rauto2
git init
git config user.email "hjoonygo@gmail.com"
git config user.name  "hjoonygo"
git remote remove origin 2>$null
git remote add origin "https://$PAT@github.com/hjoonygo/D_ML_Verify_Rauto.git"
git fetch origin rfrauto
git reset --hard origin/rfrauto
git branch -f rfrauto origin/rfrauto; git checkout rfrauto 2>$null

# 5분마다 무인 자동배포 태스크 등록
schtasks /Create /TN Rauto2Deploy /TR "`"$PY`" `"C:\Rauto2\07_Rauto_System\260626_02_Rauto2_Sys\rauto2_autopull.py`"" /SC MINUTE /MO 5 /RU SYSTEM /F

# 지금 즉시 1회 배포(현재 코드=REVoi@ETF·색상통일·청산가 전부 반영) + 서버 재시작
schtasks /Run /TN Rauto2Deploy
```

→ 실행 후 ~1분 뒤 폰 새로고침 = **REVoi@ETF·색상·청산가 반영**. 이게 마지막 수동작업.

---

## 이후 배포 (영원히)
- **PC에서**: `deploy.bat` 더블클릭 (또는 `git push origin HEAD:rfrauto`)
- **AWS**: 5분 내 자동 pull + 재시작. 손 안 댐.
- 즉시 반영 원하면 AWS서 `schtasks /Run /TN Rauto2Deploy` 1줄(선택).

## 로그·점검
- 배포 로그 = `C:\Rauto2\rauto2_deploy.log` (언제 무엇이 배포됐는지).
- 태스크 확인 = `schtasks /Query /TN Rauto2Deploy`.

## 주의(정직)
- private repo라 **PAT 1회** 필요(URL에 저장 — private 서버라 허용 수준).
- `$PY`가 run_aws.bat과 다르면 SYSTEM서 python 못 찾아 실패(STATE Dauto 사고 동일) → **반드시 동일 전체경로**.
- git이 AWS에 system-wide 설치돼 있어야 SYSTEM 태스크서 동작(보통 OK).
- 완전무인이라 **깨진 커밋 push 시** 자동pull이 받지만 — 문법검증 실패면 **재시작 보류(기존 서버 유지)**라 다운 안 됨. (앵커·런타임 로직 버그까진 못 잡으니 push 전 로컬 확인 권장.)
