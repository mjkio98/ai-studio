#!/bin/bash

# YouTube Summarizer Production Startup Script
# This script helps you run the app in different modes for optimal performance

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 YouTube Summarizer Deployment Helper${NC}"
echo "=================================================="

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}⚠️  Virtual environment not found. Creating one...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}✅ Virtual environment created${NC}"
fi

# Activate virtual environment
source venv/bin/activate
echo -e "${GREEN}✅ Virtual environment activated${NC}"

# Install/update dependencies
echo -e "${BLUE}📦 Installing dependencies...${NC}"
pip install -r config/requirements.txt
echo -e "${GREEN}✅ Dependencies installed${NC}"

# Ask user for deployment mode
echo ""
echo -e "${YELLOW}Choose deployment mode:${NC}"
echo "1) Development (single user, with debugging)"
echo "2) Development with threading (multiple users, with debugging)"
echo "3) Production (multiple users, optimized performance)"
echo ""
read -p "Enter your choice (1-3): " choice

case $choice in
    1)
        echo -e "${BLUE}🔧 Starting in development mode...${NC}"
        python3 main.py --debug
        ;;
    2)
        echo -e "${BLUE}� Starting in threaded development mode...${NC}"
        python3 main.py --debug
        ;;
    3)
        echo -e "${GREEN}⚡ Starting in production mode with Gunicorn...${NC}"
        echo -e "${BLUE}📌 Using optimized settings for concurrent requests${NC}"
        
        # Check if gunicorn is installed
        if ! command -v gunicorn &> /dev/null; then
            echo -e "${RED}❌ Gunicorn not found. Installing...${NC}"
            pip install gunicorn
        fi
        
        # Start with Gunicorn using our config
        echo -e "${GREEN}🌐 Server starting at http://0.0.0.0:5001${NC}"
        echo -e "${BLUE}� Multiple concurrent users supported${NC}"
        echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
        echo ""
        
        gunicorn -c config/gunicorn_config.py app:app
        ;;
    *)
        echo -e "${RED}❌ Invalid choice. Please run the script again.${NC}"
        exit 1
        ;;
esac