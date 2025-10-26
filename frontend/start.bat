@echo off
echo Starting AI Interview Caller Frontend...
echo.

REM Check if Node.js is available
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Node.js is not installed or not in PATH
    echo Please install Node.js 18+ and try again
    pause
    exit /b 1
)

REM Check if npm is available
npm --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: npm is not available
    echo Please install Node.js with npm and try again
    pause
    exit /b 1
)

REM Install dependencies if node_modules doesn't exist
if not exist "node_modules" (
    echo Installing dependencies...
    npm install
    if %errorlevel% neq 0 (
        echo ERROR: Failed to install dependencies
        pause
        exit /b 1
    )
)

REM Check for .env.local file
if not exist ".env.local" (
    echo.
    echo NOTICE: .env.local file not found
    echo Using default API base URL: http://localhost:8000
    echo Copy .env.example to .env.local if you need custom configuration
    echo.
)

REM Start the development server
echo.
echo Starting Next.js development server...
echo Frontend will be available at: http://localhost:3000
echo Make sure the backend is running at: http://localhost:8000
echo.
echo Press Ctrl+C to stop the server
echo.

npm run dev

pause