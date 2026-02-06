#!/bin/sh

# Read configuration from Home Assistant options
CONFIG_PATH=/data/options.json

if [ -f "$CONFIG_PATH" ]; then
    TEMPIRO_USERNAME=$(jq -r '.tempiro_username' $CONFIG_PATH)
    TEMPIRO_PASSWORD=$(jq -r '.tempiro_password' $CONFIG_PATH)
    PRICE_AREA=$(jq -r '.price_area // "SE3"' $CONFIG_PATH)
else
    echo "ERROR: No configuration file found at $CONFIG_PATH"
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

# Set data directory to persistent storage
export DATA_DIR=/data

echo "Starting Tempiro Energy Monitor..."
echo "Price area: ${PRICE_AREA}"

cd /app
exec python3 app.py
