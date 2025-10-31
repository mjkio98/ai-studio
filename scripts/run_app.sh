#!/bin/bash
# YouTube Summarizer - Easy Startup Script
# Choose your preferred way to run the app

echo "🎯 YouTube Summarizer - Startup Options"
echo "======================================"
echo ""
echo "Choose how to run your app:"
echo "1) Development Mode (Threading) - Good for testing"
echo "2) Production Mode (Gunicorn) - Best performance"
echo "3) API Only Mode - No web interface"
echo "4) Custom Settings"
echo ""
read -p "Enter choice (1-4): " choice

cd /home/majal/Desktop/youtube-proejct
source venv/bin/activate

case $choice in
    1)
        echo "🔧 Starting in Development Mode with Threading..."
        python3 main.py --port 5005 --debug
        ;;
    2)
        echo "🚀 Starting in Production Mode with Gunicorn..."
        echo "   ✅ 4 worker processes"
        echo "   ✅ Optimized for concurrent users"
        echo "   ✅ Better memory management"
        gunicorn app:app \
            --workers 4 \
            --bind 0.0.0.0:5005 \
            --timeout 120 \
            --worker-class sync \
            --max-requests 1000 \
            --max-requests-jitter 50 \
            --preload
        ;;
    3)
        echo "📡 Starting API-Only Mode..."
        python3 main.py --port 5005
        ;;
    4)
        read -p "Enter port (default 5005): " port
        port=${port:-5005}
        read -p "Development (d) or Production (p): " mode
        if [[ $mode == "p" ]]; then
            echo "🚀 Starting Production Mode on port $port..."
            gunicorn app:app --workers 4 --bind 0.0.0.0:$port
        else
            echo "🔧 Starting Development Mode on port $port..."
            python3 main.py --port $port --debug
        fi
        ;;
    *)
        echo "❌ Invalid choice. Starting Development Mode..."
        python3 main.py --port 5005 --debug
        ;;
esac