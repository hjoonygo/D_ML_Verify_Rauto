# Rauto OLD (b32) cleanup — RUN ON THE AWS BOX (RDP) in an ADMIN PowerShell window.
# Safe by design: it DISCOVERS first, SHOWS what it will remove, asks you to type DELETE,
# then stops the old control server (port 8787) + its service/scheduled tasks and removes
# the old Rauto folders. It KEEPS C:\BinanceData (Dauto data needed by Rauto2). ASCII only.
#
# How to use: RDP into the AWS machine -> open PowerShell as Administrator -> paste this whole
# script -> review the discovery -> type DELETE to confirm.

$ErrorActionPreference = 'SilentlyContinue'
Write-Host "===== Rauto OLD (b32) CLEANUP : DISCOVERY (nothing removed yet) =====" -ForegroundColor Cyan

# 1) Process(es) serving the old dashboard on port 8787
$pids = Get-NetTCPConnection -LocalPort 8787 -State Listen | Select-Object -ExpandProperty OwningProcess -Unique
Write-Host "`n[1] Port 8787 listener PID(s): $($pids -join ', ')"
$serverPaths = @()
foreach ($pp in $pids) {
    $ci = Get-CimInstance Win32_Process -Filter "ProcessId=$pp"
    if ($ci) { Write-Host ("    PID {0}: {1}" -f $pp, $ci.CommandLine); if ($ci.CommandLine) { $serverPaths += $ci.CommandLine } }
}

# 2) Services that look like Rauto
$svc = Get-Service | Where-Object { $_.Name -match 'rauto' -or $_.DisplayName -match 'rauto' }
Write-Host "`n[2] Rauto-like services:"
if ($svc) { $svc | Select-Object Name, Status, DisplayName | Format-Table -Auto | Out-String | Write-Host } else { Write-Host "    (none)" }

# 3) Scheduled tasks that look like Rauto
$tasks = Get-ScheduledTask | Where-Object { $_.TaskName -match 'rauto' -or $_.TaskPath -match 'rauto' }
Write-Host "[3] Rauto-like scheduled tasks:"
if ($tasks) { $tasks | Select-Object TaskName, State | Format-Table -Auto | Out-String | Write-Host } else { Write-Host "    (none)" }

# 4) Folders to remove: ONLY C:\Rauto<digits> (slot folders Rauto1..Rauto8).
#    Tightened regex '^Rauto\d+$' so it does NOT touch C:\Rauto2_incoming, C:\BinanceData, or a future deploy folder.
$folders = @()
$folders += Get-ChildItem 'C:\' -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^Rauto\d+$' }
Write-Host "[4] Folders that WILL be deleted:"
if ($folders) { $folders | ForEach-Object { Write-Host ("    " + $_.FullName) } } else { Write-Host "    (no C:\Rauto* folders found)" }
Write-Host "    KEEP (NOT deleting): C:\BinanceData  (Dauto market data, needed by Rauto2)" -ForegroundColor Yellow
if ($serverPaths) { Write-Host "`n    NOTE: the old server script path(s) above show where the b32 code lives." -ForegroundColor Yellow
                    Write-Host "    If that code folder is NOT under C:\Rauto*, delete it manually after this script." -ForegroundColor Yellow }

# ---- CONFIRM ----
$ans = Read-Host "`nType  DELETE  to STOP and REMOVE everything above (keeps C:\BinanceData)"
if ($ans -ne 'DELETE') { Write-Host "Aborted. Nothing changed." -ForegroundColor Red; return }

Write-Host "`n===== EXECUTING =====" -ForegroundColor Cyan
# Stop listeners
foreach ($pp in $pids) { Stop-Process -Id $pp -Force; Write-Host "stopped PID $pp" }
# Stop + delete services
foreach ($s in $svc) { Stop-Service $s.Name -Force; & sc.exe delete $s.Name | Out-Null; Write-Host "removed service $($s.Name)" }
# Remove scheduled tasks
foreach ($t in $tasks) { Unregister-ScheduledTask -TaskName $t.TaskName -Confirm:$false; Write-Host "removed task $($t.TaskName)" }
Start-Sleep -Seconds 2
# Delete folders
foreach ($f in $folders) { Remove-Item $f.FullName -Recurse -Force; if (Test-Path $f.FullName) { Write-Host "FAILED $($f.FullName) (in use?)" -ForegroundColor Red } else { Write-Host "deleted $($f.FullName)" } }

# ---- VERIFY ----
Start-Sleep -Seconds 2
Write-Host "`n===== VERIFY =====" -ForegroundColor Cyan
$v8787 = Get-NetTCPConnection -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue
$vFold = Get-ChildItem 'C:\' -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^Rauto\d+$' }
$vSvc  = Get-Service -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'rauto' -or $_.DisplayName -match 'rauto' }
$vTask = Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { $_.TaskName -match 'rauto' }
Write-Host ("  8787 listener : " + $(if ($v8787) { "STILL UP" } else { "gone" }))
Write-Host ("  Rauto# folders: " + (($vFold | Measure-Object).Count))
Write-Host ("  rauto services: " + (($vSvc  | Measure-Object).Count))
Write-Host ("  rauto tasks    : " + (($vTask | Measure-Object).Count))
$bin = Test-Path 'C:\BinanceData'
Write-Host ("  C:\BinanceData : " + $(if ($bin) { "KEPT (ok)" } else { "MISSING (!)" }))
if (-not $v8787 -and -not $vFold -and -not $vSvc -and -not $vTask) {
    Write-Host "`n  RESULT: SUCCESS - old Rauto (b32) fully removed." -ForegroundColor Green
} else {
    Write-Host "`n  RESULT: STILL PRESENT - some items remain (see above). May need manual delete or a reboot if files were in use." -ForegroundColor Red
}
Write-Host "===== DONE. C:\BinanceData kept. =====" -ForegroundColor Green
