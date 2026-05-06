ARG BASE_IMAGE=docker.io/ainullcode/borg-ui-runtime-base:runtime-borg1-1.4.4-borg2-2.0.0b21-r1

# Build stage for backend
FROM python:3.10-slim AS backend-builder
WORKDIR /app

# Install build dependencies for psutil and other packages
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    python3-dev \
    libffi-dev \
    libssl-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and setuptools for better wheel support
RUN pip install --upgrade pip setuptools wheel

COPY requirements.txt .
# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Development stage
FROM ${BASE_IMAGE} AS development

# Build arguments
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

WORKDIR /app

# Copy Python dependencies
COPY --from=backend-builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=backend-builder /usr/local/bin /usr/local/bin

# Copy application code. Frontend assets are not required in dev because
# the Vite dev server runs locally and proxies API requests to this backend.
COPY app/ ./app/
COPY VERSION ./VERSION

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PYTHONPATH=/app
ENV DATA_DIR=/data
ENV DATABASE_URL=sqlite:////data/borg.db
ENV BORG_BACKUP_PATH=/backups
ENV ENABLE_CRON_BACKUPS=false
ENV PORT=8081
ENV ACTIVATION_SERVICE_URL=https://license.borgui.com
ENV ENABLE_STARTUP_LICENSE_SYNC=true

EXPOSE 8081

ENTRYPOINT ["/entrypoint.sh"]

# Production stage
FROM ${BASE_IMAGE} AS production

# Build arguments
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

# Docker image metadata
LABEL org.opencontainers.image.title="Borg Web UI"
LABEL org.opencontainers.image.description="A lightweight web interface for Borg backup management"
LABEL org.opencontainers.image.version="${APP_VERSION}"
LABEL org.opencontainers.image.vendor="Borg Web UI"
LABEL org.opencontainers.image.url="https://github.com/karanhudia/borg-ui"
LABEL org.opencontainers.image.documentation="https://github.com/karanhudia/borg-ui/blob/main/README.md"
LABEL org.opencontainers.image.source="https://github.com/karanhudia/borg-ui"
LABEL org.opencontainers.image.licenses="MIT"
LABEL com.borg-ui.icon.color="#00dd00"

WORKDIR /app

# Copy Python dependencies
COPY --from=backend-builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=backend-builder /usr/local/bin /usr/local/bin

# Frontend assets are prepared outside Docker in CI and copied into the
# build context to avoid rebuilding the same static bundle per architecture.
COPY docker/frontend-build-output/ ./app/static/

# Copy application code
COPY app/ ./app/

# Copy VERSION file
COPY VERSION ./VERSION

# Set proper ownership and permissions
RUN chown -R borg:borg /app /data /backups /var/log/borg /etc/borg && \
    chmod -R 755 /app && \
    chmod -R 755 /data && \
    chmod -R 755 /backups && \
    chmod -R 755 /var/log/borg && \
    chmod -R 755 /etc/borg

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Stay as root - entrypoint will handle UID/GID changes and switch to borg user

# Set environment variables
ENV PYTHONPATH=/app
ENV DATA_DIR=/data
ENV DATABASE_URL=sqlite:////data/borg.db
ENV BORG_BACKUP_PATH=/backups
ENV ENABLE_CRON_BACKUPS=false
ENV PORT=8081
ENV ACTIVATION_SERVICE_URL=https://license.borgui.com
ENV ENABLE_STARTUP_LICENSE_SYNC=true

# Expose port
EXPOSE 8081

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8081}/ || exit 1

# Use entrypoint that handles UID/GID changes
ENTRYPOINT ["/entrypoint.sh"]
