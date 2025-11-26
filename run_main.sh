#!/bin/bash
# Script to run main.py with proper environment variables
# Usage: ./run_main.sh

echo "=================================================="
echo "🚀 IoT Health Monitoring System - Startup Script"
echo "=================================================="

# Load environment variables from .env file if it exists
if [ -f ".env" ]; then
    echo "📄 Loading environment variables from .env file..."
    set -a
    source .env
    set +a
    echo "✅ Environment variables loaded"
else
    echo "⚠️  Warning: .env file not found"
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

# Activate virtual environment
source .venv/bin/activate

# Run main.py
python main.py

echo ""
echo "=================================================="
echo "⏹️  Application stopped"
echo "=================================================="
