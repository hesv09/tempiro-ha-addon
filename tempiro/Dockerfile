ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python and dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-requests \
    jq

# Create app directory
WORKDIR /app

# Copy application files
COPY app.py database.py backfill.py requirements.txt /app/
COPY static /app/static/
COPY rootfs/run.sh /run.sh

# Install Python dependencies
RUN pip3 install --no-cache-dir --break-system-packages \
    flask \
    flask-cors

# Set permissions
RUN chmod +x /run.sh

# Expose port
EXPOSE 8099

CMD ["/run.sh"]
