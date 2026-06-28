@echo off
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
git add -A
git commit -m "deploy"
git push origin HEAD:rfrauto
echo.
echo [deploy] pushed to origin/rfrauto. AWS auto-pulls and restarts within ~5 min.
