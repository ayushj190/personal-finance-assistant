#!/usr/bin/env bash
set -euo pipefail

echo "=================================================="
echo "Building Personal Finance Assistant macOS DMG"
echo "=================================================="

# Ensure script runs from repository root
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "Repository root: $REPO_ROOT"

# Clean old artifacts
echo "Cleaning previous build artifacts..."
rm -rf build dist

# Ensure PyInstaller and desktop dependencies are installed
echo "Verifying desktop packaging dependencies..."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements-desktop.txt

# Run PyInstaller bundling
echo "Compiling application bundle with PyInstaller..."
pyinstaller --clean desktop_app.spec

APP_PATH="dist/Personal Finance Assistant.app"
if [ ! -d "$APP_PATH" ]; then
    echo "Error: Application bundle not found at $APP_PATH" >&2
    exit 1
fi

echo "Application bundle created successfully at $APP_PATH"

# Create DMG staging directory
DMG_STAGING="dist/dmg_staging"
rm -rf "$DMG_STAGING"
mkdir -p "$DMG_STAGING"

echo "Populating DMG staging area..."
cp -R "$APP_PATH" "$DMG_STAGING/"
ln -s /Applications "$DMG_STAGING/Applications"

# Add Gatekeeper instructions (AC-6)
cat << 'EOF' > "$DMG_STAGING/QUICKSTART_GATEKEEPER.txt"
Personal Finance Assistant (macOS Standalone Edition)
=====================================================

Installation:
1. Drag "Personal Finance Assistant.app" into the "Applications" shortcut in this window.
2. Open your Applications folder in Finder.

First Launch (macOS Gatekeeper):
Because this open-source build is distributed without an expensive Apple Developer Paid Certificate:
- First launch: Right-click (or Control-click) "Personal Finance Assistant.app" in Applications and click "Open".
- When macOS displays the prompt ("macOS cannot verify the developer..."), click "Open".
- All subsequent launches can be opened with a regular double-click.

Terminal Quick Fix:
If macOS blocks execution, open Terminal and run:
  xattr -cr "/Applications/Personal Finance Assistant.app"

Your database and financial records are safely stored in:
  ~/Library/Application Support/PersonalFinanceAssistant/
EOF

DMG_OUTPUT="dist/PersonalFinanceAssistant.dmg"
echo "Creating compressed DMG at $DMG_OUTPUT..."
hdiutil create \
    -volname "Personal Finance Assistant" \
    -srcfolder "$DMG_STAGING" \
    -ov \
    -format UDZO \
    "$DMG_OUTPUT"

rm -rf "$DMG_STAGING"

echo "=================================================="
echo "Successfully built: $DMG_OUTPUT"
echo "=================================================="
