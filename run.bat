@echo off
chcp 65001 >/dev/null
echo Cleaning cache...
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>/dev/null
del /s /q *.pyc 2>/dev/null

echo Starting application...
C:\Users\Administrator\AppData\Local\Python\pythoncore-3.14-64\python.exe main.py
pause
