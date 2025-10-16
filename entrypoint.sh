#!/bin/sh
# Start Xvfb in background
echo "Starting Xvfb..."
Xvfb :99 -screen 0 1280x720x24 &
export DISPLAY=:99

# Execute whatever CMD is passed
exec "$@"
