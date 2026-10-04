@echo off
cd /d "%~dp0"
echo Starting Personal Finance Assistant...
start "" http://localhost:8501
.\.venv\Scripts\streamlit.exe run app.py --server.headless true --server.address 127.0.0.1 --browser.gatherUsageStats false
pause
