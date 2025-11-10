@echo off
REM Build script for Dark API Tester (Windows)
echo Cleaning old builds...
if exist build rmdir /S /Q build
if exist dist rmdir /S /Q dist
if exist main.spec del /Q main.spec

echo Building .exe with PyInstaller...
pyinstaller --onefile --noconsole --add-data "asserts;asserts" --add-data "data;data" --icon="asserts\icons\app.ico" main.py

echo Build finished.
pause
