---
layout: default
title: Usage Guide - Borg Web UI
---

# Usage Guide: Creating Backups

This guide shows you how to create backups using Borg Web UI. There are two main methods:

1. **Local Backups** - Backup to storage attached to your Docker host (USB drives, NAS mounts, etc.)
2. **SSH/Remote Backups** - Backup to remote servers via SSH

Both methods follow the same workflow, with one key difference: **SSH backups require SSH key setup**.

---

## Table of Contents

- [Understanding Backup Types](#understanding-backup-types)
- [Prerequisites](#prerequisites)
- [Method 1: Local Backups](#method-1-local-backups-recommended-for-beginners)
- [Method 2: SSH/Remote Backups](#method-2-sshremote-backups)
- [Running Your First Backup](#running-your-first-backup)
- [Scheduling Automated Backups](#scheduling-automated-backups)
- [Restoring from Backups](#restoring-from-backups)

---

## Understanding Backup Types

### Local Backups

**What is it?**
Stores backup data on storage directly accessible to your Docker host machine.

**Best for:**
- USB external drives
- Network-attached storage (NAS) mounted via NFS/CIFS
- Additional internal drives
- Same-machine backups

**Advantages:**
- ✅ Simple setup (no SSH keys needed)
- ✅ Faster backup speeds (no network overhead)
- ✅ Works offline
- ✅ Lower latency

**Disadvantages:**
- ❌ No off-site protection (if your machine fails, backups may be lost)
- ❌ Requires physical storage

---

### SSH/Remote Backups

**What is it?**
Stores backup data on a remote server accessible via SSH.

**Best for:**
- Remote VPS/cloud servers
- Off-site backup targets (Raspberry Pi at another location)
- Storage servers without NFS/CIFS
- Professional/enterprise setups

**Advantages:**
- ✅ Off-site protection (survives local disasters)
- ✅ No need to mount network drives
- ✅ Works across the internet
- ✅ Industry-standard secure protocol

**Disadvantages:**
- ❌ Requires SSH key setup
- ❌ Slower over internet connections
- ❌ Requires remote server access

---

## Prerequisites

Before creating backups, ensure:

1. **Borg Web UI is running**: `http://localhost:8081`
2. **You're logged in** (default: `admin` / `admin123`)
3. **Container has proper permissions**: Set `PUID`/`PGID` if needed (see [Troubleshooting > Permission Issues](https://github.com/karanhudia/borg-ui#permission-issues))

---

## Method 1: Local Backups (Recommended for Beginners)

### What You'll Need

- A storage location on your Docker host machine
- The path to that storage (e.g., `/mnt/usb-drive`, `/mnt/nas`)

### Understanding `/local` Mount

**Key Concept:** The container automatically mounts your host filesystem at `/local`.

By default:
- **Host path**: `/` (your entire filesystem)
- **Container path**: `/local`

This means:
- Host `/home/user/backups` → Container `/local/home/user/backups`
- Host `/mnt/usb-drive/borg` → Container `/local/mnt/usb-drive/borg`

You can customize this via the `LOCAL_STORAGE_PATH` environment variable (see [Configuration](#customizing-local-mount)).

---

### Step 1: Prepare Your Storage Location (On Host)

First, create a directory on your host machine where backups will be stored.

**For Linux/Raspberry Pi:**

```bash
# Option A: USB external drive (assuming mounted at /mnt/usb-drive)
sudo mkdir -p /mnt/usb-drive/borg-backups
sudo chown $(id -u):$(id -g) /mnt/usb-drive/borg-backups

# Option B: NAS mount (assuming mounted at /mnt/nas)
sudo mkdir -p /mnt/nas/borg-backups
sudo chown $(id -u):$(id -g) /mnt/nas/borg-backups

# Option C: Home directory
mkdir -p ~/backups/borg-repos
```

**For macOS:**

```bash
# Option A: External drive
mkdir -p /Volumes/MyExternalDrive/borg-backups

# Option B: Home directory
mkdir -p ~/backups/borg-repos
```

**Important:** Ensure your Docker user (set via `PUID`/`PGID`) has write permissions to this directory!

---

### Step 2: Create a Repository in Borg Web UI

A **repository** is where Borg stores your encrypted backup data.

1. **Navigate to Repositories**
   Click **"Repositories"** in the sidebar

2. **Click "Create Repository"**

3. **Fill in Repository Details:**

   | Field | Example Value | Description |
   |-------|---------------|-------------|
   | **Repository Name** | `my-laptop-backup` | Friendly name for identification |
   | **Repository Path** | `/local/mnt/usb-drive/borg-backups/laptop` | Path **inside the container** (use `/local/` prefix!) |
   | **Encryption Mode** | `repokey-blake2` | Recommended for best security |
   | **Passphrase** | `your-strong-password-123` | **Store this safely!** You cannot recover data without it. |

   **Path Translation Examples:**

   | Host Path | Container Path (use this in UI) |
   |-----------|----------------------------------|
   | `/mnt/usb-drive/borg-backups/laptop` | `/local/mnt/usb-drive/borg-backups/laptop` |
   | `/mnt/nas/backups/myrepo` | `/local/mnt/nas/backups/myrepo` |
   | `/home/user/backups/data` | `/local/home/user/backups/data` |
   | `~/backups/borg-repos/myrepo` | `/local/home/<username>/backups/borg-repos/myrepo` |

4. **Configure Compression (Optional)**
   - **Recommended**: `lz4` (fast) or `zstd,3` (balanced)
   - Leave default if unsure

5. **Add Source Paths**
   Click **"Add Source Path"** and specify what to backup:

   **Examples:**
   - `/local/home/user/Documents` - Backup Documents folder
   - `/local/var/www` - Backup web server files
   - `/local/etc` - Backup configuration files

   **⚠️ Important:** Use `/local/` prefix for paths inside the container!

6. **Review and Create**
   - Check the auto-generated command preview
   - Click **"Create Repository"**

7. **Success!**
   You'll see your repository listed with status "Active"

---

### Step 3: Run Your First Backup

Now that your repository is created, let's create your first backup (called an "archive" in Borg).

1. **Navigate to Backup Tab**
   Click **"Backup"** in the sidebar

2. **Select Repository**
   Choose `my-laptop-backup` from the dropdown

3. **Optional: Add Exclude Patterns**
   Exclude files you don't want to backup:
   ```
   **/.git
   **/node_modules
   **/__pycache__
   **/.DS_Store
   **/Thumbs.db
   ```

4. **Click "Start Backup"**

5. **Watch Progress in Real-Time:**
   - Current file being processed
   - Files processed count
   - Original size vs. compressed size
   - Deduplicated size (space saved!)
   - Speed and ETA

6. **Completion**
   Once finished, you'll see:
   - Total files processed
   - Original size → Compressed → Deduplicated
   - Duration and average speed
   - Backup archive name (e.g., `2025-10-22T10-30-45`)

**🎉 Congratulations!** Your first local backup is complete.

---

### Customizing Local Mount

By default, the entire host filesystem (`/`) is mounted at `/local`. You can restrict this:

**Edit `docker-compose.yml` or `.env`:**

```yaml
volumes:
  # Option 1: Mount only user directories (Linux)
  - /home:/local:rw

  # Option 2: Mount only user directories (macOS)
  - /Users:/local:rw

  # Option 3: Mount only NAS
  - /mnt/nas:/local:rw
```

Or in `.env`:
```bash
LOCAL_STORAGE_PATH=/home
```

Then use repository paths like `/local/username/backups/repo`.

---

## Method 2: SSH/Remote Backups

### What You'll Need

- A remote server with:
  - SSH access (username and IP/hostname)
  - Borg installed (`sudo apt install borgbackup` or equivalent)
  - A directory for backups
- SSH key pair (we'll generate this in the UI)

---

### Step 1: Generate or Import SSH Key

SSH keys authenticate your connection to the remote server without passwords.

1. **Navigate to SSH Keys**
   Click **"SSH Keys"** in the sidebar

2. **Generate New Key**
   Click **"Generate Key Pair"**

   | Field | Example | Description |
   |-------|---------|-------------|
   | **Key Name** | `backup-server-key` | Friendly identifier |
   | **Key Type** | `ed25519` | Recommended (secure & fast) |
   | **Comment** | `borg-ui@myhost` | Optional label |

3. **Download Private Key** (Optional)
   - Click **"Download Private Key"** to save a backup
   - Store safely (this is your authentication credential!)

4. **Copy Public Key**
   Click **"Copy Public Key"** - you'll need this for the next step

---

### Step 2: Deploy Public Key to Remote Server

The remote server needs your public key to allow connections.

**Option A: Automatic Deployment (Recommended)**

1. In the SSH Keys list, click **"Deploy"** next to your key

2. Fill in deployment details:

   | Field | Example | Description |
   |-------|---------|-------------|
   | **Hostname** | `192.168.1.100` or `backup.example.com` | IP or domain of remote server |
   | **Port** | `22` | SSH port (usually 22) |
   | **Username** | `backupuser` | SSH username on remote server |
   | **Password** | `server-password` | Temporary (only for deployment) |

3. Click **"Deploy Key"**
   The UI will automatically add your public key to `~/.ssh/authorized_keys` on the remote server.

4. **Success!**
   You can now use this key for SSH repositories.

**Option B: Manual Deployment**

If automatic deployment fails, do this manually on the **remote server**:

```bash
# SSH into your remote server
ssh user@192.168.1.100

# Create SSH directory if it doesn't exist
mkdir -p ~/.ssh
chmod 700 ~/.ssh

# Add public key (paste the key you copied from UI)
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... borg-ui@myhost" >> ~/.ssh/authorized_keys

# Set correct permissions
chmod 600 ~/.ssh/authorized_keys

# Exit
exit
```

---

### Step 3: Test SSH Connection

Before creating a repository, verify the SSH connection works:

1. In **SSH Keys** tab, find your key
2. Click **"Test Connection"**
3. Enter remote server details:
   - Hostname: `192.168.1.100`
   - Port: `22`
   - Username: `backupuser`

4. If successful, you'll see: ✅ **"Connection successful!"**

---

### Step 4: Prepare Remote Storage Directory

On the **remote server**, create a directory for Borg repositories:

```bash
# SSH into remote server
ssh backupuser@192.168.1.100

# Create backup directory
mkdir -p ~/borg-backups

# Ensure Borg is installed
borg --version
# If not installed: sudo apt install borgbackup

# Exit
exit
```

---

### Step 5: Create SSH Repository in Borg Web UI

Now create a repository that uses SSH to store data remotely.

1. **Navigate to Repositories**
   Click **"Repositories"** in the sidebar

2. **Click "Create Repository"**

3. **Fill in Repository Details:**

   | Field | Example Value | Description |
   |-------|---------------|-------------|
   | **Repository Name** | `offsite-backup` | Friendly name |
   | **Repository Path** | `backupuser@192.168.1.100:borg-backups/myrepo` | SSH format: `user@host:path` |
   | **SSH Key** | `backup-server-key` | Select the key you created earlier |
   | **Encryption Mode** | `repokey-blake2` | Recommended |
   | **Passphrase** | `your-strong-password-456` | **Store safely!** |

   **SSH Path Format:**
   ```
   username@hostname:/absolute/path
   username@hostname:relative/path
   user@example.com:/home/user/backups/repo
   user@192.168.1.100:borg-backups/data
   ```

4. **Configure Compression** (Optional)
   - **Over Fast Network**: `lz4` (fast)
   - **Over Slow Network**: `zstd,3` (more compression = less data transferred)

5. **Add Source Paths**
   What to backup (same as local backups):
   ```
   /local/home/user/Documents
   /local/var/www/html
   /local/etc/nginx
   ```

6. **Click "Create Repository"**

7. **Success!**
   Repository is now active and ready for backups.

---

### Step 6: Run Your First SSH Backup

The process is **identical to local backups**:

1. **Navigate to Backup Tab**
2. **Select your SSH repository** (`offsite-backup`)
3. **Optional: Add exclude patterns**
4. **Click "Start Backup"**
5. **Watch real-time progress**

**Note:** SSH backups may be slower than local backups due to network speed, but Borg's deduplication minimizes data transfer after the first backup.

---

## Commonalities Between Local and SSH Backups

Both methods share the same workflow after repository creation:

### 1. **Backup Process** (Identical)
- Select repository
- Add exclude patterns
- Start backup
- Monitor progress
- View completion statistics

### 2. **Archive Management** (Identical)
- Browse backups in **Archives** tab
- View archive contents
- Restore files
- Delete old archives

### 3. **Scheduling** (Identical)
- Create scheduled jobs in **Schedule** tab
- Set cron expressions (daily, weekly, etc.)
- Monitor execution history

### 4. **Monitoring** (Identical)
- View backup history
- Download logs
- Check repository statistics

---

## Key Differences Summary

| Feature | Local Backups | SSH/Remote Backups |
|---------|---------------|-------------------|
| **Setup Complexity** | ⭐ Simple | ⭐⭐ Moderate (SSH key required) |
| **Speed** | 🚀 Fast | 🐌 Depends on network |
| **Off-site Protection** | ❌ No | ✅ Yes |
| **Storage** | Must be attached to host | Any SSH-accessible server |
| **Key Requirement** | ❌ None | ✅ SSH key needed |
| **Path Format** | `/local/path/to/repo` | `user@host:path/to/repo` |

---

## Running Your First Backup

Regardless of method (local or SSH), the backup process is the same:

### Using the Backup Tab (Manual Backup)

1. **Go to Backup Tab**
2. **Select Repository** from dropdown
3. **(Optional) Add Exclude Patterns:**
   ```
   **/.git
   **/node_modules
   **/__pycache__
   **/*.tmp
   **/*.log
   ```

4. **Click "Start Backup"**
5. **Monitor Progress:**
   - Current file being processed
   - Files processed
   - Original size vs compressed vs deduplicated
   - Backup speed and ETA

6. **Completion:**
   - View summary statistics
   - Download logs if needed

---

## Scheduling Automated Backups

Set up automated backups to run on a schedule:

### Step 1: Navigate to Schedule Tab

Click **"Schedule"** in the sidebar.

### Step 2: Create Scheduled Job

1. Click **"Create Job"**

2. Fill in details:

   | Field | Example | Description |
   |-------|---------|-------------|
   | **Job Name** | `Daily Documents Backup` | Descriptive name |
   | **Repository** | `my-laptop-backup` | Select your repository |
   | **Schedule** | `0 2 * * *` | Cron expression (2 AM daily) |
   | **Description** | `Backup documents every night` | Optional notes |
   | **Enabled** | ✅ | Start immediately |

3. **Use Preset Schedules:**
   Click the clock icon (⏰) to choose from presets:
   - Every 5 minutes
   - Every hour
   - Daily at 2 AM
   - Weekly on Sunday
   - Monthly on 1st

4. **Click "Create Job"**

### Step 3: Monitor Scheduled Jobs

- View **Next Run** time
- See **Last Run** status
- Check **Backup History** for execution logs

### Step 4: View Running Jobs

When a scheduled backup is running, you'll see it in the **"Running Scheduled Backups"** section with real-time progress.

---

## Restoring from Backups

### Step 1: Browse Archives

1. **Navigate to Archives Tab**
2. **Select Repository**
3. **View list of backups** (sorted by date)

### Step 2: Browse Archive Contents

1. Click **"Browse"** on any archive
2. Navigate through directories
3. Search for specific files

### Step 3: Extract Files

1. Select files/directories to restore
2. Click **"Extract Selected"**
3. Choose destination:
   - **Local**: `/local/home/user/restored-files`
   - **SSH**: Restore to remote server

4. Click **"Start Restore"**
5. Monitor progress

**🎉 Files restored!**

---

## Best Practices

### For Local Backups

1. **Use external storage** - Don't backup to the same drive as your data
2. **Test restores regularly** - Backups are useless if you can't restore
3. **Consider off-site copies** - Add an SSH backup for critical data
4. **Monitor disk space** - Set up pruning/retention policies

### For SSH Backups

1. **Use strong passphrases** - Both for SSH keys and repository encryption
2. **Keep SSH keys secure** - Download and store private keys safely
3. **Test connectivity first** - Use "Test Connection" before creating repositories
4. **Use compression** - Saves bandwidth over slow connections
5. **Dedicated backup user** - Create a separate SSH user on remote server

### General

1. **Never lose your passphrase** - Write it down, use a password manager
2. **Schedule backups during off-hours** - Reduces impact on system performance
3. **Use exclude patterns** - Don't backup cache, logs, or temporary files
4. **Monitor backup jobs** - Check logs regularly for errors
5. **Prune old archives** - Set retention policies to manage storage

---

## Troubleshooting

### Common Issues

#### "Permission denied" when creating repository

**Cause:** Docker user doesn't have write access to storage location.

**Solution:** Set `PUID`/`PGID` in docker-compose.yml:

```yaml
environment:
  - PUID=1000  # Your user ID (run: id -u)
  - PGID=1000  # Your group ID (run: id -g)
```

Restart container: `docker compose down && docker compose up -d`

---

#### SSH connection fails

**Causes:**
1. Public key not deployed correctly
2. Wrong hostname/port/username
3. Firewall blocking SSH
4. Remote server doesn't have Borg installed

**Solutions:**
1. Use **"Test Connection"** to diagnose
2. Verify `~/.ssh/authorized_keys` on remote server
3. Check firewall rules: `sudo ufw allow 22/tcp`
4. Install Borg: `sudo apt install borgbackup`

---

#### Backup is very slow

**For Local:**
- Check disk I/O performance
- Reduce compression level
- Exclude unnecessary files

**For SSH:**
- Use faster compression (`lz4` or `none`)
- Check network speed
- Consider initial backup over LAN, then move to remote location

---

#### "Repository not found" error

**Cause:** Path is incorrect or repository wasn't created successfully.

**Solution:**
1. Verify path format:
   - Local: `/local/mnt/usb-drive/backups/repo`
   - SSH: `user@host:backups/repo`

2. Check repository exists:
   ```bash
   # For local
   docker exec borg-web-ui ls -la /local/mnt/usb-drive/backups

   # For SSH
   ssh user@host ls -la ~/backups
   ```

3. Re-create repository if needed

---

## Next Steps

- **[Scheduling Guide](https://github.com/karanhudia/borg-ui#scheduling)** - Automate your backups
- **[Archives Browser](https://github.com/karanhudia/borg-ui#archive-browser)** - Browse and restore files
- **[API Documentation](http://localhost:8081/api/docs)** - Integrate with other tools
- **[Troubleshooting Guide](https://github.com/karanhudia/borg-ui#troubleshooting)** - Common issues

---

## Summary

### Local Backups in 3 Steps:
1. **Create storage directory** on host
2. **Create repository** using `/local/path/to/repo`
3. **Run backup** - no SSH key needed!

### SSH Backups in 6 Steps:
1. **Generate SSH key** in UI
2. **Deploy public key** to remote server
3. **Test connection**
4. **Prepare remote directory**
5. **Create repository** using `user@host:path`
6. **Run backup**

**The difference?** Just the SSH key setup. Everything else is identical!

---

**Need Help?**
- 📖 [Full Documentation](https://karanhudia.github.io/borg-ui)
- 🐛 [Report Issues](https://github.com/karanhudia/borg-ui/issues)
- 💬 [GitHub Discussions](https://github.com/karanhudia/borg-ui/discussions)
