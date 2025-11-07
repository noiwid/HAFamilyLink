ARG BUILD_FROM=ghcr.io/hassio-addons/base:14.0.2
FROM ${BUILD_FROM}

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install system dependencies required for Playwright and Chromium
RUN apk add --no-cache \
    python3=~3.11 \
    py3-pip=~23 \
    chromium \
    chromium-chromedriver \
    nss \
    freetype \
    harfbuzz \
    ca-certificates \
    ttf-freefont \
    nodejs \
    npm \
    curl \
    && rm -rf /var/cache/apk/*

# Set environment variables for Playwright
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=0
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Install Playwright and its browsers
# Note: Using latest version for better ARM64 support
RUN pip3 install --no-cache-dir --break-system-packages playwright && \
    playwright install chromium && \
    playwright install-deps chromium

# Copy application code
COPY app/ /app/app/
COPY rootfs/ /

# Set permissions
RUN chmod a+x /usr/local/bin/run.sh && \
    chmod a+x /etc/services.d/familylink/run && \
    chmod a+x /etc/services.d/familylink/finish

# Create necessary directories
RUN mkdir -p /share/familylink && \
    chmod 700 /share/familylink

# Expose port
EXPOSE 8099

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8099/api/health || exit 1

# Labels
LABEL \
    io.hass.name="Google Family Link Auth" \
    io.hass.description="Authentication service for Google Family Link" \
    io.hass.type="addon" \
    io.hass.version="1.0.0"

# Start command
CMD ["/usr/local/bin/run.sh"]
