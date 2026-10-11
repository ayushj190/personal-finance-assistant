@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONPATH=%~dp0
.\.venv\Scripts\pytest.exe %*
