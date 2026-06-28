@echo off
REM === Check whether OLD Rauto (b32) is gone. Double-click anytime. ===
powershell -NoProfile -Command "$p=Get-NetTCPConnection -LocalPort 8787 -State Listen -EA 0; $f=Get-ChildItem 'C:\' -Directory -EA 0 | ?{$_.Name -match '^Rauto\d+$'}; $s=Get-Service -EA 0 | ?{$_.Name -match 'rauto'}; $t=Get-ScheduledTask -EA 0 | ?{$_.TaskName -match 'rauto'}; Write-Host ('8787 listener : '+$(if($p){'STILL UP'}else{'gone'})); Write-Host ('Rauto# folders: '+(($f|Measure-Object).Count)); Write-Host ('rauto services: '+(($s|Measure-Object).Count)); Write-Host ('rauto tasks   : '+(($t|Measure-Object).Count)); Write-Host ('C:\BinanceData: '+$(if(Test-Path 'C:\BinanceData'){'KEPT (ok)'}else{'MISSING (!)'})); if(-not $p -and -not $f -and -not $s -and -not $t){Write-Host 'RESULT: SUCCESS - old Rauto gone' -ForegroundColor Green}else{Write-Host 'RESULT: STILL PRESENT' -ForegroundColor Red}"
echo.
pause
