# AWS ↔ PC ↔ 구글드라이브 파일교류 가이드 (드라이브 매핑 대신 '전송/동기화')

## 왜 드라이브 문자 매핑(D:/G:)을 안 쓰나
- PC의 D:를 AWS에 매핑 = PC가 절전/재부팅하면 끊김(불안정).
- 구글드라이브(G:)를 서버에 = 데스크톱 앱 필요 + 구글이 서버 로그인 차단 가능 = 서버 비권장.
- 정석 = **파일 전송(Taildrop)** + **서버→클라우드 동기화(rclone)**. 둘 다 Tailscale 기반으로 안정적.

## A) PC D: ↔ AWS  — Tailscale Taildrop (검증됨)
### PC → AWS 보내기 (PC에서)
    "C:\Program Files\Tailscale\tailscale.exe" file cp <보낼파일> ec2amaz-cor6gpg:
### AWS에서 받기 (AWS에서)
    "C:\Program Files\Tailscale\tailscale.exe" file get C:\Rauto2_incoming\
  (C:\Rauto2_incoming 폴더에 받은 파일이 떨어짐. 폴더 미리 만들어두기.)
### AWS → PC 보내기 (AWS에서)
    "C:\Program Files\Tailscale\tailscale.exe" file cp <파일> ai-ml:
  PC에서 받기: tailscale file get D:\ML\RfRauto\_incoming\

## B) AWS Dauto 결과물 → 구글드라이브 백업  — rclone (서버→클라우드 정석)
※ rclone은 G: 드라이브 문자 없이 구글드라이브 클라우드에 직접 올림. PC의 G:에도 자동 동기화돼 나타남.

### 1) AWS에 rclone 설치 (AWS PowerShell 관리자)
    winget install Rclone.Rclone
  (winget 없으면 https://rclone.org/downloads/ 의 Windows zip 받아 C:\rclone\rclone.exe 압축해제)

### 2) 구글드라이브 원격 1회 설정 (AWS에서, 브라우저 OAuth)
    rclone config
  - n (new) → 이름: gdrive → 종류: drive(구글드라이브) → client_id/secret 비워둠(엔터)
  - scope: 1 (전체) → 나머지 엔터 → "Use web browser to authenticate?" y → 브라우저 로그인 승인
  - 확인 후 q (종료)

### 3) 백업 실행 (AWS에서)
    rclone copy "C:\BinanceData" gdrive:Dauto_Backup --progress
  (C:\BinanceData = Dauto 결과물 폴더. gdrive:Dauto_Backup = 구글드라이브 안 폴더.)

### 4) 자동 백업 스케줄 (AWS 작업 스케줄러, 예: 매시간)
    schtasks /create /tn "DautoBackupGDrive" /tr "\"C:\Program Files\rclone\rclone.exe\" copy \"C:\BinanceData\" gdrive:Dauto_Backup" /sc hourly /ru SYSTEM

## C) Rauto2를 AWS에 올릴 때 (배포)
- PC에서 Rauto2 묶음(zip) 만들기 → Taildrop으로 AWS 전송 → AWS C:에 풀고 실행.
- 드라이브 매핑 불필요. AWS는 C:만 쓰는 설계 유지.
