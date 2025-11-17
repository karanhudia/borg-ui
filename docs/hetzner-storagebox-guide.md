---
layout: default
title: Hetzner Storagebox Guide - Borg Web UI
---

# Hetzner Storagebox & Restricted SSH Environments

This guide explains how to use Borg Web UI with **restricted SSH environments** like Hetzner Storagebox, rsync.net, BorgBase, and other SFTP-only storage services.

## What are Restricted SSH Environments?

Restricted SSH environments are storage services that only allow SFTP (SSH File Transfer Protocol) access and do not permit running arbitrary commands on the remote server.

**Common examples:**
- **Hetzner Storagebox** - German cloud storage provider
- **rsync.net** - Dedicated backup storage
- **BorgBase** - Borg-specific cloud storage
- Various VPS providers offering SFTP-only backup storage

### How Borg Works with SFTP

Good news! **Borg doesn't need to be installed on the remote server** when using SFTP-only storage.

- Borg runs **locally** inside the Borg Web UI container
- Borg uses **SFTP protocol** to transfer data to/from the remote repository
- The remote server only needs to support **SFTP** (not Borg installation)

---

## Hetzner Storagebox Setup Guide

### Prerequisites

1. **Hetzner Storagebox account** (e.g., `u436898@u436898.your-storagebox.de`)
2. **SSH key** configured in your Storagebox (see [Generating SSH Keys](#generating-ssh-keys))
3. **Borg Web UI running** at `http://localhost:8081`

---

### Step 1: Generate SSH Key in Borg Web UI

1. **Navigate to Settings** → **SSH Keys**
2. **Click "Generate New Key"**
3. **Configure the key:**
   - **Name:** `Hetzner Storagebox`
   - **Description:** `SSH key for u436898.your-storagebox.de`
   - **Key Type:** `ED25519` (recommended) or `RSA`
   - **Key Size:** `4096` (if using RSA)
4. **Click "Generate"**

The public and private keys will be generated and stored securely in Borg Web UI.

---

### Step 2: Add Public Key to Hetzner Storagebox

#### Method 1: Using Hetzner Robot Interface (Recommended)

1. **Log in to** [Hetzner Robot](https://robot.hetzner.com/)
2. **Navigate to your Storagebox**
3. **Go to** "SSH-Keys" or "Access" tab
4. **Click "Add SSH Key"**
5. **Copy the public key** from Borg Web UI:
   - In Borg Web UI, click your SSH key
   - Click "Copy Public Key" button
6. **Paste into Hetzner Robot** and save

#### Method 2: Using SFTP

If your Storagebox allows SFTP uploads:

```bash
# Download the public key from Borg Web UI
# Then upload it via SFTP
sftp -P 23 u436898@u436898.your-storagebox.de
> mkdir .ssh
> cd .ssh
> put borg_web_ui_public_key.pub authorized_keys
> chmod 600 authorized_keys
> quit
```

---

### Step 3: Test SSH Connection

Before creating a repository, verify your SSH connection:

```bash
# From your Docker host (optional, for testing)
ssh -p 23 -i /path/to/private/key u436898@u436898.your-storagebox.de

# You should see: "This service allows sftp connections only."
# This is NORMAL and expected!
```

---

### Step 4: Create Repository in Borg Web UI

1. **Navigate to Repositories** → **Create Repository**

2. **Fill in Repository Details:**

   | Field | Value |
   |-------|-------|
   | **Repository Name** | `Hetzner Backup` |
   | **Repository Type** | `SSH` |
   | **Host** | `u436898.your-storagebox.de` |
   | **Port** | `23` (Hetzner Storagebox default) |
   | **Username** | `u436898` (your Storagebox username) |
   | **SSH Key** | Select the key you created in Step 1 |
   | **Remote Path** | `/backup-unraid` (or any path you want) |
   | **Encryption** | `repokey-blake2` (recommended) |
   | **Compression** | `zstd` or `lz4` |
   | **Passphrase** | Enter a strong passphrase |

3. **Source Directories:**
   - Add the directories you want to backup (e.g., `/local/home/user/documents`)
   - You can add multiple directories

4. **Click "Create Repository"**

**Important:** Borg Web UI will automatically detect that Hetzner Storagebox is a restricted SFTP environment and proceed without trying to run remote commands.

---

### Step 5: Run Your First Backup

1. **Navigate to Backups** → **Create Backup**
2. **Select your Hetzner repository**
3. **Click "Start Backup"**

You'll see real-time progress with:
- Files being processed
- Compression ratio
- Deduplication savings
- Transfer speed

---

## Troubleshooting

### Error: "Borg Backup is not installed on remote server"

**This error should NOT appear** with the latest version of Borg Web UI (v1.5.0+).

If you see this error:
1. **Update Borg Web UI** to the latest version:
   ```bash
   docker pull ainullcode/borg-ui:latest
   docker-compose up -d
   ```
2. **Verify the fix** by checking the logs:
   ```bash
   docker logs borg-web-ui | grep "restricted SSH"
   ```
   You should see: "Detected SFTP-only environment (Borg will use SFTP protocol)"

---

### Connection Timeout

**Symptoms:** Repository creation times out or fails to connect

**Solutions:**

1. **Check firewall rules:**
   ```bash
   # Test connection from Docker host
   nc -zv u436898.your-storagebox.de 23
   ```

2. **Verify SSH key is correctly uploaded:**
   ```bash
   ssh -p 23 -i /path/to/key u436898@u436898.your-storagebox.de
   ```

3. **Check Storagebox status:**
   - Visit [Hetzner Status Page](https://status.hetzner.com/)
   - Ensure your Storagebox is active and not suspended

---

### Permission Denied

**Symptoms:** "Permission denied (publickey)"

**Solutions:**

1. **Verify SSH key is added to Storagebox:**
   - Log in to Hetzner Robot
   - Check SSH-Keys section
   - Ensure the key fingerprint matches the one in Borg Web UI

2. **Regenerate SSH key:**
   - Delete the old key in Borg Web UI
   - Generate a new one
   - Re-upload to Hetzner Storagebox

---

### Slow Backup Performance

**Symptoms:** Backup takes much longer than expected

**Solutions:**

1. **Use better compression:**
   - Change from `lz4` to `zstd,3` for better compression (slightly slower)
   - Or use `none` for fastest uploads (larger size)

2. **Check your upload speed:**
   ```bash
   # Speed test to Hetzner
   curl -o /dev/null http://speed.hetzner.de/100MB.bin
   ```

3. **Enable checkpoint intervals:**
   - In repository settings, set checkpoint interval to 300 (5 minutes)
   - This saves progress during long backups

---

## Repository Path Guidelines

When creating repositories on Hetzner Storagebox, use these path conventions:

### Recommended Paths

```
/backup-<hostname>          # e.g., /backup-unraid
/borg/<hostname>            # e.g., /borg/homeserver
/<project-name>/backups     # e.g., /website/backups
```

### Path Rules

- **Must start with `/`** (absolute path)
- **Case-sensitive** (Linux filesystem)
- **No spaces** (use hyphens or underscores)
- **Create parent directories first** via SFTP if needed

### Example SFTP Session

```bash
sftp -P 23 u436898@u436898.your-storagebox.de
> mkdir backups
> mkdir backups/my-server
> quit
```

Then use `/backups/my-server` as your repository path in Borg Web UI.

---

## Security Best Practices

### 1. Use Strong Encryption

Always use `repokey-blake2` or `keyfile-blake2` encryption:
- **blake2** is faster and more secure than SHA-256
- **repokey** stores the key inside the repository (easier recovery)
- **keyfile** stores the key locally (more secure, but you must back it up!)

### 2. Strong Passphrase

Generate a strong passphrase:
```bash
# Generate a random 20-character passphrase
openssl rand -base64 20
```

Store it securely in a password manager (1Password, Bitwarden, LastPass, etc.)

### 3. Rotate SSH Keys

Rotate your SSH keys every 6-12 months:
1. Generate a new SSH key in Borg Web UI
2. Add new key to Hetzner Storagebox
3. Update repositories to use the new key
4. Delete the old key after 24 hours

### 4. Monitor Access

Check Hetzner Storagebox access logs regularly:
- Log in to Hetzner Robot
- Check "Access Logs" or "Statistics"
- Look for unusual connection patterns

---

## Advanced Configuration

### Custom Port

If your Hetzner Storagebox uses a custom port:

```yaml
# In repository settings
Port: 2222  # or your custom port
```

### Multiple Repositories

You can create multiple repositories on the same Storagebox:

```
/backup-server1
/backup-server2
/backup-database
/backup-photos
```

Each repository can have:
- Different encryption keys
- Different compression settings
- Different backup schedules

### Pruning Policy

For Hetzner Storagebox (which charges for storage), configure aggressive pruning:

```
Keep Daily: 7
Keep Weekly: 4
Keep Monthly: 3
Keep Yearly: 1
```

This keeps:
- Last 7 days of daily backups
- Last 4 weeks of weekly backups
- Last 3 months of monthly backups
- Last 1 year of yearly backups

---

## Cost Optimization

### Storage Space

Monitor your repository size:
1. **Navigate to Repositories** → **Select your repository**
2. **Check "Repository Info"** for total size
3. **Run "Compact"** monthly to reclaim space after pruning

### Compression Settings

Test different compression algorithms to find the best balance:

| Compression | Speed | Size Reduction | Best For |
|-------------|-------|----------------|----------|
| `none` | Fastest | 0% | Pre-compressed files (videos, images) |
| `lz4` | Very Fast | 20-30% | General use, text files |
| `zstd,1` | Fast | 30-40% | Good balance |
| `zstd,3` | Medium | 40-50% | Better compression |
| `zlib,6` | Slow | 50-60% | Maximum compression |

### Deduplication

Borg automatically deduplicates data across all archives. To maximize deduplication:
- Keep similar files in the same repository
- Don't encrypt individual files before backup (Borg encrypts everything)
- Avoid compressed archives (ZIP, tar.gz) inside backups

---

## Comparison: Hetzner Storagebox vs Other Providers

| Feature | Hetzner Storagebox | rsync.net | BorgBase |
|---------|-------------------|-----------|----------|
| **Storage Sizes** | 100GB - 20TB | 1TB+ | 250GB - 5TB |
| **Price (1TB/month)** | €3.81 | $18 | $12 |
| **SSH Port** | 23 | 22 | 22 |
| **Borg Support** | ✅ SFTP | ✅ Native | ✅ Native |
| **Snapshots** | ✅ | ✅ | ✅ |
| **European Data** | ✅ Germany | ❌ USA | ✅ EU |
| **Setup Complexity** | Medium | Easy | Easy |

---

## Example: Complete Workflow

Here's a complete example of setting up backups for a home server to Hetzner Storagebox:

### 1. Purchase Storagebox

- Visit [Hetzner Robot](https://robot.hetzner.com/)
- Order Storagebox (e.g., 1TB BX31 - €3.81/month)
- Note your credentials: `u436898@u436898.your-storagebox.de`

### 2. Generate SSH Key

- In Borg Web UI: Settings → SSH Keys → Generate
- Name: `Hetzner BX31`
- Type: ED25519

### 3. Upload Key to Storagebox

- Copy public key from Borg Web UI
- Paste into Hetzner Robot → Storagebox → SSH Keys

### 4. Create Repository

- Repositories → Create
- Host: `u436898.your-storagebox.de`
- Port: 23
- Username: `u436898`
- Path: `/backup-homeserver`
- Encryption: `repokey-blake2`
- Compression: `zstd,3`

### 5. Add Source Directories

```
/local/home/user/documents
/local/home/user/photos
/local/etc
```

### 6. Create First Backup

- Backups → Create Backup
- Select "Hetzner BX31" repository
- Wait for completion (monitor progress in real-time)

### 7. Schedule Automated Backups

- Schedules → Create Schedule
- Repository: "Hetzner BX31"
- Frequency: Daily at 2:00 AM
- Retention: 7 daily, 4 weekly, 3 monthly

### 8. Test Restoration

- Archives → Select recent archive
- Browse files → Select a test file
- Restore to `/local/tmp/restore-test`
- Verify file integrity

---

## Getting Help

If you encounter issues:

1. **Check Borg Web UI logs:**
   ```bash
   docker logs borg-web-ui | tail -100
   ```

2. **Test SSH connection manually:**
   ```bash
   ssh -p 23 -v u436898@u436898.your-storagebox.de
   ```

3. **Open a GitHub Issue:**
   - [Borg Web UI Issues](https://github.com/karanhudia/borg-ui/issues)
   - Include logs, error messages, and configuration

4. **Hetzner Support:**
   - [Hetzner Docs: Storage Box](https://docs.hetzner.com/robot/storage-box/)
   - [Hetzner Support Portal](https://accounts.hetzner.com/)

---

## Additional Resources

- **Official Borg Documentation:** https://borgbackup.readthedocs.io/
- **Hetzner Storagebox Docs:** https://docs.hetzner.com/robot/storage-box/
- **Borg Web UI Repository:** https://github.com/karanhudia/borg-ui
- **Borg Web UI Docs:** https://karanhudia.github.io/borg-ui

---

**Last Updated:** 2025-11-17
**Borg Web UI Version:** 1.5.0+
