@echo off
REM Debug script for candidate_id JSON testing (Windows)

echo 🔧 Candidate ID System Debug Script
echo ======================================
echo.

REM Test 1: Check if server is running
echo 1️⃣ Testing server connectivity...
curl -s http://localhost:8000/test-webhook >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ Server is running on port 8000
) else (
    echo ❌ Server is NOT running. Start with: cd backend ^&^& python main.py
    pause
    exit /b 1
)
echo.

REM Test 2: Test JSON parsing with debug endpoint
echo 2️⃣ Testing JSON parsing...
curl -X POST http://localhost:8000/test-json -H "Content-Type: application/json" -d "{\"candidate_id\": \"TEST_12345678\"}"
echo.
echo.

REM Test 3: Get actual candidates
echo 3️⃣ Getting list of candidates...
curl -s -X GET http://localhost:8000/list-candidates
echo.
echo.

REM Test 4: Provide example curl command
echo 4️⃣ Example curl command for calling a candidate:
echo Replace ACTUAL_CANDIDATE_ID with a real ID from step 3:
echo.
echo curl -X POST http://localhost:8000/call-candidate ^
echo   -H "Content-Type: application/json" ^
echo   -d "{\"candidate_id\": \"ACTUAL_CANDIDATE_ID\"}"
echo.

echo 🎯 Common Issues:
echo - Make sure to use double quotes in JSON: {\"candidate_id\": \"value\"}
echo - Include Content-Type header: -H "Content-Type: application/json"
echo - Use actual candidate_id from step 3, not placeholder text
echo - Escape quotes properly in command line

echo.
echo Press any key to exit...
pause >nul