#!/usr/bin/with-contenv bashio

# Read configuration from Home Assistant
CONFIG_PATH=/data/options.json

TEMPIRO_USERNAME=$(bashio::config 'tempiro_username')
TEMPIRO_PASSWORD=$(bashio::config 'tempiro_password')
PRICE_AREA=$(bashio::config 'price_area')

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

bashio::log.info "Starting Tempiro Energy Monitor..."
bashio::log.info "Price area: ${PRICE_AREA}"

cd /app
exec python3 app.py
