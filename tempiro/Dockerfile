ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python and dependencies
RUN apk add --no-cache python3 py3-pip py3-requests py3-flask

# Create app directory
WORKDIR /app

# Copy application files
COPY rootfs /
COPY app.py database.py backfill.py requirements.txt /app/
COPY static /app/static/

# Install Python dependencies
RUN pip3 install --no-cache-dir flask-cors

# Set permissions
RUN chmod +x /run.sh

# Expose port
EXPOSE 5001

CMD ["/run.sh"]
