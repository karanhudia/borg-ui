# Build stage for frontend
FROM node:18-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
RUN npm run build

# Build stage for backend
FROM python:3.9-slim AS backend-builder
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

# Production stage
FROM python:3.9-slim AS production

# Build arguments
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

WORKDIR /app

# Install system dependencies including borg and related packages
RUN apt-get update && apt-get install -y \
    # Core system packages
    cron \
    curl \
    wget \
    gnupg \
    lsb-release \
    gosu \
    # Borg and related packages
    borgbackup \
    borgbackup-doc \
    # Additional useful packages
    rsync \
    openssh-client \
    python3-pip \
    python3-dev \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# No additional Python packages needed - borg is already installed

# Install additional useful tools
RUN apt-get update && apt-get install -y \
    # Monitoring tools
    htop \
    iotop \
    # Network tools
    net-tools \
    iputils-ping \
    # File system tools
    tree \
    ncdu \
    # SSH deployment tools
    sshpass \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies
COPY --from=backend-builder /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
COPY --from=backend-builder /usr/local/bin /usr/local/bin

# Copy application code
COPY app/ ./app/
COPY --from=frontend-builder /app/frontend/build ./app/static

# Create necessary directories with proper permissions
# /data - main data directory for all persistent data (database, ssh keys, logs, configs)
# /backups - for actual backup storage
RUN mkdir -p \
    /data \
    /data/ssh_keys \
    /data/logs \
    /data/config \
    /backups \
    /var/log/borg \
    /etc/borg

# Create non-root user with default UID/GID 1001:1001
# Runtime UID/GID can be changed via PUID/PGID environment variables
RUN groupadd -g 1001 borg && \
    useradd -m -u 1001 -g 1001 -s /bin/bash borg && \
    # Add user to necessary groups
    usermod -a -G sudo borg && \
    # Set up sudo access for borg user (needed for cron jobs and borg operations)
    echo "borg ALL=(ALL) NOPASSWD: /usr/bin/borg, /usr/bin/crontab" >> /etc/sudoers

# Set proper ownership and permissions
RUN chown -R borg:borg /app /data /backups /var/log/borg /etc/borg && \
    chmod -R 755 /app && \
    chmod -R 755 /data && \
    chmod -R 755 /backups && \
    chmod -R 755 /var/log/borg && \
    chmod -R 755 /etc/borg

# Create SSH directory for borg user
RUN mkdir -p /home/borg/.ssh && \
    chown -R borg:borg /home/borg/.ssh && \
    chmod 700 /home/borg/.ssh

# Set up cron directory
RUN mkdir -p /etc/cron.d && \
    chown -R borg:borg /etc/cron.d

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

# Expose port
EXPOSE 8081

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8081}/ || exit 1

# Use entrypoint that handles UID/GID changes
ENTRYPOINT ["/entrypoint.sh"] 