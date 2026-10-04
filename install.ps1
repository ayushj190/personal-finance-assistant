# Windows 11 Install & Setup Script
$ErrorActionPreference = "Stop"

Write-Host "Setting up Personal Finance Assistant..." -ForegroundColor Cyan

# 1. Check Python
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Error "Python was not found in PATH. Please install Python 3.12+."
    exit 1
}

# 2. Setup Venv
if (-not (Test-Path ".venv")) {
    Write-Host "Creating Python virtual environment (.venv)..." -ForegroundColor Yellow
    python -m venv .venv
}

# 3. Pip install
Write-Host "Installing requirements..." -ForegroundColor Yellow
.\.venv\Scripts\pip install -r requirements.txt

# 4. Migrate DB
Write-Host "Initializing SQLite database and views..." -ForegroundColor Yellow
.\.venv\Scripts\python -c "from db.database import migrate; migrate(); print('Database ready.')"

# 5. Create Desktop shortcut
$shortcutPath = "$([Environment]::GetFolderPath('Desktop'))\Personal Finance Assistant.lnk"
$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "$PSScriptRoot\run.bat"
$shortcut.WorkingDirectory = "$PSScriptRoot"
$shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,220"
$shortcut.Save()

Write-Host "Installation completed successfully! Desktop shortcut created." -ForegroundColor Green
