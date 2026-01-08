#!/bin/bash
# Script to run main.py with proper environment variables
# Usage: ./run_main.sh

# Log file for autostart debugging
LOG_DIR="$HOME/Desktop/IoT_health/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/autostart_$(date +%Y%m%d_%H%M%S).log"

# Redirect all output to log file
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=================================================="
echo "🚀 IoT Health Monitoring System - Startup Script"
echo "   Time: $(date)"
echo "   PWD: $PWD"
echo "   USER: $USER"
echo "=================================================="

# Change to script directory
cd "$(dirname "$0")"
echo "📂 Changed to directory: $PWD"

# Load environment variables from .env file if it exists
if [ -f ".env" ]; then
    echo "📄 Loading environment variables from .env file..."
    set -a
    source .env
    set +a
    echo "✅ Environment variables loaded"
else
    echo "⚠️  Warning: .env file not found at: $PWD/.env"
fi
    
# Set environment variables (export nếu chưa có trong ~/.bashrc)
export DISPLAY=:0

# MQTT Password (HiveMQ Cloud)
if [ -z "$MQTT_PASSWORD" ]; then
    echo "⚠️  Warning: MQTT_PASSWORD not set"
    echo "   Set it with: export MQTT_PASSWORD='your_password'"
fi

# MySQL Cloud Password (AWS RDS)
if [ -z "$MYSQL_CLOUD_PASSWORD" ]; then
    echo "⚠️  Warning: MYSQL_CLOUD_PASSWORD not set (admin user)"
fi

if [ -z "$MYSQL_PI_SYNC_PASSWORD" ]; then
    echo "⚠️  Warning: MYSQL_PI_SYNC_PASSWORD not set (Pi sync user)"
    echo "   Cloud sync will be disabled"
fi

echo ""
echo "📋 Environment Check:"
echo "   DISPLAY: $DISPLAY"
echo "   MQTT_PASSWORD: ${MQTT_PASSWORD:+***set***}"
echo "   MYSQL_CLOUD_PASSWORD: ${MYSQL_CLOUD_PASSWORD:+***set***}"
echo "   MYSQL_PI_SYNC_PASSWORD: ${MYSQL_PI_SYNC_PASSWORD:+***set***}"
echo ""
echo "=================================================="
echo "▶️  Starting application..."
echo "=================================================="
echo ""

# Check virtual environment exists
if [ ! -d ".venv" ]; then
    echo "❌ ERROR: Virtual environment not found at .venv"
    exit 1
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source .venv/bin/activate
echo "✅ Virtual environment activated: $(which python)"

# Check main.py exists
if [ ! -f "main.py" ]; then
    echo "❌ ERROR: main.py not found"
    exit 1
fi

# Run main.py
echo "🚀 Running main.py..."
python main.py

EXIT_CODE=$?
echo ""
echo "=================================================="
echo "⏹️  Application stopped with exit code: $EXIT_CODE"
echo "   Time: $(date)"
echo "=================================================="

exit $EXIT_CODE
