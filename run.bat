@echo off
cd /d "%~dp0"

if "%~1"=="--demo" (
    set PFA_DEMO=1
    if not exist "data\demo.db" (
        echo Seeding demo database...
        .\.venv\Scripts\python.exe scripts\seed_demo.py
    )
)

echo Starting Personal Finance Assistant...
start msedge http://localhost:8501
.\.venv\Scripts\streamlit.exe run app.py --server.headless true --server.address 127.0.0.1 --browser.gatherUsageStats false
pause
