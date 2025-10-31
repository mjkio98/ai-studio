#!/bin/bash

# Deploy from GitHub repository to VPS

VPS_HOST="193.111.77.97"
VPS_USER="root"
APP_DIR="/opt/ai-studio"
GITHUB_REPO="https://github.com/mjkio98/ai-studio.git"

echo "🚀 Starting GitHub deployment to VPS..."
echo "======================================"

echo "📋 Repository: ${GITHUB_REPO}"
echo "📋 Target: ${VPS_USER}@${VPS_HOST}:${APP_DIR}"
echo ""

echo "📋 Step 1: Cleaning up existing deployment..."
ssh -i ~/.ssh/id_rsa_vps ${VPS_USER}@${VPS_HOST} << 'ENDSSH'

echo "  🧹 Stopping existing ai-studio service (if running)..."
if systemctl is-active --quiet ai-studio; then
    echo "    ⚠️  Stopping ai-studio service..."
    systemctl stop ai-studio
fi

echo "  🧹 Disabling ai-studio service (if exists)..."
if systemctl is-enabled --quiet ai-studio 2>/dev/null; then
    echo "    ⚠️  Disabling ai-studio service..."
    systemctl disable ai-studio
fi

echo "  🧹 Removing service file..."
rm -f /etc/systemd/system/ai-studio.service

echo "  🧹 Removing existing project directory..."
rm -rf /opt/ai-studio

echo "  🧹 Reloading systemd daemon..."
systemctl daemon-reload

echo ""
echo "📋 Step 2: Fresh deployment from GitHub..."

echo "  📌 Installing Git if not present..."
which git || apt update && apt install -y git

echo "  📌 Cloning fresh from GitHub repository..."
git clone https://github.com/mjkio98/ai-studio.git /opt/ai-studio
cd /opt/ai-studio

echo ""
echo "📋 Step 3: Setting up application..."

echo "  📌 Installing Python dependencies..."
pip3 install -r config/requirements.txt

echo "  📌 Checking Tor service..."
if ! systemctl is-active --quiet tor; then
    echo "    ⚠️  Starting Tor service..."
    systemctl start tor
    sleep 3
fi

echo "  📌 Creating systemd service..."
cat > /etc/systemd/system/ai-studio.service << 'EOF'
[Unit]
Description=AI Studio - YouTube & Web Content Analyzer
After=network.target tor.service
Wants=tor.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/ai-studio
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
ExecStart=/usr/bin/python3 /opt/ai-studio/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "  📌 Reloading systemd and starting application..."
systemctl daemon-reload
systemctl enable ai-studio
systemctl start ai-studio

echo "  📌 Waiting for application to start..."
sleep 5

echo ""
echo "======================================"
echo "✅ Deployment complete!"
echo ""
echo "📊 Application Status:"
systemctl status ai-studio --no-pager | head -10

ENDSSH

echo ""
echo "🌐 Access your application at: http://193.111.77.97:8080"
echo ""
echo "📝 Useful commands:"
echo "  View logs:    ssh -i ~/.ssh/id_rsa_vps root@193.111.77.97 'journalctl -u ai-studio -f'"
echo "  Restart app:  ssh -i ~/.ssh/id_rsa_vps root@193.111.77.97 'systemctl restart ai-studio'"
echo "  App status:   ssh -i ~/.ssh/id_rsa_vps root@193.111.77.97 'systemctl status ai-studio'"
echo "  Update app:   ssh -i ~/.ssh/id_rsa_vps root@193.111.77.97 'cd /opt/ai-studio && git pull && systemctl restart ai-studio'"
echo ""
echo "🎉 GitHub deployment completed successfully!"
