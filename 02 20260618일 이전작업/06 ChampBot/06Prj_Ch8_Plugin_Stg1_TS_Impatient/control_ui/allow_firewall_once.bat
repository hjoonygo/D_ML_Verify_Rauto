@echo off
REM Run this ONCE as Administrator (right-click -> Run as administrator).
REM Allows the phone on the same Wi-Fi to reach port 8787.
netsh advfirewall firewall add rule name="Rauto Control 8787" dir=in action=allow protocol=TCP localport=8787
echo.
echo Done: inbound TCP port 8787 is now allowed.
pause
