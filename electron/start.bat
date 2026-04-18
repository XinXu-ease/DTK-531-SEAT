@echo off
REM Quick start script for Chair Pet Electron App

echo ========================================
echo  Chair Pet Desktop - Quick Start
echo ========================================
echo.

REM Check if npm is installed
where npm >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Error: npm not found. Please install Node.js first.
    echo Visit: https://nodejs.org/
    pause
    exit /b 1
)

REM Install dependencies if node_modules doesn't exist
if not exist "node_modules" (
    echo Installing dependencies...
    call npm install
    if %ERRORLEVEL% NEQ 0 (
        echo Error: Failed to install dependencies
        pause
        exit /b 1
    )
)

echo.
echo Starting Chair Pet Desktop App...
echo.
echo Tips:
echo - Click the 📊 button on the floating window to open Dashboard
echo - Import your User ID in Dashboard
echo - Check MQTT connection status (green dot = connected)
echo.
echo Press Ctrl+C to stop the application.
echo.

REM Start the app
call npm start

pause
