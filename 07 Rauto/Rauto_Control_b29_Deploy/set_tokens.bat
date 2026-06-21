@echo off
echo Set Rauto RBAC tokens machine-wide (run as Administrator, ONE time).
echo Token format: TOKEN:ROLE  or  TOKEN:ROLE:YYYY-MM-DD (expiry; after that date the link auto-dies).
echo Admin token below = no expiry. Viewer tokens below expire on 2026-09-19 (3 months).
echo To revoke a viewer early: delete that token from the line below and run this bat again, then redeploy.bat.
setx /M RAUTO_TOKENS "d498b724f6884c7609e74dd340139e8b:admin,61136f075e24e596b9327411:view:2026-09-19,a02bd780ba8e449d756e30f4:view:2026-09-19,c40a443a61544d8ced978a1c:view:2026-09-19"
echo Done. Open a NEW admin cmd and run redeploy.bat.
pause
