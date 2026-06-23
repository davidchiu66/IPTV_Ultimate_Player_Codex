@echo off
chcp 65001 >nul
setlocal

set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"

set "PYTHON_EXE=python"
if exist "%LocalAppData%\Python\pythoncore-3.14-64\python.exe" (
    set "PYTHON_EXE=%LocalAppData%\Python\pythoncore-3.14-64\python.exe"
)

echo Cleaning Python cache...
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul
del /s /q *.pyc 2>nul

echo Checking Python dependencies...
"%PYTHON_EXE%" -c "import PySide6" >nul 2>nul
if errorlevel 1 (
    echo.
    echo The selected Python environment does not have PySide6 installed:
    echo   "%PYTHON_EXE%"
    echo.
    echo Please run:
    echo   "%PYTHON_EXE%" -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo.
echo Starting IPTV Ultimate Player...
echo Python: "%PYTHON_EXE%"
echo Args: %*
echo.

"%PYTHON_EXE%" pyside_main.py %*
pause
