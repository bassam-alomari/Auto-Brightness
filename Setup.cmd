@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto reuse
where py >nul 2>nul
if errorlevel 1 goto use_python
py -3 -m venv .venv
if errorlevel 1 goto failed
goto install
:use_python
python -m venv .venv
if errorlevel 1 goto failed
goto install
:reuse
echo Reusing the existing Python environment.
".venv\Scripts\python.exe" -c "import sys; assert sys.version_info >= (3,10)"
if errorlevel 1 goto failed
:install
echo Close Auto Brightness using Exit from its tray menu before installing updates.
".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 goto failed
echo Setup complete. Open Start.cmd to launch Auto Brightness.
pause
exit /b 0
:failed
echo Setup failed. Close Auto Brightness using Exit, then try again.
echo Existing environment was not deleted. Do not run venv creation over a running app.
echo Check the error above, Python 3.10+ and your internet connection.
pause
exit /b 1
