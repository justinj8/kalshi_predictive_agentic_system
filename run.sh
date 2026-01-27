#!/bin/bash

# Kalshi Predictive Markets Trading System - Startup Script

echo "=================================================="
echo "Kalshi Predictive Markets Agentic AI System"
echo "=================================================="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found!"
    echo "Please copy .env.example to .env and add your API keys:"
    echo "  cp .env.example .env"
    echo "  nano .env  # Edit and add your ANTHROPIC_API_KEY"
    exit 1
fi

# Check if dependencies are installed
if ! python -c "import anthropic" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi

# Create data directories
mkdir -p data/logs

echo ""
echo "Starting trading system..."
echo "Press Ctrl+C to stop"
echo ""

# Run the system
python src/main.py
