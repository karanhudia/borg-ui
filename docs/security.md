---
layout: default
title: Security
nav_order: 7
description: "Best practices and security recommendations"
---

# Security Guide

Best practices for securing your Borg Web UI installation.

---

## Quick Security Checklist

- [ ] Change default admin password immediately
- [ ] Use HTTPS with reverse proxy (production)
- [ ] Restrict volume mounts to necessary directories only
- [ ] Set appropriate PUID/PGID for file permissions
- [ ] Use SSH keys (not passwords) for remote repositories
- [ ] Enable firewall rules to limit access
- [ ] Regularly update to latest version
- [ ] Backup the `/data` volume (contains database and keys)
- [ ] Review and rotate SSH keys periodically
- [ ] Monitor application logs for suspicious activity

---

## Authentication Security

### Change Default Password

On first login, you'll be prompted to change the default password (`admin123`).

**To change later:**
1. Go to **Settings** > **Profile**
2. Enter current password
3. Enter new password (minimum 8 characters)
4. Confirm new password

### Strong Password Requirements

Use passwords with:
- Minimum 12 characters
- Mix of uppercase and lowercase
- Numbers and special characters
- Unique to this application (no reuse)

**Example strong password:** `B0rg!Backup#2025$Secure`

### User Management

**For multi-user setups:**
1. Create individual accounts for each user
2. Assign appropriate permissions (admin vs. regular user)
3. Disable or delete inactive accounts
4. Review user access regularly

---

## Network Security

### Use HTTPS in Production

**Never expose Borg Web UI directly to the internet without HTTPS.**

#### Option 1: Nginx Reverse Proxy

```nginx
server {
    listen 443 ssl http2;
    server_name backups.example.com;

    ssl_certificate /etc/letsencrypt/live/backups.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/backups.example.com/privkey.pem;

    # Strong SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    location / {
        proxy_pass http://localhost:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### Option 2: Traefik with Let's Encrypt

```yaml
services:
  borg-ui:
    image: ainullcode/borg-ui:latest
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.borg-ui.rule=Host(`backups.example.com`)"
      - "traefik.http.routers.borg-ui.entrypoints=websecure"
      - "traefik.http.routers.borg-ui.tls.certresolver=letsencrypt"
      - "traefik.http.services.borg-ui.loadbalancer.server.port=8081"
```

#### Option 3: Caddy (Automatic HTTPS)

```
backups.example.com {
    reverse_proxy localhost:8081
}
```

### Restrict Access by IP

**Docker-level restriction:**
```yaml
ports:
  - "127.0.0.1:8081:8081"  # Only localhost
```

**Firewall rules:**
```bash
# Linux (ufw)
sudo ufw allow from 192.168.1.0/24 to any port 8081

# Linux (iptables)
sudo iptables -A INPUT -p tcp -s 192.168.1.0/24 --dport 8081 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 8081 -j DROP
```

### VPN Access

For remote access, use VPN instead of exposing to internet:
- WireGuard
- OpenVPN
- Tailscale
- ZeroTier

---

## File System Security

### Restrict Volume Mounts

**⚠️ Critical Security Practice**

**Never mount the entire filesystem in production:**
```yaml
volumes:
  # ❌ DANGEROUS: Full filesystem access
  - /:/local:rw  # Development/testing ONLY
```

**✅ Recommended (principle of least privilege):**
```yaml
volumes:
  # Application data (required)
  - borg_data:/data
  - borg_cache:/home/borg/.cache/borg

  # Backup sources - mount only what you need
  - /home/username:/local:ro              # Home directory (read-only)
  - /var/www:/local/www:ro                # Website files (read-only)
  - /mnt/backups:/local/backup:rw         # Backup destination (read-write)
```

**Why this matters:**
- **Reduces attack surface** - Container can only access specified directories
- **Prevents data leakage** - Accidental exposure is limited to mounted paths
- **Audit trail** - Clear documentation of what's accessible
- **Defense in depth** - If container is compromised, damage is contained

### Set Appropriate Permissions

Match container user with host user:

```yaml
environment:
  - PUID=1000  # Your user ID
  - PGID=1000  # Your group ID
```

This prevents:
- Unauthorized file access
- Permission denied errors
- Files owned by root when created by container

### Read-Only Mounts for Sources

**Always mount backup sources as read-only when possible:**

```yaml
volumes:
  # ✅ Read-only for backup-only directories
  - /var/www:/local/www:ro            # Can't be modified
  - /home/user/documents:/local:ro    # Protected from writes

  # ⚠️ Read-write only when needed for restores
  - /mnt/backups:/local/backup:rw     # Backup storage location
```

**Benefits:**
- Prevents accidental modification during backup operations
- Protects against ransomware that might target backup source
- Makes it clear which directories are backup sources vs. destinations
- Additional layer of protection if backup script has bugs

---

## SSH Security

### Use SSH Keys (Not Passwords)

**Always use SSH keys for remote repositories.**

Generate keys through the web interface:
1. Go to **SSH Keys**
2. Click **Generate SSH Key**
3. Use ED25519 (modern) or RSA 4096 (compatible)

### Restrict SSH Key Access

On the remote server, restrict what the key can do:

```bash
# In ~/.ssh/authorized_keys
command="borg serve --restrict-to-path /backups/borg-repo",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 AAAAC3... borg-web-ui
```

This:
- Limits to `borg serve` command only
- Restricts access to specific path
- Disables port forwarding
- Disables X11 forwarding
- Prevents interactive shell

### SSH Server Hardening

On remote backup servers:

```bash
# /etc/ssh/sshd_config
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
AllowUsers backup-user
Port 2222  # Use non-standard port
```

Restart SSH: `sudo systemctl restart sshd`

---

## Repository Security

### Use Encryption

**Always encrypt repositories**, especially for offsite/cloud backups.

Choose encryption mode when creating repository:
- **repokey-blake2** (recommended) - Key stored in repo, fast
- **keyfile-blake2** - Key stored locally only
- **repokey** - AES-256, widely compatible

### Strong Passphrases

Use strong repository passphrases:
- Minimum 20 characters
- Mix of characters, numbers, symbols
- Generated randomly (use password manager)
- Unique per repository

**Example:** `Xk9#mP2$vL8@qR5!wT3&hN7*`

### Store Passphrases Securely

- Use a password manager (Bitwarden, 1Password, KeePass)
- **Never** commit passphrases to git
- Document where passphrase is stored
- Have a recovery plan

### Backup Repository Keys

For `keyfile` encryption mode:

```bash
# Export key
docker exec borg-web-ui borg key export /path/to/repo backup-key.txt

# Store securely (offline, encrypted USB drive, password manager)
```

**Without the key, your backups are unrecoverable.**

---

## Application Security

### SECRET_KEY Rotation

The SECRET_KEY is used for session management and JWT tokens.

**To rotate:**
```bash
docker exec borg-web-ui rm /data/.secret_key
docker restart borg-web-ui
```

**Note:** This logs out all users and invalidates all tokens.

### Database Encryption

The SQLite database contains:
- User credentials (hashed)
- Repository configurations
- Notification service URLs (may contain credentials)
- SSH key paths

**Protect `/data` volume:**
- Secure file permissions
- Regular backups
- Encrypt at rest (LUKS, dm-crypt)

### Secure Notification URLs

Notification service URLs often contain credentials:

```
mailto://user:app_password@gmail.com?smtp=smtp.gmail.com
slack://TokenA/TokenB/TokenC/
```

**Best practices:**
- Don't share notification configurations
- Rotate tokens periodically
- Use least-privilege service accounts

---

## Monitoring and Auditing

### Enable Logging

```yaml
environment:
  - LOG_LEVEL=INFO  # or DEBUG for troubleshooting
```

**Application logs** are sent to Docker logs (stdout/stderr). **Job logs** are stored in `/data/logs/`.

### Review Logs Regularly

```bash
# View application logs (authentication, errors, API requests)
docker logs borg-web-ui

# Tail application logs in real-time
docker logs -f borg-web-ui

# Search for failed logins
docker logs borg-web-ui 2>&1 | grep "authentication failed"

# Check for errors
docker logs borg-web-ui 2>&1 | grep "ERROR"

# View job logs (backup, check, compact operations)
docker exec borg-web-ui ls -lh /data/logs/
```

### Monitor Failed Login Attempts

Watch for suspicious activity:
```bash
# Failed authentication attempts
docker logs borg-web-ui 2>&1 | grep "401 Unauthorized"

# Multiple failed attempts from same IP
docker logs borg-web-ui 2>&1 | grep "authentication" | sort | uniq -c
```

### Set Up Alerts

Use [notifications](notifications.md) to get alerts for:
- Backup failures
- Schedule failures
- System errors

---

## Update Security

### Keep Software Updated

```bash
# Check for updates
docker pull ainullcode/borg-ui:latest

# Update
docker compose pull
docker compose up -d
```

### Subscribe to Security Announcements

- Watch GitHub repository for security releases
- Check [GitHub Security Advisories](https://github.com/karanhudia/borg-ui/security/advisories)
- Review release notes for security fixes

---

## Backup Security

### Backup Strategy

**3-2-1 Rule:**
- **3** copies of data
- **2** different media types
- **1** offsite backup

### Secure Backup Locations

**For offsite backups:**
- Use encrypted repositories
- Verify physical security of remote location
- Use VPN or SSH tunnels for transmission
- Regular integrity checks

### Test Restores

Regularly test restoring from backups:
1. Verify backups are accessible
2. Check data integrity
3. Confirm encryption keys work
4. Document restore procedures

---

## Incident Response

### If Credentials Are Compromised

1. **Change passwords immediately**
   - Admin password in Borg Web UI
   - Repository passphrases
   - Remote server passwords

2. **Rotate SSH keys**
   - Generate new keys
   - Deploy to servers
   - Remove old keys

3. **Rotate SECRET_KEY**
   ```bash
   docker exec borg-web-ui rm /data/.secret_key
   docker restart borg-web-ui
   ```

4. **Review logs for unauthorized access**

5. **Check backups for tampering**

### If Container Is Compromised

1. **Stop the container immediately**
   ```bash
   docker stop borg-web-ui
   ```

2. **Preserve logs for analysis**
   ```bash
   docker logs borg-web-ui > incident-logs.txt
   ```

3. **Check for malware**

4. **Restore from known-good backup**

5. **Investigate root cause**

6. **Update and strengthen security**

---

## Security Best Practices Summary

1. **Authentication**
   - Strong unique passwords
   - Change default credentials
   - Regular password rotation

2. **Network**
   - Always use HTTPS in production
   - Restrict access by IP/VPN
   - Never expose directly to internet

3. **File System**
   - Restrict volume mounts
   - Use read-only for sources
   - Proper PUID/PGID

4. **SSH**
   - Use keys, not passwords
   - Restrict key permissions
   - Non-standard ports

5. **Repositories**
   - Always use encryption
   - Strong passphrases
   - Backup repository keys

6. **Monitoring**
   - Enable logging
   - Review logs regularly
   - Set up failure alerts

7. **Updates**
   - Keep software current
   - Subscribe to security announcements
   - Test updates in staging first

---

## Security Resources

- [Borg Backup Security](https://borgbackup.readthedocs.io/en/stable/quickstart.html#important-note-about-free-space)
- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Let's Encrypt](https://letsencrypt.org/)

---

## Reporting Security Issues

If you discover a security vulnerability:

1. **Do NOT open a public issue**
2. Email: security contact via GitHub Security Advisories
3. Include:
   - Description of vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We take security seriously and will respond promptly.
