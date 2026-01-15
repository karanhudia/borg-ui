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

**🎯 UI-First Approach:** Everything is done through the web interface - no terminal commands needed! Just click **Deploy Key to Server**, enter your server password, and the UI handles the rest.

**Single-Key System:** Borg Web UI uses one system SSH key for all remote connections, simplifying key management while maintaining security.

---

## Quick Start (UI-Based Setup)

**Everything is done through the web interface - no terminal needed!**

1. Go to **Remote Machines** page
2. Click **Generate System Key** (one-time setup)
3. Click **Deploy Key to Server**
4. Enter your remote server details:
   - Host (e.g., `192.168.1.100`)
   - Username (e.g., `root` or `backup-user`)
   - Password (used once for deployment)
   - Mount point (optional, e.g., `/mnt/remote-server`)
   - Default path (optional, e.g., `/backups`)
5. Click **Deploy** - the UI automatically installs your SSH key!
6. Done! Your remote machine is now ready for backups

**That's it!** No manual SSH commands needed. The key is automatically deployed and your connection is saved.

---

## Managing SSH Keys

### Generating a New SSH Key

**Via Web Interface:**

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

---

### Importing an Existing SSH Key

**Use Case:** Import an SSH key from your host filesystem (e.g., mounted Docker volume) instead of generating a new one.

**Via Web Interface:**

1. Go to **Remote Machines** page
2. Click **Import System Key**
3. Fill in the import form:
   ```
   Key Name: System SSH Key
   Private Key Path: /home/borg/.ssh/id_ed25519
   Public Key Path: (leave empty to auto-detect .pub file)
   Description: Imported system SSH key
   ```
4. Click **Import**

**What happens:**
- The UI reads the key files from the specified paths
- Keys are encrypted and stored in the database
- The system key is deployed to `/home/borg/.ssh/`
- You can now use the imported key for all connections

**Common scenarios:**
```bash
# Mount your existing SSH key when starting the container
docker run -v ~/.ssh:/host-ssh:ro \
  -v /path/to/data:/data \
  borgui/borg-web-ui

# Then import from: /host-ssh/id_ed25519
```

**Note:** The imported key must be readable by the container user. Use appropriate volume mount permissions.

---

### Deleting the SSH Key

**Warning:** Deleting the system SSH key will prevent all SSH-based backups and connections from working until you generate or import a new key.

**Via Web Interface:**

1. Go to **Remote Machines** page
2. Click **Delete Key** (trash icon next to the key)
3. Confirm deletion
4. The key is removed from the database and filesystem

**What happens:**
- System SSH key is deleted from the database
- Key files removed from `/home/borg/.ssh/`
- All existing SSH connections will fail until a new key is generated or imported
- Remote servers still have the old public key in `authorized_keys` (manual cleanup recommended)

**After deletion:**
- Generate a new key or import an existing one
- Re-deploy to all your remote servers

---

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

### Method 1: Automatic Deployment via Web UI (Recommended)

**The easiest way - everything is done through the interface:**

1. Go to **Remote Machines** page
2. Click **Deploy Key to Server** button
3. Fill in the deployment form:
   ```
   Host: 192.168.1.100
   Port: 22
   Username: root
   Password: your-server-password
   Default Path: /backups (optional)
   Mount Point: /mnt/remote-server (optional)
   ```
4. Click **Deploy**

**What happens:**
- UI connects to your server using the password (SSH password authentication)
- Automatically creates `~/.ssh/` directory with correct permissions
- Installs your public key to `~/.ssh/authorized_keys`
- Saves the connection in your Remote Machines list
- You can now use SSH key authentication (no more passwords needed!)

**Benefits:**
- ✅ No terminal commands needed
- ✅ Automatic permission setting
- ✅ Connection saved for future use
- ✅ Password only used once for initial setup

---

### Re-deploying to Existing Connections

**Use Case:** Deploy your current system SSH key to a connection that was previously set up, or after rotating your SSH key.

1. Go to **Remote Machines** page
2. Find the connection in the **Remote Connections** list
3. Click **Deploy to Server** button (three dots menu)
4. Enter the SSH password for authentication
5. Click **Deploy Key**

**What happens:**
- Your current system SSH key is deployed to the connection
- Existing `authorized_keys` is updated with the new public key
- Old key remains in place (doesn't remove previous entries)
- Connection details (host, port, username) are already filled from saved connection

**When to use:**
- After rotating your SSH key (deleted and generated new one)
- After importing a different SSH key
- When a remote server was rebuilt and needs the key re-deployed
- Testing key deployment without creating a new connection

---

### Adding Connections Manually (Without Deployment)

**Use Case:** Add a connection where the SSH key is already deployed, or you deployed it manually.

1. Go to **Remote Machines** page
2. Click **Add Manual Connection**
3. Fill in connection details:
   ```
   Host: 192.168.1.100
   Port: 22
   Username: root
   Default Path: /backups (optional)
   Mount Point: /mnt/remote-server (optional)
   ```
4. Click **Add Connection**

**What happens:**
- Connection is saved to your list
- **No password needed** - assumes key is already deployed
- You can test the connection immediately
- Connection is ready to use for repositories

**When to use:**
- SSH key already deployed via control panel (Hetzner, BorgBase, etc.)
- Key deployed manually via command line
- Migrating from another backup system
- Remote server doesn't support password authentication

---

### Testing Connections

**Test before using in production:**

1. Go to **Remote Machines** page
2. Find connection in the list
3. Click **Test Connection** button
4. View test results:
   - ✅ Success: Connection works, SSH key is properly configured
   - ❌ Failed: Shows error message (permission denied, timeout, etc.)

**What it tests:**
- Network connectivity to the host
- SSH port accessibility
- SSH key authentication
- Permission to execute commands

**Troubleshooting:**
- If test fails, check:
  - Host/IP is correct and accessible
  - SSH port is open (firewall rules)
  - Username exists on remote server
  - SSH key is properly deployed to `~/.ssh/authorized_keys`
  - Permissions are correct (`chmod 600 authorized_keys`, `chmod 700 ~/.ssh`)

---

### Method 2: Manual Deployment (Alternative)

If you prefer manual deployment or password authentication is disabled:

1. **Get the public key** from Remote Machines page
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

## Managing Remote Connections

### Editing Connections

**Update connection details (host, port, username, paths):**

1. Go to **Remote Machines** page
2. Find connection in the **Remote Connections** list
3. Click **Edit** button (three dots menu)
4. Update any field:
   - Host
   - Username
   - Port
   - Default Path
   - Mount Point
5. Click **Save**

**Note:** Editing a connection does not re-deploy the SSH key. If you changed the host or username, you may need to deploy the key again.

---

### Deleting Connections

**Remove a saved connection:**

1. Go to **Remote Machines** page
2. Find connection in the **Remote Connections** list
3. Click **Delete** button (three dots menu)
4. Confirm deletion

**What happens:**
- Connection is removed from Borg Web UI
- SSH key remains on the remote server (in `~/.ssh/authorized_keys`)
- Repositories using this connection may still work (if using the same host/username)

**Manual cleanup on remote server:**
```bash
# Remove the public key from authorized_keys
ssh user@remote-server
vim ~/.ssh/authorized_keys
# Delete the line starting with "ssh-ed25519 ... borg-web-ui"
```

---

### Testing SSH Connection

**Via Web Interface:**

1. Go to **Remote Machines** page
2. Click **Test Connection** on an existing connection
3. View test results

The system automatically uses your system SSH key for all connections.

**Via Command Line:**

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

Rotate SSH keys periodically for security:

**Via Web Interface:**

1. **Generate new key:**
   - Go to Remote Machines page
   - Click **Generate System Key**
   - Select key type (ED25519 recommended)
   - Click **Generate**
   - Old key is automatically replaced

2. **Deploy to all servers:**
   - For each connection in your list:
     - Click **Deploy to Server** (three dots menu)
     - Enter SSH password
     - Click **Deploy Key**
   - Or manually add the new public key to each server

3. **Test connections:**
   - Click **Test Connection** for each remote machine
   - Verify all connections work with the new key

4. **Clean up old key:**
   - SSH to each remote server
   - Edit `~/.ssh/authorized_keys`
   - Remove the old key line (will have old timestamp)
   - Keep the new key line

**Alternative with Import:**

If you generate keys externally:
1. Generate new key on host system
2. Delete old key in Borg Web UI
3. Import new key from filesystem
4. Re-deploy to all servers

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

**If key is missing:**
- Generate new key via Remote Machines page
- Or import existing key from mounted volume
- Deploy to all remote servers

### Rotating Compromised Keys

**If you suspect your SSH key is compromised:**

1. **Immediately generate a new key:**
   - Go to Remote Machines page
   - Generate System Key (replaces old key)

2. **Deploy new key to all servers:**
   - Use **Deploy to Server** on each connection
   - Or manually deploy via control panels

3. **Remove old key from servers:**
   ```bash
   # On each remote server
   vim ~/.ssh/authorized_keys
   # Delete the compromised key line
   ```

4. **Verify all connections:**
   - Test each connection in Remote Machines page
   - Check that backups still work

### Import Fails with Permission Denied

**If importing an SSH key fails:**

1. **Check file permissions:**
   ```bash
   # Files must be readable by container user
   ls -la /path/to/key
   ```

2. **Fix permissions if needed:**
   ```bash
   # On host system
   chmod 644 /path/to/id_ed25519.pub
   chmod 600 /path/to/id_ed25519
   ```

3. **Verify mount path:**
   - Ensure the volume is mounted correctly in docker-compose.yml
   - Path in import dialog must match container path (not host path)

4. **Check key format:**
   ```bash
   # Verify key is valid
   ssh-keygen -l -f /path/to/id_ed25519
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
