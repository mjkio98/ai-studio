#!/bin/bash

# VPS Deployment Script for YouTube Analyzer with Tor
# This script will stop the old app, remove it, clone the new version from GitHub, and start it

VPS_HOST="193.111.77.97"
VPS_USER="root"
APP_DIR="/opt/youtube-analyzer"
REPO_URL="https://github.com/majdh7463/main-project-tor.git"

echo "🚀 Starting deployment to VPS..."
echo "======================================"

# Connect to VPS and execute deployment commands
ssh -i ~/.ssh/id_rsa_vps ${VPS_USER}@${VPS_HOST} << 'ENDSSH'

echo "📋 Step 1: Stopping existing application..."
systemctl stop youtube-app 2>/dev/null || pkill -f "python.*main.py" || true
sleep 2

echo "📋 Step 2: Removing old application directory..."
rm -rf /opt/youtube-analyzer
rm -rf /opt/main-app-tor

echo "📋 Step 3: Cloning latest code from GitHub..."
cd /opt
git clone https://github.com/majdh7463/main-project-tor.git youtube-analyzer

echo "📋 Step 4: Installing Python dependencies..."
cd /opt/youtube-analyzer
pip3 install -r config/requirements.txt

echo "📋 Step 5: Checking Tor service..."
systemctl status tor --no-pager | head -5
if ! systemctl is-active --quiet tor; then
    echo "⚠️  Starting Tor service..."
    systemctl start tor
    sleep 3
fi

echo "📋 Step 6: Creating systemd service..."
cat > /etc/systemd/system/youtube-app.service << 'EOF'
[Unit]
Description=YouTube Analyzer with Tor
After=network.target tor.service
Wants=tor.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/youtube-analyzer
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
ExecStart=/usr/bin/python3 /opt/youtube-analyzer/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "📋 Step 7: Reloading systemd and starting application..."
systemctl daemon-reload
systemctl enable youtube-app
systemctl start youtube-app

echo "📋 Step 8: Waiting for application to start..."
sleep 5

echo "📋 Step 9: Checking application status..."
systemctl status youtube-app --no-pager | head -15

echo ""
echo "======================================"
echo "✅ Deployment complete!"
echo ""
echo "📊 Application Status:"
systemctl is-active youtube-app && echo "  Status: ✅ Running" || echo "  Status: ❌ Stopped"
echo ""
echo "🌐 Access your application at: http://193.111.77.97:8080"
echo ""
echo "📝 Useful commands:"
echo "  View logs:    journalctl -u youtube-app -f"
echo "  Restart app:  systemctl restart youtube-app"
echo "  Stop app:     systemctl stop youtube-app"
echo "  App status:   systemctl status youtube-app"

ENDSSH

echo ""
echo "🎉 Deployment script completed!"
