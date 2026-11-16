#!/bin/bash
# =====================================================================
# Google Cloud VM Automated Deployment Script
# NSE Breakout Quant Screener (FastAPI + Background Scanner)
# =====================================================================
set -e

echo "🚀 [1/6] Setting System Timezone to Asia/Kolkata..."
sudo timedatectl set-timezone Asia/Kolkata

echo "📦 [2/6] Updating packages & installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv git curl build-essential tzdata ufw

APP_DIR=$(pwd)
echo "📂 Working directory: $APP_DIR"

echo "🐍 [3/6] Creating Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

echo "⬇️ [4/6] Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Ensure .env exists
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "⚠️ Created .env from .env.example. Please update your Telegram Bot Token and Chat IDs in .env!"
    fi
fi

echo "⚙️ [5/6] Creating Systemd Service for 24/7 background execution..."
CURRENT_USER=$(whoami)

sudo bash -c "cat > /etc/systemd/system/screener.service <<EOF
[Unit]
Description=NSE Breakout Quant Screener & Telegram Bot
After=network.target

[Service]
User=$CURRENT_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/python main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF"

echo "🔄 [6/6] Reloading systemd and enabling service..."
sudo systemctl daemon-reload
sudo systemctl enable screener
sudo systemctl restart screener

echo ""
echo "====================================================================="
echo "✅ DEPLOYMENT COMPLETE & RUNNING IN BACKGROUND!"
echo "====================================================================="
echo "🔍 Check service status : sudo systemctl status screener"
echo "📜 View live logs       : sudo journalctl -u screener -f"
echo "🔄 Restart service      : sudo systemctl restart screener"
echo "⏹️ Stop service         : sudo systemctl stop screener"
echo "🌐 Web Dashboard        : http://<YOUR_VM_EXTERNAL_IP>:8000"
echo "====================================================================="
