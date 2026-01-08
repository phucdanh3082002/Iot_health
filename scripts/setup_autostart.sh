#!/bin/bash
# Script to setup autostart for IoT Health Monitor on Raspberry Pi OS Bookworm
# Run this once: ./scripts/setup_autostart.sh

echo "=================================================="
echo "🔧 IoT Health Monitor - Autostart Setup"
echo "=================================================="
echo ""

PROJECT_DIR="/home/pi/Desktop/IoT_health"
AUTOSTART_DIR="$HOME/.config/autostart"
DESKTOP_FILE="$AUTOSTART_DIR/iot-health-monitor.desktop"

# 1. Ensure run_main.sh is executable
echo "1️⃣  Setting executable permission for run_main.sh..."
chmod +x "$PROJECT_DIR/run_main.sh"
echo "✅ run_main.sh is now executable"
echo ""

# 2. Create autostart directory if not exists
echo "2️⃣  Creating autostart directory..."
mkdir -p "$AUTOSTART_DIR"
echo "✅ Directory created: $AUTOSTART_DIR"
echo ""

# 3. Create .desktop file for autostart
echo "3️⃣  Creating autostart desktop entry..."
cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Type=Application
Name=IoT Health Monitor
Comment=Auto-start IoT Health Monitoring System
Exec=/bin/bash $PROJECT_DIR/run_main.sh
Path=$PROJECT_DIR
Terminal=false
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=15
StartupNotify=false
EOF

echo "✅ Desktop file created: $DESKTOP_FILE"
echo ""

# 4. Verify .desktop file
echo "4️⃣  Verifying autostart configuration..."
if [ -f "$DESKTOP_FILE" ]; then
    echo "✅ Autostart file exists"
    echo "📄 Content:"
    cat "$DESKTOP_FILE"
else
    echo "❌ Failed to create autostart file"
    exit 1
fi
echo ""

# 5. Instructions
echo "=================================================="
echo "✅ Setup Complete!"
echo "=================================================="
echo ""
echo "📋 Next Steps:"
echo "   1. Reboot your Pi: sudo reboot"
echo "   2. System will auto-start after login (~10s delay)"
echo ""
echo "🔍 To verify autostart is enabled:"
echo "   ls -la ~/.config/autostart/iot-health-monitor.desktop"
echo ""
echo "🛑 To disable autostart:"
echo "   rm ~/.config/autostart/iot-health-monitor.desktop"
echo ""
echo "🔄 To manually restart after boot:"
echo "   ./run_main.sh"
echo ""
echo "📝 Logs location (if needed):"
echo "   ./logs/"
echo ""
echo "=================================================="
