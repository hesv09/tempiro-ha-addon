#!/bin/sh

# Read configuration from Home Assistant options
CONFIG_PATH=/data/options.json

echo "=== Tempiro Energy Monitor Starting ==="
echo "Looking for config at: $CONFIG_PATH"

if [ -f "$CONFIG_PATH" ]; then
    echo "Config file found!"
    echo "Config contents:"
    cat $CONFIG_PATH | jq 'del(.tempiro_password) | .tempiro_password = "***HIDDEN***"'

    TEMPIRO_USERNAME=$(jq -r '.tempiro_username' $CONFIG_PATH)
    TEMPIRO_PASSWORD=$(jq -r '.tempiro_password' $CONFIG_PATH)
    PRICE_AREA=$(jq -r '.price_area // "SE3"' $CONFIG_PATH)

    echo "Username: $TEMPIRO_USERNAME"
    echo "Password length: ${#TEMPIRO_PASSWORD}"
    echo "Price area: $PRICE_AREA"
else
    echo "ERROR: No configuration file found at $CONFIG_PATH"
    echo "Contents of /data:"
    ls -la /data/
    exit 1
fi

# Create config file for the app
cat > /app/config.json << EOF
{
    "tempiro": {
        "base_url": "http://xmpp.tempiro.com:5000",
        "username": "${TEMPIRO_USERNAME}",
        "password": "${TEMPIRO_PASSWORD}"
    },
    "server": {
        "host": "0.0.0.0",
        "port": 5001
    },
    "price_area": "${PRICE_AREA}"
}
EOF

echo "Config file created at /app/config.json"

# Set data directory to persistent storage
export DATA_DIR=/data

echo "Starting Flask server..."
cd /app
exec python3 app.py
