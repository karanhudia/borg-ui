# Installation Guide

Simple installation guide for Borgmatic Web UI. Works on any system with Docker.

---

## Prerequisites

- Docker & Docker Compose
- 512MB RAM minimum (1GB recommended)
- Linux, macOS, or Windows with Docker Desktop

---

## Quick Install

### 1. Clone Repository

```bash
git clone https://github.com/karanhudia/borg-ui.git
cd borg-ui
```

### 2. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Generate secure secret key
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))" >> .env
```

### 3. Start Application

**Docker Compose (Recommended):**
```bash
docker-compose up -d
```

**Portainer:**
1. Upload `docker-compose.yml` to Portainer
2. Add environment variables from `.env`
3. Deploy stack

**Docker Run:**
```bash
docker run -d \
  --name borgmatic-ui \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/backups:/backups \
  -e SECRET_KEY=your-generated-secret-key \
  -e ENVIRONMENT=production \
  ainullcode/borgmatic-ui:latest
```

### 4. Access Web Interface

Open browser: `http://localhost:8000`

**Default credentials:**
- Username: `admin`
- Password: `admin123`

**⚠️ Change password immediately after first login!**

---

## Configuration

### Required Environment Variables

```bash
# Security (REQUIRED)
SECRET_KEY=your-32-char-random-string

# Environment
ENVIRONMENT=production
```

### Optional Environment Variables

```bash
# Database
DATABASE_URL=sqlite:////app/data/borgmatic.db

# Logging
LOG_LEVEL=INFO

# Borgmatic paths
BORGMATIC_CONFIG_PATH=/app/config/borgmatic.yaml
BORGMATIC_BACKUP_PATH=/backups

# Initial admin password (first startup only)
INITIAL_ADMIN_PASSWORD=custom-password
```

### Volume Mounts

Mount these directories for persistent data:

```yaml
volumes:
  - ./data:/app/data        # Database and SSH keys
  - ./config:/app/config    # Borgmatic configuration
  - ./backups:/backups      # Backup storage
  - ./logs:/app/logs        # Application logs
```

**To backup source directories, add:**
```yaml
volumes:
  - /path/to/source:/backup-source:ro  # Read-only source
```

---

## Network Configuration

**Default:** Uses bridge network (works everywhere)

**If you need SSH access to other machines on your network:**
- Only supported on native Linux (not Docker Desktop/Colima)
- Uncomment `network_mode: "host"` in `docker-compose.yml`
- Comment out `networks:` and `extra_hosts:` sections

---

## Security Setup

See [SECURITY.md](SECURITY.md) for detailed security configuration.

**Quick security checklist:**
- [ ] Generate strong `SECRET_KEY`
- [ ] Set `ENVIRONMENT=production`
- [ ] Change default admin password
- [ ] Use HTTPS (reverse proxy)
- [ ] Configure firewall
- [ ] Regular backups

---

## Updating

```bash
# Pull latest image
docker-compose pull

# Restart with new version
docker-compose up -d
```

---

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs borgmatic-ui

# Common issues:
# - Missing SECRET_KEY: Add to .env file
# - Port 8000 in use: Change port in docker-compose.yml
# - Permission denied: Check volume permissions
```

### Can't access UI

```bash
# Check if container is running
docker-compose ps

# Check if port is accessible
curl http://localhost:8000/api/health/system

# Check firewall
sudo ufw allow 8000/tcp  # Linux
```

### Database issues

```bash
# Database is stored in ./data/borgmatic.db
# To reset: rm ./data/borgmatic.db && docker-compose restart
```

---

## Uninstall

```bash
# Stop and remove containers
docker-compose down

# Remove data (optional - THIS DELETES EVERYTHING!)
# rm -rf data/ config/ backups/ logs/
```

---

## Support

- **Documentation:** [README.md](README.md)
- **Security:** [SECURITY.md](SECURITY.md)
- **Issues:** https://github.com/karanhudia/borg-ui/issues
- **API Docs:** http://localhost:8000/api/docs (after install)
