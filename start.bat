@echo off
REM 清理 Python 缓存并启动应用

echo Cleaning Python cache...
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
del /s /q *.pyc 2>nul

echo.
echo Starting IPTV Player...
echo.

python main.py

pause
