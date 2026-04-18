#!/bin/bash

# Quick start script for Chair Pet Electron App (Linux/Mac)

echo "========================================"
echo " Chair Pet Desktop - Quick Start"
echo "========================================"
echo ""

# Check if npm is installed
if ! command -v npm &> /dev/null; then
    echo "Error: npm not found. Please install Node.js first."
    echo "Visit: https://nodejs.org/"
    exit 1
fi

# Install dependencies if node_modules doesn't exist
if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
    if [ $? -ne 0 ]; then
        echo "Error: Failed to install dependencies"
        exit 1
    fi
fi

echo ""
echo "Starting Chair Pet Desktop App..."
echo ""
echo "Tips:"
echo "- Click the 📊 button on the floating window to open Dashboard"
echo "- Import your User ID in Dashboard"
echo "- Check MQTT connection status (green dot = connected)"
echo ""
echo "Press Ctrl+C to stop the application."
echo ""

# Start the app
npm start
