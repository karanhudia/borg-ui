---
layout: default
title: SSH Keys
nav_order: 6
description: "Set up SSH keys for remote backup repositories"
---

# SSH Keys Guide

Set up SSH keys for remote backup repositories.

---

## Overview

SSH keys allow Borg Web UI to access remote backup repositories securely without storing passwords. This is essential for:

- Backing up to remote servers
- Storing backups on NAS devices
- Cloud backup services (Hetzner, BorgBase, etc.)
- Offsite backup locations

**Single-Key System:** Borg Web UI uses one system SSH key for all remote connections, simplifying key management while maintaining security.

---

## Quick Start

1. Navigate to **Remote Machines** page
2. Click **Generate System Key** (if not already generated)
3. Select key type (ED25519 recommended)
4. Copy the public key
5. Add it to remote server's `~/.ssh/authorized_keys`
6. Add connections to your remote servers

---

## Generating SSH Keys

### Via Web Interface

1. Go to **Remote Machines** page
2. Click **Generate System Key** (one-time setup)
3. Select key type:
   - **ED25519** (recommended, modern, smaller)
   - **RSA 4096** (maximum compatibility)
4. Click **Generate**

**Note:** You only need to generate the system key once. It will be used for all remote connections.

**How SSH keys are stored:**
- Private keys are encrypted and stored in the SQLite database (`/data/borg.db`)
- At container startup, the system SSH key is deployed to `/home/borg/.ssh/`
- When running as root (`PUID=0`), a symlink `/root/.ssh` → `/home/borg/.ssh` is created automatically
- During backup operations, keys are decrypted from the database and used via temporary files
- `/data/ssh_keys/` is used only for temporary files during deployment and testing operations

### Via Command Line (Alternative)

**Note:** The web interface is strongly recommended as it encrypts keys in the database. Manual key generation creates unencrypted filesystem keys.

```bash
# Generate key inside container (will be stored in filesystem, not database)
docker exec borg-web-ui ssh-keygen -t ed25519 -f /home/borg/.ssh/id_ed25519 -N ""

# View public key
docker exec borg-web-ui cat /home/borg/.ssh/id_ed25519.pub
```

---

## Deploying SSH Keys

### Method 1: Manual Deployment (Most Common)

1. **Get the public key** from Borg Web UI
2. **Copy it to remote server:**

```bash
# On your local machine
ssh user@remote-server

# On remote server
mkdir -p ~/.ssh
echo "ssh-ed25519 AAAAC3... borg-web-ui" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh
```

### Method 2: Using ssh-copy-id

```bash
# From a machine with SSH access to the remote server
ssh-copy-id -i /path/to/public-key.pub user@remote-server
```

### Method 3: Via Control Panel

Many hosting providers and NAS systems have web interfaces to add SSH keys:

**Hetzner Storage Box:**
1. Login to Robot panel
2. Go to your Storage Box
3. Add SSH key under "SSH-Keys" tab

**BorgBase:**
1. Login to BorgBase
2. Go to Account > SSH Keys
3. Add your public key

**Synology NAS:**
1. Control Panel > Terminal & SNMP
2. Enable SSH service
3. User > Advanced > User Home
4. Upload key via File Station to `~/.ssh/authorized_keys`

---

## Testing SSH Connection

### Via Web Interface

1. Go to **Remote Machines** page
2. Click **Add Connection** or **Test Connection** on an existing connection
3. Enter connection details:
   - Host: `remote-server.example.com`
   - Port: `22` (or custom)
   - Username: `backup-user`
4. Click **Test** or **Deploy**

The system automatically uses your system SSH key for all connections.

### Via Command Line

```bash
# Test from inside container using the deployed system key
docker exec borg-web-ui ssh -i /home/borg/.ssh/id_ed25519 user@remote-server -p 22 "echo Connection successful"
```

**Note:** Replace `id_ed25519` with your key type (e.g., `id_rsa`).

---

## Using SSH Keys in Repositories

When creating or importing a repository:

1. Set repository location to SSH format:
   ```
   user@hostname:/path/to/repo
   ```

2. Borg Web UI automatically uses your system SSH key

3. Examples:
   ```
   backup@192.168.1.100:/mnt/backups/borg-repo
   user@server.example.com:~/backups/my-repo
   u123456@u123456.your-storagebox.de:./backup-repo
   ```

**Note:** The same system SSH key is used for all SSH repositories. Ensure you've deployed the key to all remote servers you want to access.

---

## SSH Configuration

### Custom Port

If your server uses a non-standard SSH port, specify it in the repository URL:

```
ssh://user@hostname:2222/path/to/repo
```

### SSH Config File

For advanced configuration, create `/home/borg/.ssh/config`:

```bash
docker exec borg-web-ui tee /home/borg/.ssh/config << 'EOF'
Host backup-server
    HostName server.example.com
    Port 2222
    User backup-user
    IdentityFile /home/borg/.ssh/id_ed25519

Host *.your-storagebox.de
    Port 23
    IdentityFile /home/borg/.ssh/id_ed25519
EOF
```

Then use short names in repository URLs:
```
backup-server:/path/to/repo
```

---

## Security Best Practices

### 1. Use Dedicated Backup User

Create a separate user on the remote server for backups:

```bash
# On remote server
sudo useradd -m -s /bin/bash backup-user
sudo mkdir -p /backups
sudo chown backup-user:backup-user /backups
```

### 2. Restrict SSH Key Permissions

Limit what the SSH key can do:

```bash
# In ~/.ssh/authorized_keys on remote server
command="borg serve --restrict-to-path /backups/borg-repo",restrict ssh-ed25519 AAAAC3... borg-web-ui
```

This:
- Only allows `borg serve` command
- Restricts access to specific repository path
- Prevents shell access

### 3. Use Strong Passphrases (Optional)

For additional security, protect SSH keys with passphrases:

**Note:** Passphrase-protected keys require manual entry and are not supported by the web UI's automated backups.

### 4. Regular Key Rotation

Rotate SSH keys periodically:

1. Generate new key
2. Deploy to servers
3. Test with new key
4. Remove old key from servers
5. Delete old key from Borg Web UI

### 5. Firewall Rules

Restrict SSH access to known IP addresses:

```bash
# On remote server
sudo ufw allow from 192.168.1.0/24 to any port 22
```

---

## Troubleshooting

### Permission Denied (publickey)

**Possible causes:**
1. Public key not added to remote server
2. Wrong username or hostname
3. SSH service not running on remote server
4. Firewall blocking connection

**Solutions:**
```bash
# Verify SSH service is running
ssh user@remote-server "echo success"

# Check SSH key permissions
docker exec borg-web-ui ls -la /home/borg/.ssh/

# Test with verbose output
docker exec borg-web-ui ssh -vvv -i /home/borg/.ssh/id_ed25519 user@remote-server
```

### Host Key Verification Failed

First-time connections require accepting the host key:

```bash
# Accept host key manually
docker exec -it borg-web-ui ssh-keyscan remote-server >> /home/borg/.ssh/known_hosts
```

Or disable host key checking (less secure):

```bash
# In SSH config
Host *
    StrictHostKeyChecking no
    UserKnownHostsFile=/dev/null
```

### Connection Timeout

**Possible causes:**
1. Firewall blocking port 22
2. Wrong hostname/IP
3. Server is down

**Solutions:**
```bash
# Test network connectivity
docker exec borg-web-ui ping -c 3 remote-server

# Test SSH port
docker exec borg-web-ui nc -zv remote-server 22
```

### SSH Key Not Found

Verify the key exists:

```bash
# List SSH keys
docker exec borg-web-ui ls -la /home/borg/.ssh/

# Check key format (for system key)
docker exec borg-web-ui ssh-keygen -l -f /home/borg/.ssh/id_ed25519

# If running as root (PUID=0), verify symlink
docker exec borg-web-ui ls -la /root/.ssh
# Should show: /root/.ssh -> /home/borg/.ssh
```

---

## Common Scenarios

### Hetzner Storage Box

1. Generate ED25519 key in Borg Web UI
2. Copy public key
3. Login to [Hetzner Robot](https://robot.your-server.de/)
4. Go to your Storage Box
5. Add SSH key under "SSH-Keys" tab
6. Use repository URL:
   ```
   ssh://u123456@u123456.your-storagebox.de:23/./backup-repo
   ```

**Note:** Hetzner uses port 23 for SSH, not port 22.

### Synology NAS

1. Enable SSH: Control Panel > Terminal & SNMP
2. Create backup user with home directory
3. Generate key in Borg Web UI
4. Add public key to NAS:
   ```bash
   ssh admin@nas-ip
   sudo mkdir -p /volume1/homes/backup-user/.ssh
   sudo vim /volume1/homes/backup-user/.ssh/authorized_keys
   # Paste public key
   sudo chown -R backup-user:users /volume1/homes/backup-user/.ssh
   sudo chmod 700 /volume1/homes/backup-user/.ssh
   sudo chmod 600 /volume1/homes/backup-user/.ssh/authorized_keys
   ```
5. Use repository URL:
   ```
   backup-user@nas-ip:/volume1/backups/borg-repo
   ```

### Raspberry Pi Remote Backup

1. Set up SSH on Pi: `sudo raspi-config` > Interface Options > SSH
2. Create backup directory: `mkdir -p ~/backups`
3. Generate key in Borg Web UI
4. Deploy key to Pi:
   ```bash
   ssh pi@raspberry-pi
   mkdir -p ~/.ssh
   echo "your-public-key" >> ~/.ssh/authorized_keys
   chmod 600 ~/.ssh/authorized_keys
   ```
5. Use repository URL:
   ```
   pi@raspberry-pi:~/backups/borg-repo
   ```

---

## Single-Key System

Borg Web UI uses a **single system SSH key** for all remote connections. This simplifies key management:

1. **Generate one key**: Create the system SSH key once via **Remote Machines** page
2. **Deploy to multiple servers**: Deploy the same key to all your remote servers
3. **Automatic management**: The system uses this key for all SSH repositories and connections

**Benefits:**
- Simpler management - one key to maintain
- Easier deployment - same key works everywhere
- Automatic usage - no need to select which key to use

**How it works:**
```
System SSH Key → Deployed to:
                 ├─ Server 1 (Hetzner)
                 ├─ Server 2 (NAS)
                 └─ Server 3 (Raspberry Pi)
```

All repositories and connections automatically use the system key.

**Advanced: Custom SSH Config (Optional)**

For advanced scenarios requiring different key types per host, manually configure SSH:

```bash
docker exec borg-web-ui tee -a /home/borg/.ssh/config << 'EOF'
Host special-server
    HostName server.example.com
    User backup
    IdentityFile /home/borg/.ssh/custom_key
EOF
```

**Note:** This is rarely needed. The single system key works for nearly all use cases.

---

## Next Steps

- [Configuration Guide](configuration.md) - Volume mounts and permissions
- [Usage Guide](usage-guide.md) - Create your first backup
- [Notifications Setup](notifications.md) - Get alerts for backup events
