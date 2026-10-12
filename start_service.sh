#!/bin/bash
# Start from the directory containing this script, regardless of its location.
cd "$(dirname "$0")" || exit 1

if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 2 http://127.0.0.1:8087/api/health >/dev/null; then
    echo "Micro-AGI is already running at http://127.0.0.1:8087/"
    exit 0
fi

echo "Starting Micro-AGI at http://127.0.0.1:8087/"
while true; do
    python app.py
    status=$?
    if [ "$status" -ne 0 ]; then
        echo "Micro-AGI exited with status $status. Check port 8087 and the error above."
        exit "$status"
    fi
    sleep 2
done
