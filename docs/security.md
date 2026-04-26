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

#### Two-Factor Authentication (TOTP)

Borg UI supports built-in TOTP for local password-based accounts.

**What it does:**
- Adds a second factor after username/password login
- Issues single-use recovery codes during setup
- Supports disabling TOTP with the current password plus an authenticator or recovery code

**How to enable it:**
1. Go to **Settings** > **Account**
2. Under **Two-factor authentication**, choose **Enable TOTP**
3. Confirm your current password
4. Add the displayed secret to your authenticator app
5. Save the recovery codes somewhere secure
6. Enter the current 6-digit authenticator code to finish setup

**Notes:**
- TOTP is only available for Borg UI's built-in local accounts
- Proxy-auth / external SSO deployments should enforce MFA in the identity provider instead
- Recovery codes are shown during setup, so they must be stored before closing the dialog

#### Passkeys

Borg UI also supports WebAuthn passkeys for local accounts.

**What it does:**
- Lets users sign in with device-bound passkeys instead of typing a password
- Stores multiple passkeys per account
- Supports removing passkeys from **Settings** > **Account**

**Notes:**
- Passkeys require the Python `webauthn` dependency to be installed
- Passkey enrollment currently requires confirming the current account password first
- Reverse-proxy / external SSO deployments should usually keep passkeys in the identity provider instead of inside Borg UI

#### Emergency Password Reset (CLI)

Use this procedure when a user (including the admin) is locked out of the web UI and cannot change their password through **Settings > Profile**.

{: .warning }
> **Security warning:** This tool requires shell access to the container or host. Treat shell access as equivalent to full admin access — anyone who can run `docker exec` can reset any password.

**Docker (primary method):**

```bash
docker exec -it borg-ui python -m app.scripts.reset_password <username> <new_password>
```

Concrete example:

```bash
docker exec -it borg-ui python -m app.scripts.reset_password admin newpassword123
```

**Non-Docker / custom database path:**

Set the `BORG_DB_PATH` environment variable to override the default `/data/borg.db`:

```bash
BORG_DB_PATH=/custom/path/borg.db python -m app.scripts.reset_password admin newpassword123
```

**Behaviour:** The script sets `must_change_password = 0`, so the user is not forced to change the password again immediately after logging in.

---

### SSO Authentication

{: .new }
> Borg UI supports two enterprise SSO patterns: built-in OIDC and reverse-proxy header authentication.

Use **built-in OIDC** when you want Borg UI to be the OIDC client itself. Use **proxy-header mode** when an existing access gateway or authenticated reverse proxy already sits in front of Borg UI and you want Borg UI to trust only that proxy.

#### Choosing a Mode

**Built-in OIDC is the recommended default for new enterprise deployments.**

Use **built-in OIDC** when:
- your identity provider supports standard OpenID Connect
- you want Borg UI to redirect users to the IdP and handle the callback itself
- you want less reliance on trusted inbound identity headers
- you want a cleaner fit for Authentik, Keycloak, Okta, Entra ID, Google, or similar providers

Use **proxy-header mode** when:
- you already have an authenticated reverse proxy, access gateway, or forward-auth layer
- the same upstream access layer protects multiple internal apps
- your environment already standardizes on forwarded identity headers
- you need the proxy to inject extra trusted headers for Borg UI-specific role mapping

Do not enable both modes for the same public entrypoint. Pick one trust model and document it clearly.

#### Built-in OIDC Mode

In built-in OIDC mode, Borg UI acts as the OIDC client:
1. Borg UI redirects the user to the identity provider
2. the identity provider authenticates the user
3. Borg UI receives the callback and validates the response
4. Borg UI provisions or updates the local user record
5. Borg UI issues its normal application session token

This keeps identity in the IdP while keeping Borg UI's own authorization model for app-local permissions.

##### Built-in OIDC Security Model

- Authentication is handled by the OIDC provider
- Borg UI validates the OIDC response before creating a local session
- Borg UI still maintains its own user record, role, repository permissions, and audit context
- MFA should usually be enforced in the identity provider, not reimplemented inside Borg UI for SSO users

##### Built-in OIDC Hardening

Borg UI's OIDC flow includes the main hardening controls you should expect:
- **PKCE** protects the authorization code flow against intercepted codes
- **Signed and time-limited `state`** protects against CSRF and callback mix-up attacks
- **Provider logout support** can redirect the browser to the IdP's logout flow when configured
- **Local session exchange** keeps the browser on Borg UI's normal token model after the callback

Operationally, you should still:
- terminate TLS in front of Borg UI
- use the correct public URL and redirect URI
- avoid mismatched internal and public callback URLs unless you intentionally configure an override
- keep time synchronization correct on both Borg UI and the IdP

##### Built-in OIDC User Provisioning

Built-in OIDC still creates or updates Borg UI users locally. Typical patterns are:
- `viewer`: first login creates a regular user with a safe default role
- `pending`: first login creates an approval-required local user until an admin reviews access
- `template`: first login copies permissions from a designated template user
- `deny`: only pre-created or already-approved users may sign in

For enterprise environments, `pending` or `template` is often the right fit when you need tighter onboarding control.

**Pending approvals at a high level:**
- the user can authenticate with the IdP successfully
- Borg UI still blocks access until a Borg UI admin approves or promotes that local account
- this separates "identity is valid" from "this person is allowed to operate backups here"

##### Built-in OIDC Role Mapping

If your IdP emits trusted claims for application roles, Borg UI can map them into its own authorization model.

Recommended approach:
- keep IdP access control coarse: who may access Borg UI at all
- keep Borg UI authorization explicit: `viewer`, `operator`, `admin`
- only map roles from IdP claims if your organization is prepared to manage those claims carefully

Treat role claims as security-sensitive. A bad claim mapping can over-privilege users just as easily as a bad proxy header mapping.

##### Built-in OIDC Setup Checklist

At minimum you need:
- OIDC discovery URL or provider endpoints
- client ID
- client secret for confidential-client deployments
- exact redirect URI registered in the provider
- claim mapping for username, and optionally email/full name
- a decision on new-user behavior: `viewer`, `pending`, `template`, or `deny`

##### Authentik Notes for Built-in OIDC

Typical Authentik setup:
1. Create an **OAuth2/OpenID Provider**
2. Set the Borg UI redirect URI exactly to Borg UI's callback URL
3. Assign users or groups through Authentik application bindings
4. Prefer group or policy control in Authentik for "can access Borg UI"
5. Optionally emit claims for Borg UI role mapping if you want centralized authorization

Recommended Authentik claim choices:
- username claim: a stable username or preferred username
- email claim: the primary email
- full-name claim: display name

Prefer stable identifiers. Do not map Borg UI usernames from display-only values that may change frequently.

##### Keycloak Notes for Built-in OIDC

Typical Keycloak setup:
1. Create a confidential OIDC client for Borg UI
2. Add the exact Borg UI redirect URI
3. Use standard scopes like `openid profile email`
4. Control access through realm/client roles or groups
5. Add protocol mappers only when you intentionally want Borg UI-specific claims

With Keycloak, be explicit about:
- valid redirect URIs
- post-logout redirect URIs if you use provider logout
- whether role claims come from realm roles, client roles, or groups

##### Built-in OIDC Logout

Logout has two layers:
- Borg UI local logout: clear the app session
- provider logout: optionally redirect the browser to the IdP's logout endpoint

The exact result depends on the provider:
- some providers fully clear the upstream SSO session
- some only end the application session
- some require a configured post-logout redirect URI

Test logout explicitly with your chosen provider. Do not assume all IdPs behave the same way.

##### Troubleshooting Built-in OIDC

**Problem: Login redirects to the IdP but callback fails**
- check the registered redirect URI exactly
- check whether Borg UI is behind a reverse proxy with the correct public URL
- check whether you need a redirect URI override for split internal/public URLs

**Problem: Login succeeds at the IdP but Borg UI denies access**
- review the new-user mode (`deny`, `pending`, `template`, `viewer`)
- check the username claim mapping
- check whether the user was created locally and whether it needs approval

**Problem: Logout returns to the wrong place**
- verify the provider end-session URL
- verify post-logout redirect settings on the IdP
- verify any Borg UI logout override you configured

#### Proxy-Header Mode

Proxy-header mode disables the Borg UI login screen and trusts identity headers from a reverse proxy or access gateway.

Supported upstream patterns include:
- Authentik proxy or outpost mode
- Authelia
- Keycloak or another IdP behind a forward-auth gateway
- Cloudflare Access
- Google Identity-Aware Proxy
- Azure AD Application Proxy
- any reverse proxy that injects a trusted authenticated username header

##### How Proxy-Header Mode Works

When enabled, Borg UI:
1. disables the login screen
2. reads the username from a trusted header
3. auto-creates users on first access
4. can optionally map Borg UI roles, repository-wide roles, email, or full name from additional trusted headers
5. rejects requests that do not include the required identity header

**Security model:**
- authentication is handled by the proxy or gateway
- Borg UI authorization still happens inside Borg UI
- Borg UI trusts the proxy, not the browser

##### Proxy-Header Configuration

```yaml
environment:
  - DISABLE_AUTHENTICATION=true
  - PROXY_AUTH_HEADER=X-Forwarded-User
  - PROXY_AUTH_ROLE_HEADER=X-Borg-Role
  - PROXY_AUTH_ALL_REPOSITORIES_ROLE_HEADER=X-Borg-All-Repositories-Role
  - PROXY_AUTH_EMAIL_HEADER=X-Borg-Email
  - PROXY_AUTH_FULL_NAME_HEADER=X-Borg-Full-Name
```

**Supported identity headers when using the default username header:**
- `X-Forwarded-User`
- `X-Remote-User`
- `Remote-User`
- `X-authentik-username`

If you set a custom `PROXY_AUTH_HEADER`, Borg UI trusts only that configured header for identity.

**Optional authorization headers:**
- `PROXY_AUTH_ROLE_HEADER`: `viewer`, `operator`, `admin`
- `PROXY_AUTH_ALL_REPOSITORIES_ROLE_HEADER`: `viewer`, `operator`
- `PROXY_AUTH_EMAIL_HEADER`
- `PROXY_AUTH_FULL_NAME_HEADER`

Invalid role values are ignored rather than silently elevating access.

##### Proxy-Header Hardening Requirements

⚠️ **Proxy-header mode is safe only when Borg UI is reachable exclusively through the authenticated proxy path.**

You must:
1. bind Borg UI to localhost or a private internal Docker network
2. block direct access to the Borg UI container port
3. ensure the reverse proxy strips or overwrites user-supplied identity headers
4. expose only the reverse proxy to users
5. treat any trusted role-mapping header as security-sensitive

**Example localhost binding:**
```yaml
ports:
  - "127.0.0.1:8081:8081"
```

**Example firewall policy:**
```bash
sudo ufw deny 8081
sudo ufw allow from 127.0.0.1 to any port 8081
```

Why this matters:
- if users can reach Borg UI directly, they may be able to forge `X-Forwarded-User` or any other trusted header
- the proxy must be the only entity allowed to present identity to Borg UI

##### Proxy-Header Role Mapping

If your proxy or IdP emits trusted claims as headers, Borg UI can map them into its built-in authorization model.

Behavior:
- new users default to `viewer` unless a valid trusted role header is configured
- existing users are updated on login when a valid trusted role header is present
- invalid role values are ignored instead of blocking login

Example:
```yaml
environment:
  - DISABLE_AUTHENTICATION=true
  - PROXY_AUTH_HEADER=X-authentik-username
  - PROXY_AUTH_ROLE_HEADER=X-Borg-Role
  - PROXY_AUTH_ALL_REPOSITORIES_ROLE_HEADER=X-Borg-All-Repositories-Role
  - PROXY_AUTH_EMAIL_HEADER=X-Borg-Email
  - PROXY_AUTH_FULL_NAME_HEADER=X-Borg-Full-Name
```

Example reverse-proxy forwarding:
```nginx
proxy_set_header X-authentik-username $upstream_http_x_authentik_username;
proxy_set_header X-Borg-Role $upstream_http_x_borg_role;
proxy_set_header X-Borg-All-Repositories-Role $upstream_http_x_borg_all_repositories_role;
proxy_set_header X-Borg-Email $upstream_http_x_borg_email;
proxy_set_header X-Borg-Full-Name $upstream_http_x_borg_full_name;
```

##### Authentik Notes for Proxy-Header Mode

The common Authentik pattern here is:
1. protect Borg UI with an Authentik proxy provider or outpost
2. forward `X-authentik-username` as the primary identity header
3. optionally forward additional trusted headers for Borg UI roles or profile data
4. keep Borg UI itself private behind the Authentik-protected proxy

##### Keycloak Notes for Proxy-Header Mode

Keycloak usually fits proxy-header mode only when another access layer is translating a successful Keycloak login into trusted headers. In that setup:
- the gateway authenticates against Keycloak
- the gateway injects the trusted username header
- Borg UI trusts the gateway, not Keycloak directly

If you want Borg UI to talk to Keycloak itself, built-in OIDC is usually the cleaner model.

##### Testing Proxy-Header Mode

Verify the expected behavior directly:

```bash
# Should fail closed without the trusted header
curl -i http://localhost:8081/api/auth/me

# Should succeed only when the trusted header is present
curl -i -H "X-Forwarded-User: testuser" http://localhost:8081/api/auth/me
```

Check logs:
```bash
docker logs borg-web-ui 2>&1 | grep "proxy"
```

##### Switching Between Modes

To return from proxy-header mode to local login, remove the proxy-auth environment variables and restart the container.

To move from proxy-header mode to built-in OIDC, remove the proxy-header trust configuration first. Avoid leaving an old trusted-header path reachable after switching to OIDC.

##### Security Checklist for SSO

- [ ] HTTPS is enabled in front of Borg UI
- [ ] You chose one SSO trust model per public entrypoint: built-in OIDC or proxy-header mode
- [ ] Redirect URIs exactly match the public Borg UI URL
- [ ] MFA is enforced in the identity provider for SSO users
- [ ] New-user behavior is intentional: `viewer`, `pending`, `template`, or `deny`
- [ ] Pending-user approval workflow is documented if you use `pending`
- [ ] Role mapping is reviewed before trusting IdP claims or proxy headers
- [ ] Logout behavior has been tested with your provider
- [ ] For proxy-header mode, Borg UI is not directly reachable by end users
- [ ] For proxy-header mode, the proxy strips or overwrites user-supplied identity headers

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
