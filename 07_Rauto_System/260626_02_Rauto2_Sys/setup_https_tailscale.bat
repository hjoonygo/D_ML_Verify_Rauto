@echo off
REM Rauto2 HTTPS via Tailscale Serve (valid cert) for full-screen PWA on Android.
REM Run once per machine. Persists across reboots. Requires Tailscale logged in + HTTPS enabled in admin.
set PORT=8788
"%ProgramFiles%\Tailscale\tailscale.exe" serve --bg %PORT%
"%ProgramFiles%\Tailscale\tailscale.exe" serve status
