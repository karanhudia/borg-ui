# Security Policy

## Reporting Security Vulnerabilities

**Please do NOT report security vulnerabilities through public GitHub issues.**

Instead, please report them privately via GitHub Security Advisories:
1. Go to the [Security tab](https://github.com/karanhudia/borg-ui/security)
2. Click "Report a vulnerability"
3. Provide detailed information about the vulnerability

We will respond as quickly as possible and keep you updated on the resolution.

---

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| latest  | :white_check_mark: |
| < 1.0   | :x:                |

---

## Security Best Practices

### 1. Environment Variables & Secrets

#### ⚠️ CRITICAL: Never Commit Secrets

**Files that should NEVER be committed:**
- `.env` (already in `.gitignore`)
- `*.key`, `*.pem` (SSH keys, certificates)
- `config/secrets.yaml`
- Any file containing passwords, API keys, or tokens

#### Generate Strong Secrets

**For `SECRET_KEY` (JWT tokens):**
```bash
# Method 1: Python
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Method 2: OpenSSL
openssl rand -base64 32

# Method 3: /dev/urandom (Linux/Mac)
head -c 32 /dev/urandom | base64
```

**Requirements:**
- Minimum 32 characters
- Randomly generated
- Different for each environment (dev/staging/prod)
- Rotated periodically (every 90 days recommended)

### 2. Initial Setup

#### First-Time Installation

1. **Copy environment template:**
   ```bash
   cp .env.example .env
   ```

2. **Generate and set SECRET_KEY:**
   ```bash
   SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
   echo "SECRET_KEY=$SECRET_KEY" >> .env
   ```

3. **Set environment:**
   ```bash
   echo "ENVIRONMENT=production" >> .env
   echo "STRICT_SECURITY=true" >> .env
   ```

4. **Optional: Set custom initial admin password:**
   ```bash
   echo "INITIAL_ADMIN_PASSWORD=your-secure-password" >> .env
   ```

5. **Start application:**
   ```bash
   docker-compose up -d
   ```

6. **Change admin password immediately:**
   - Login with `admin` / `admin123` (or your custom password)
   - Go to Settings → Profile → Change Password
   - Use a strong password (12+ characters, mixed case, numbers, symbols)

### 3. Production Deployment Checklist

Before deploying to production, verify:

- [ ] `SECRET_KEY` is set to a strong, random value (not default)
- [ ] `ENVIRONMENT=production` is set
- [ ] `STRICT_SECURITY=true` is enabled
- [ ] Default admin password has been changed
- [ ] `.env` file is NOT committed to git
- [ ] SSH keys are stored securely
- [ ] HTTPS is enabled (use reverse proxy like Nginx/Caddy)
- [ ] Firewall rules are configured (only allow necessary ports)
- [ ] Database backups are configured
- [ ] Log monitoring is set up
- [ ] Security updates are enabled

### 4. Access Control

#### User Management

**Admin users can:**
- Create/delete users
- View all backups and repositories
- Modify system settings
- Access debug endpoints

**Regular users can:**
- Create and manage their own backups
- Access repositories they created
- View logs for their operations

**Best practices:**
- Use principle of least privilege
- Create separate users for different purposes
- Regularly review user access
- Disable unused accounts

#### Password Policy

**Enforce strong passwords:**
- Minimum 12 characters
- Mix of uppercase, lowercase, numbers, symbols
- No common words or patterns
- Change passwords every 90 days
- No password reuse

**The application enforces:**
- Bcrypt hashing with salt
- Protection against brute force (rate limiting)
- Secure password storage (never plaintext)

### 5. Network Security

#### Docker Networking

**For local deployments:**
```yaml
# Use bridge network (default)
networks:
  - borgmatic-network
```

**For Linux servers with SSH access needed:**
```yaml
# Use host network
network_mode: "host"
```

**Security implications:**
- Bridge network: Isolated from host network (more secure)
- Host network: Direct access to host network (needed for SSH to other machines)

#### Firewall Configuration

**Minimum required ports:**
- `8000/tcp` - Web UI and API (can be changed)

**Recommended UFW setup (Linux):**
```bash
# Enable firewall
sudo ufw enable

# Allow SSH (if managing remotely)
sudo ufw allow 22/tcp

# Allow Borgmatic UI
sudo ufw allow 8000/tcp

# Check status
sudo ufw status
```

### 6. HTTPS/TLS

**⚠️ CRITICAL for production:**

Never expose Borgmatic UI directly to the internet without HTTPS!

**Option 1: Nginx Reverse Proxy**
```nginx
server {
    listen 443 ssl http2;
    server_name backup.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Option 2: Caddy (Auto HTTPS)**
```
backup.example.com {
    reverse_proxy localhost:8000
}
```

**Option 3: Traefik (Docker labels)**
Already configured in `docker-compose.yml`:
```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.borgmatic-ui.rule=Host(`backup.example.com`)"
```

### 7. SSH Key Security

#### Key Generation

**Use strong key types:**
```bash
# RSA 4096-bit (recommended)
ssh-keygen -t rsa -b 4096

# Ed25519 (modern, secure, fast)
ssh-keygen -t ed25519
```

#### Key Storage

**Application stores keys in:**
- `/app/data/ssh_keys/` (inside container)
- Mounted to `./data/ssh_keys/` (on host)

**Security measures:**
- Keys stored with `0600` permissions (read/write by owner only)
- Private keys never logged or exposed via API
- Keys encrypted at rest (if using encrypted storage)

#### Key Distribution

**When deploying keys:**
- Use `ssh-copy-id` or similar secure methods
- Never send private keys over unencrypted channels
- Verify host fingerprints before connecting
- Use SSH agent forwarding cautiously

### 8. Database Security

#### SQLite (Default)

**Pros:**
- Simple, no additional services needed
- File-based, easy to backup
- Good for single-server deployments

**Security:**
- Database file stored in `./data/` (mounted volume)
- File permissions: `0600` (owner read/write only)
- Regular backups recommended

#### PostgreSQL (Production)

**For multi-instance or high-availability:**

```yaml
# docker-compose.yml
environment:
  - DATABASE_URL=postgresql://borgmatic:${DB_PASSWORD}@postgres:5432/borgmatic
```

**Security:**
- Use strong database password
- Enable SSL/TLS for database connections
- Restrict network access to database
- Regular security updates
- Automated backups

### 9. Logging & Monitoring

#### What to Monitor

**Security events:**
- Failed login attempts
- User creation/deletion
- Password changes
- Admin actions
- SSH key deployment
- Configuration changes

**Suspicious activity:**
- Multiple failed logins from same IP
- Logins from unusual locations
- Large data transfers
- Unusual backup patterns

#### Log Management

**Configure:**
```bash
# Set appropriate log level
LOG_LEVEL=INFO  # or WARNING for production

# Rotate logs to prevent disk fill
# (Configure in your log rotation tool)
```

**Monitor logs:**
```bash
# View recent logs
docker-compose logs -f borgmatic-ui

# Search for security events
docker-compose logs borgmatic-ui | grep -i "security\|auth\|fail"
```

### 10. Backup Security

#### Backup Encryption

**Always encrypt backups:**
```yaml
# Borgmatic configuration
encryption:
  passphrase: "strong-random-passphrase"
  encryption: repokey-blake2
```

**Passphrase management:**
- Generate with: `openssl rand -base64 32`
- Store securely (password manager, vault)
- Never commit to git
- Backup passphrase separately (can't recover without it!)

#### Off-site Backups

**3-2-1 backup rule:**
- **3** copies of data
- **2** different storage types
- **1** off-site copy

**Secure transmission:**
- Use SSH for remote backups
- Verify host keys
- Use key-based authentication (not passwords)

### 11. Updates & Patching

#### Keep Software Updated

**Application updates:**
```bash
# Pull latest image
docker-compose pull

# Restart with new image
docker-compose up -d
```

**System updates:**
```bash
# Update base system
sudo apt update && sudo apt upgrade -y

# Update Docker
sudo apt install docker-ce docker-ce-cli containerd.io
```

**Monitor for security advisories:**
- GitHub Security Advisories
- Docker Hub security scans
- CVE databases

### 12. Security Headers

**If using reverse proxy, add security headers:**

```nginx
# Nginx example
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Content-Security-Policy "default-src 'self'" always;
```

---

## Security Features

### Built-in Security

- ✅ JWT-based authentication
- ✅ Bcrypt password hashing
- ✅ Rate limiting on API endpoints
- ✅ CORS configuration
- ✅ SQL injection protection (parameterized queries)
- ✅ XSS protection (input sanitization)
- ✅ CSRF protection
- ✅ Secure session management
- ✅ Non-root container execution
- ✅ Encrypted SSH key storage

### Security Validations

**At startup, the application checks:**
- SECRET_KEY is not using default value (in production)
- SECRET_KEY is sufficiently long (≥32 characters)
- Debug mode is disabled (in production)
- All critical environment variables are set

**With `STRICT_SECURITY=true`:**
- Application REFUSES to start if security checks fail
- Recommended for all production deployments

---

## Incident Response

### If You Suspect a Security Breach

1. **Immediate actions:**
   - Change all passwords
   - Rotate SECRET_KEY
   - Review access logs
   - Check for unauthorized users
   - Verify backup integrity

2. **Investigation:**
   - Check logs for suspicious activity
   - Review recent changes
   - Identify entry point
   - Assess damage

3. **Recovery:**
   - Remove unauthorized access
   - Patch vulnerabilities
   - Restore from clean backup if needed
   - Update security measures

4. **Prevention:**
   - Implement additional security controls
   - Update documentation
   - Train team on security practices
   - Schedule regular security audits

### Emergency Contacts

- **Security Issues:** Report via GitHub Security Advisories
- **Support:** Open an issue on GitHub (for non-security matters)

---

## Compliance

### Data Privacy

**This application:**
- Stores user credentials (hashed)
- Logs authentication attempts
- Stores SSH keys (encrypted)
- Stores backup metadata

**Compliance considerations:**
- GDPR: If storing EU user data
- HIPAA: If backing up healthcare data
- PCI-DSS: If backing up payment card data

**Your responsibilities:**
- Secure storage of backups
- Access control
- Data retention policies
- Breach notification procedures

---

## Security Roadmap

**Planned improvements:**
- [ ] Two-factor authentication (2FA)
- [ ] OAuth2/OIDC integration
- [ ] Security audit logging
- [ ] Automated security scanning
- [ ] Intrusion detection
- [ ] API key management
- [ ] Role-based access control (RBAC)
- [ ] Encryption at rest for all sensitive data

---

## Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
- [Borgmatic Security](https://torsion.org/borgmatic/docs/how-to/deal-with-very-large-backups/#security)
- [Let's Encrypt (Free HTTPS)](https://letsencrypt.org/)

---

**Last Updated:** 2025-01-14
**Version:** 1.0.0

© 2025 Karan Hudia. All Rights Reserved.
