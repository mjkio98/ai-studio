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

echo "  📌 Updating yt-dlp to latest version..."
pip3 install --upgrade yt-dlp
echo "    ✅ yt-dlp version: $(yt-dlp --version)"

echo "  📌 Setting up and testing Tor service..."
if ! systemctl is-active --quiet tor@default; then
    echo "    ⚠️  Starting Tor default service..."
    systemctl start tor@default
    sleep 5
fi

echo "    🔍 Testing Tor connectivity..."
TOR_TEST=$(curl --connect-timeout 10 --socks5 127.0.0.1:9050 https://check.torproject.org/api/ip 2>/dev/null)
if echo "$TOR_TEST" | grep -q '"IsTor":true'; then
    TOR_IP=$(echo "$TOR_TEST" | grep -o '"IP":"[^"]*"' | cut -d'"' -f4)
    echo "    ✅ Tor working - IP: $TOR_IP"
else
    echo "    ⚠️  Tor not working, restarting..."
    systemctl restart tor@default
    sleep 5
    TOR_TEST2=$(curl --connect-timeout 10 --socks5 127.0.0.1:9050 https://check.torproject.org/api/ip 2>/dev/null)
    if echo "$TOR_TEST2" | grep -q '"IsTor":true'; then
        TOR_IP2=$(echo "$TOR_TEST2" | grep -o '"IP":"[^"]*"' | cut -d'"' -f4)
        echo "    ✅ Tor working after restart - IP: $TOR_IP2"
    else
        echo "    ❌ Tor still not working - will continue anyway"
    fi
fi

echo "  📌 Testing YouTube extraction with latest yt-dlp..."
YOUTUBE_TEST=$(timeout 15 yt-dlp --no-download --print title "https://www.youtube.com/watch?v=dQw4w9WgXcQ" 2>/dev/null)
if [ ! -z "$YOUTUBE_TEST" ]; then
    echo "    ✅ YouTube extraction working: ${YOUTUBE_TEST:0:50}..."
else
    echo "    ⚠️  YouTube extraction test failed - may work with Tor in app"
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
sleep 8

echo ""
echo "📋 Step 4: Post-deployment verification..."

echo "  🔍 Verifying AI Studio service..."
if systemctl is-active --quiet ai-studio; then
    echo "    ✅ AI Studio service is running"
else
    echo "    ❌ AI Studio service failed to start"
    echo "    📋 Last few log lines:"
    journalctl -u ai-studio --no-pager -n 5
fi

echo "  🔍 Verifying Tor integration..."
TOR_VERIFY=$(curl --connect-timeout 8 --socks5 127.0.0.1:9050 https://httpbin.org/ip 2>/dev/null)
if [ ! -z "$TOR_VERIFY" ]; then
    echo "    ✅ Tor proxy responding"
else
    echo "    ⚠️  Tor proxy not responding"
fi

echo "  🔍 Verifying application endpoints..."
if curl --connect-timeout 5 -s http://127.0.0.1:8080/ >/dev/null 2>&1; then
    echo "    ✅ Web interface accessible"
else
    echo "    ❌ Web interface not accessible"
fi

echo "  🔍 Final system status:"
echo "    📊 yt-dlp: $(yt-dlp --version)"
echo "    📊 Tor status: $(systemctl is-active tor@default)"
echo "    📊 AI Studio status: $(systemctl is-active ai-studio)"

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
echo "  View logs:     ssh -i ~/.ssh/id_rsa_vps root@193.111.77.97 'journalctl -u ai-studio -f'"
echo "  Restart app:   ssh -i ~/.ssh/id_rsa_vps root@193.111.77.97 'systemctl restart ai-studio'"
echo "  App status:    ssh -i ~/.ssh/id_rsa_vps root@193.111.77.97 'systemctl status ai-studio'"
echo "  Update app:    ssh -i ~/.ssh/id_rsa_vps root@193.111.77.97 'cd /opt/ai-studio && git pull && systemctl restart ai-studio'"
echo "  Update yt-dlp: ssh -i ~/.ssh/id_rsa_vps root@193.111.77.97 'pip3 install --upgrade yt-dlp && systemctl restart ai-studio'"
echo "  Test Tor:      ssh -i ~/.ssh/id_rsa_vps root@193.111.77.97 'curl --socks5 127.0.0.1:9050 https://check.torproject.org/api/ip'"
echo "  Restart Tor:   ssh -i ~/.ssh/id_rsa_vps root@193.111.77.97 'systemctl restart tor@default'"
echo "  Full restart:  ssh -i ~/.ssh/id_rsa_vps root@193.111.77.97 'systemctl restart tor@default && systemctl restart ai-studio'"
echo ""
echo "🎉 GitHub deployment completed successfully!"
