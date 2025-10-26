@echo off
title AI Interview Caller - Project Launcher
echo ================================================
echo    AI Interview Caller - Full Stack Project
echo ================================================
echo.

REM Check prerequisites
echo Checking prerequisites...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Node.js is not installed
    echo Please install Node.js 18+ from https://nodejs.org/
    pause
    exit /b 1
)

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed
    echo Please install Python 3.10+ from https://python.org/
    pause
    exit /b 1
)

echo ✓ Node.js and Python are available
echo.

echo What would you like to do?
echo.
echo 1. Start Backend Only (FastAPI server)
echo 2. Start Frontend Only (Next.js app)
echo 3. Start Both (Recommended for full experience)
echo 4. Setup Project (Install dependencies and configure)
echo 5. View Documentation
echo 6. Exit
echo.

set /p choice="Enter your choice (1-6): "

if "%choice%"=="1" goto start_backend
if "%choice%"=="2" goto start_frontend
if "%choice%"=="3" goto start_both
if "%choice%"=="4" goto setup_project
if "%choice%"=="5" goto view_docs
if "%choice%"=="6" goto exit
goto invalid_choice

:start_backend
echo Starting Backend...
cd backend
call start.bat
goto end

:start_frontend
echo Starting Frontend...
cd frontend
call start.bat
goto end

:start_both
echo Starting both Backend and Frontend...
echo.
echo Opening Backend in new window...
start "AI Interview Caller - Backend" cmd /c "cd backend && start.bat"

echo Waiting 5 seconds for backend to start...
timeout /t 5 /nobreak > nul

echo Opening Frontend in new window...
start "AI Interview Caller - Frontend" cmd /c "cd frontend && start.bat"

echo.
echo ✓ Both services are starting in separate windows
echo ✓ Backend: http://localhost:8000
echo ✓ Frontend: http://localhost:3000
echo ✓ API Docs: http://localhost:8000/docs
echo.
echo Press any key to exit this launcher...
pause > nul
goto end

:setup_project
echo Setting up project...
echo.

echo 1. Setting up Backend...
cd backend
if not exist ".env" (
    echo Creating .env file from template...
    copy .env.example .env
    echo ✓ Created backend/.env - Please configure your credentials
) else (
    echo ✓ Backend .env file already exists
)

echo Installing backend dependencies...
python -m venv venv 2>nul
call venv\Scripts\activate.bat
pip install -r requirements.txt
echo ✓ Backend dependencies installed

cd ..

echo.
echo 2. Setting up Frontend...
cd frontend
if not exist ".env.local" (
    echo Creating .env.local file from template...
    copy .env.example .env.local
    echo ✓ Created frontend/.env.local
) else (
    echo ✓ Frontend .env.local file already exists
)

echo Installing frontend dependencies...
npm install
echo ✓ Frontend dependencies installed

cd ..

echo.
echo ================================================
echo Setup Complete!
echo ================================================
echo.
echo Next steps:
echo 1. Configure your credentials in backend/.env:
echo    - Add your Twilio credentials
echo    - Add your OpenAI API key
echo    - Set candidate information
echo.
echo 2. For local development, install ngrok:
echo    - Download from https://ngrok.com/
echo    - Run: ngrok http 8000
echo    - Copy the https URL to WEBHOOK_BASE_URL in .env
echo.
echo 3. Run this script again and choose option 3 to start both services
echo.
pause
goto end

:view_docs
echo Opening project documentation...
echo.
echo Available documentation:
echo - Main README: README.md
echo - Backend README: backend/README.md
echo - Frontend: http://localhost:3000 (when running)
echo - API Documentation: http://localhost:8000/docs (when backend is running)
echo.
echo Opening README in default text editor...
start README.md
pause
goto end

:invalid_choice
echo Invalid choice. Please enter a number between 1-6.
pause
goto end

:exit
echo Goodbye!
goto end

:end
echo.
echo Thank you for using AI Interview Caller!