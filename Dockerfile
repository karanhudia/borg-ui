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
# Additional dependencies for ARM compilation (bcrypt, cryptography)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    automake \
    autoconf \
    libtool \
    pkg-config \
    python3-dev \
    libffi-dev \
    libssl-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and setuptools for better wheel support
RUN pip install --upgrade pip setuptools wheel

COPY requirements.txt .
# Install packages - uvloop removed to avoid ARM compilation issues
RUN pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.9-slim AS production
WORKDIR /app

# Install system dependencies including borg and related packages
RUN apt-get update && apt-get install -y \
    # Core system packages
    cron \
    curl \
    wget \
    gnupg \
    lsb-release \
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

# Install borgmatic and additional Python packages
RUN pip3 install --no-cache-dir \
    borgmatic \
    borgmatic[mysql] \
    borgmatic[postgresql] \
    borgmatic[remote] \
    borgmatic[ssh]

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
RUN mkdir -p \
    /app/logs \
    /app/config \
    /app/data \
    /app/data/ssh_keys \
    /backups \
    /var/log/borgmatic \
    /etc/borgmatic

# Create non-root user with UID 1001 (Portainer recommended)
RUN groupadd -g 1001 borgmatic && \
    useradd -m -u 1001 -g 1001 -s /bin/bash borgmatic && \
    # Add user to necessary groups
    usermod -a -G sudo borgmatic && \
    # Set up sudo access for borgmatic user (needed for cron jobs)
    echo "borgmatic ALL=(ALL) NOPASSWD: /usr/bin/borg, /usr/bin/borgmatic, /usr/bin/crontab" >> /etc/sudoers

# Set proper ownership and permissions
RUN chown -R borgmatic:borgmatic /app /backups /var/log/borgmatic /etc/borgmatic && \
    chmod -R 755 /app && \
    chmod -R 755 /backups && \
    chmod -R 755 /var/log/borgmatic && \
    chmod -R 755 /etc/borgmatic

# Create SSH directory for borgmatic user
RUN mkdir -p /home/borgmatic/.ssh && \
    chown -R borgmatic:borgmatic /home/borgmatic/.ssh && \
    chmod 700 /home/borgmatic/.ssh

# Create borgmatic configuration template (optional - can be mounted via volume)
# COPY config/borgmatic.yaml.template /etc/borgmatic/config.yaml.template

# Set up cron directory
RUN mkdir -p /etc/cron.d && \
    chown -R borgmatic:borgmatic /etc/cron.d

# Create startup script
RUN echo '#!/bin/bash\n\
echo "[$(date)] Starting Borgmatic Web UI..."\n\
cd /app\n\
exec gunicorn app.main:app --bind 0.0.0.0:8000 --workers 1 --worker-class uvicorn.workers.UvicornWorker --access-logfile /app/logs/access.log --error-logfile /app/logs/error.log\n\
' > /app/start.sh && \
    chmod +x /app/start.sh && \
    chown borgmatic:borgmatic /app/start.sh

# Switch to non-root user
USER borgmatic

# Set environment variables
ENV PYTHONPATH=/app
ENV BORGMATIC_CONFIG_PATH=/app/config/borgmatic.yaml
ENV BORGMATIC_BACKUP_PATH=/backups
ENV ENABLE_CRON_BACKUPS=false

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Start application using the startup script
CMD ["/app/start.sh"] 