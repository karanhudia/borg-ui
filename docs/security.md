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

### Built-in Authentication (Default)

By default, Borg Web UI uses its own JWT-based authentication system.

#### Change Default Password

On first login, you'll be prompted to change the default password (`admin123`).

**To change later:**
1. Go to **Settings** > **Profile**
2. Enter current password
3. Enter new password (minimum 8 characters)
4. Confirm new password

#### Strong Password Requirements

Use passwords with:
- Minimum 12 characters
- Mix of uppercase and lowercase
- Numbers and special characters
- Unique to this application (no reuse)

**Example strong password:** `B0rg!Backup#2025$Secure`

#### User Management

**For multi-user setups:**
1. Create individual accounts for each user
2. Assign appropriate permissions (admin vs. regular user)
3. Disable or delete inactive accounts
4. Review user access regularly

---

### Proxy/OIDC Authentication

{: .new }
> **New Feature**: Proxy-based authentication for OIDC/SSO integration

Borg Web UI supports **proxy-based authentication** to integrate with external authentication providers like:
- **Authentik**
- **Authelia**
- **Keycloak**
- **Authserv**
- **Google Identity-Aware Proxy (IAP)**
- **Azure AD Application Proxy**
- **Cloudflare Access**
- Any reverse proxy that provides authenticated usernames in headers

#### How It Works

When enabled, Borg Web UI:
1. **Disables the login screen** - No password prompts
2. **Trusts the reverse proxy** - Reads username from HTTP headers
3. **Auto-creates users** - Creates accounts on first access
4. **Maintains authorization** - Still respects admin/user permissions

**Security Model:**
- ✅ Authentication: Handled by your proxy/OIDC provider
- ✅ Authorization: Managed by Borg Web UI (admin vs. regular user)
- ✅ Session management: JWT tokens still used for API calls

#### Configuration

**1. Enable proxy authentication:**

```yaml
environment:
  - DISABLE_AUTHENTICATION=true  # Disable built-in login screen
  - PROXY_AUTH_HEADER=X-Forwarded-User  # Default header name
```

**2. Configure your reverse proxy to forward authenticated usernames:**

The proxy must set the `X-Forwarded-User` header (or your custom header) with the authenticated username.

**Supported Headers (checked in order):**
- `X-Forwarded-User` (default, configurable via `PROXY_AUTH_HEADER`)
- `X-Remote-User`
- `Remote-User`
- `X-authentik-username` (Authentik)

#### Security Requirements

⚠️ **CRITICAL: This feature requires proper security configuration**

**You MUST:**
1. **Bind Borg UI to localhost only:**
   ```yaml
   ports:
     - "127.0.0.1:8081:8081"  # Only accessible via localhost
   ```

2. **Use firewall rules to block direct access:**
   ```bash
   # Block external access to port 8081
   sudo ufw deny 8081
   sudo ufw allow from 127.0.0.1 to any port 8081
   ```

3. **Ensure ONLY your reverse proxy can reach Borg UI**
   - Never expose the container port to the internet
   - Use Docker networks to isolate Borg UI from direct access

**Why this matters:**
- If Borg UI is directly accessible, anyone can set the `X-Forwarded-User` header and impersonate any user
- The proxy MUST strip/override user-supplied headers before forwarding

#### Example Configurations

##### Authentik

**docker-compose.yml:**
```yaml
services:
  borg-ui:
    image: ainullcode/borg-ui:latest
    environment:
      - DISABLE_AUTHENTICATION=true
      - PROXY_AUTH_HEADER=X-authentik-username
    networks:
      - internal
    # NO ports exposed - only accessible via proxy

  authentik-proxy:
    image: ghcr.io/goauthentik/proxy:latest
    environment:
      - AUTHENTIK_HOST=https://auth.example.com
      - AUTHENTIK_INSECURE=false
      - AUTHENTIK_TOKEN=your-outpost-token
    ports:
      - "8443:8443"
    networks:
      - internal
      - external
    labels:
      - "authentik.enabled=true"
      - "authentik.upstream=http://borg-ui:8081"
```

**Authentik Application Setup:**
1. Create new application in Authentik
2. Select **Proxy Provider**
3. Set External URL: `https://backups.example.com`
4. Set Internal URL: `http://borg-ui:8081`
5. Enable **Forward auth (single application)**
6. Set authorization flow and user/group bindings

##### Authelia

**Authelia configuration.yml:**
```yaml
access_control:
  rules:
    - domain: backups.example.com
      policy: one_factor  # or two_factor
      subject:
        - "group:admins"
        - "group:backup-users"
```

**nginx configuration:**
```nginx
server {
    listen 443 ssl http2;
    server_name backups.example.com;

    # SSL configuration...

    # Authelia authentication
    include /path/to/authelia-authrequest.conf;

    location / {
        # Forward authenticated username to Borg UI
        proxy_set_header X-Remote-User $remote_user;
        proxy_set_header X-Forwarded-User $remote_user;

        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

##### Cloudflare Access

**1. Create Cloudflare Access application:**
- Application name: Borg Backups
- Session duration: 24 hours
- Add policies for users/groups

**2. Configure Borg UI:**
```yaml
environment:
  - DISABLE_AUTHENTICATION=true
  - PROXY_AUTH_HEADER=Cf-Access-Authenticated-User-Email
```

**3. Cloudflare Access forwards the user's email in the `Cf-Access-Authenticated-User-Email` header**

##### Nginx with Basic Auth (Simple Setup)

For basic HTTP authentication:

```nginx
server {
    listen 443 ssl http2;
    server_name backups.example.com;

    # SSL configuration...

    auth_basic "Borg Backups";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        # Forward authenticated username
        proxy_set_header X-Remote-User $remote_user;
        proxy_set_header X-Forwarded-User $remote_user;

        proxy_pass http://127.0.0.1:8081;
        # Other proxy headers...
    }
}
```

Create users:
```bash
htpasswd -c /etc/nginx/.htpasswd username
```

#### User Management with Proxy Auth

**First-time access:**
- Users are auto-created when they first access the application
- New users are created as **regular users** (not admins)
- Users inherit the username from the proxy header

**Making users admins:**
1. Admin manually promotes users via Settings > User Management
2. Or update database directly:
   ```bash
   docker exec borg-web-ui sqlite3 /data/borg.db "UPDATE users SET is_admin=1 WHERE username='alice';"
   ```

**Disabling users:**
- Set `is_active=0` in the database
- Or use the User Management interface (when user is admin)

#### Testing Proxy Auth

**Verify headers are being sent:**

```bash
# From your reverse proxy server
curl -H "X-Forwarded-User: testuser" http://localhost:8081/api/auth/me
```

**Check application logs:**
```bash
docker logs borg-web-ui 2>&1 | grep "proxy"
docker logs borg-web-ui 2>&1 | grep "X-Forwarded-User"
```

**Test with direct access (should use fallback):**
```bash
# Without proxy header - falls back to 'admin' user
curl http://localhost:8081/api/auth/me
```

#### Switching Between Auth Methods

**To disable proxy auth and return to built-in authentication:**

1. Remove environment variables:
   ```yaml
   environment:
     # - DISABLE_AUTHENTICATION=true  # Commented out
     # - PROXY_AUTH_HEADER=X-Forwarded-User
   ```

2. Restart container:
   ```bash
   docker compose up -d
   ```

3. Users can now log in with passwords again

**Note:** Existing users created via proxy auth will still exist, but they'll need passwords set by an admin.

#### Troubleshooting

**Problem: Login screen still appears**
- Verify `DISABLE_AUTHENTICATION=true` is set
- Check environment variables: `docker exec borg-ui env | grep DISABLE`
- Restart container after changing environment

**Problem: "Could not validate credentials" errors**
- Check proxy is sending the authentication header
- Verify header name matches `PROXY_AUTH_HEADER`
- Check logs: `docker logs borg-web-ui | grep "proxy"`

**Problem: Wrong user is logged in**
- Proxy may not be stripping user-supplied headers
- Verify Borg UI is only accessible via proxy (not directly)
- Check firewall rules and port bindings

**Problem: Users can't access after proxy auth is enabled**
- First access auto-creates regular users (not admins)
- Admin must manually promote users to admin
- Check user status: `docker exec borg-web-ui sqlite3 /data/borg.db "SELECT * FROM users;"`

#### Security Checklist for Proxy Auth

- [ ] `DISABLE_AUTHENTICATION=true` is set
- [ ] Borg UI bound to localhost only (`127.0.0.1:8081`)
- [ ] Firewall blocks external access to port 8081
- [ ] Reverse proxy is configured to authenticate users
- [ ] Reverse proxy strips user-supplied authentication headers
- [ ] HTTPS is enabled on the reverse proxy
- [ ] Reverse proxy has proper access controls (groups, 2FA, etc.)
- [ ] First admin user has been promoted manually
- [ ] Tested that direct access falls back safely
- [ ] Application logs reviewed for proxy auth events

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
