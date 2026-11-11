@echo off
rem Dual arm operator interface on Windows: runs inside WSL and shows through WSLg.
rem Requires the workspace to be built in WSL first (bash scripts/build.sh).
rem Pass --monitor for a watch-only window, or --fake for demonstration data.
for /f "usebackq delims=" %%i in (`wsl wslpath -a "%~dp0.."`) do set "WS=%%i"
if "%WS%"=="" (
  echo WSL is not available or the workspace path could not be converted.
  pause
  exit /b 1
)
wsl -e bash -lc "cd '%WS%' && source install/setup.bash && exec ros2 run dual_arm_hmi hmi %*"
if errorlevel 1 pause
