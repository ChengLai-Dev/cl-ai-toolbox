@echo off
cd /d "%~dp0"

echo Deleting all files in Explain Docs\ ...
if exist "Explain Docs\*" del /f /q "Explain Docs\*" 2>nul

echo Deleting all files in Explain Scripts\ ...
if exist "Explain Scripts\*" del /f /q "Explain Scripts\*" 2>nul

echo Deleting all files in Explain Pics\ ...
if exist "Explain Pics\*" del /f /q "Explain Pics\*" 2>nul

echo Done.
