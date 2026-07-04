#!/bin/bash
# Micro-AGI MVP Service Auto-Restart Daemon Wrapper

cd /data/data/com.termux/files/home/micro-agi-mvp

echo "=================================================="
echo "🔄 Starting Micro-AGI Web Server Daemon..."
echo "=================================================="

while true; do
    python app.py
    echo "=================================================="
    echo "⚠️ Server exited. Auto-restarting in 2 seconds..."
    echo "=================================================="
    sleep 2
done
