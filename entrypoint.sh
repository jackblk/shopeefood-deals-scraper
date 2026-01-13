#!/bin/sh
# Start Xvfb in background
echo "Starting Xvfb..."

# Virtual display :99, resolution 1280x720, 24-bit color
# Disable TCP X11 connections, avoid network-related resets
# Do NOT reset X server when last client disconnects (critical)
# Disable access control, allow reconnects from same container
Xvfb :99 \
  -screen 0 1280x720x24 \
  -nolisten tcp \
  -noreset \
  -ac &

export DISPLAY=:99

# Execute whatever CMD is passed
exec "$@"
