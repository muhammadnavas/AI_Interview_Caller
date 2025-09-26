@echo off
start "ngrok" cmd /c "ngrok http 8000"
timeout /t 3 /nobreak >nul
python main.py
pause
