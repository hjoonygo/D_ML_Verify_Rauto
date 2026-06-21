@echo off
echo Set Rauto RBAC tokens machine-wide (run as Administrator, ONE time).
echo After this, OPEN A NEW admin cmd and run redeploy.bat so the server sees the tokens.
setx /M RAUTO_TOKENS "d498b724f6884c7609e74dd340139e8b:admin,61136f075e24e596b9327411:view,a02bd780ba8e449d756e30f4:view,c40a443a61544d8ced978a1c:view"
echo Done.
pause
