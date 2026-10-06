@echo off
rem Double-click to start Touff (no console window). She lives in the tray.
start "" "%~dp0.venv\Scripts\pythonw.exe" -m touff %*
