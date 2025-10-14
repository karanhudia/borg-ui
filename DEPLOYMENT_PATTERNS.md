# Deployment Patterns

Choose the deployment pattern that fits your environment.

---

## ⭐ Pattern 1: Local Installation (Recommended)

**Best for:** All users, especially beginners

Install Borgmatic UI directly on each machine you want to backup.

### Why This Pattern?
- ✅ Works on **all platforms** (Linux, macOS, Windows)
- ✅ **No network configuration** needed
- ✅ **No SSH setup** required
- ✅ Direct access to local files
- ✅ Better security (no key distribution)
- ✅ Simpler troubleshooting

### Setup

```bash
# On each machine you want to backup:
cd /opt
git clone <repo-url> borgmatic-ui
cd borgmatic-ui

# Start the service
docker-compose up -d

# Access the UI
# http://localhost:8000 (or http://machine-ip:8000)
```

### Multi-Machine Management

Access each instance separately:
- Server 1: `http://192.168.1.10:8000`
- Server 2: `http://192.168.1.20:8000`
- Laptop: `http://localhost:8000`

Optional: Use a reverse proxy (Nginx/Traefik) to unify access:
- `http://backup.local/server1` → `http://192.168.1.10:8000`
- `http://backup.local/server2` → `http://192.168.1.20:8000`

---

## Pattern 2: Central Backup Server with SSH

**Best for:**
- Linux servers only
- Advanced users
- Environments with existing SSH infrastructure

**Not recommended for:**
- Docker Desktop (Mac/Windows)
- Colima users
- Portainer on Mac/Windows

### Requirements
- Linux host with Docker
- SSH access to all target machines
- Network connectivity between backup server and targets
- Manual SSH key distribution

### Setup

```bash
# On your central Linux backup server:
git clone <repo-url> borgmatic-ui
cd borgmatic-ui

# Edit docker-compose.yml - enable host network mode
# Uncomment this line:
# network_mode: "host"

# Start the service
docker-compose up -d
```

### Configure SSH Access

1. Generate SSH keys in the UI
2. Manually distribute public keys to target machines:
   ```bash
   ssh-copy-id -i ~/.ssh/borgmatic_key.pub user@target-machine
   ```
3. Add SSH connections in the UI

### Limitations

This pattern has several limitations:

| Platform | Works? | Notes |
|----------|--------|-------|
| **Linux Docker** | ✅ Yes | Use `network_mode: "host"` |
| **Portainer (Linux)** | ✅ Yes | Use host network stack |
| **Docker Desktop (Mac)** | ❌ No | VM isolation prevents local network access |
| **Docker Desktop (Windows)** | ❌ No | VM isolation prevents local network access |
| **Colima (Mac)** | ⚠️ Workaround | Requires port forwarding or SSH relay |
| **Kubernetes** | ⚠️ Complex | Requires hostNetwork: true pod spec |

**Why these limitations exist:**
Docker Desktop and Colima run Docker inside a VM, which isolates the container from your local network (`192.168.x.x`). The container can only reach the host VM, not your actual local network devices.

---

## Pattern 3: Hybrid Approach

**Best for:** Organizations with mixed environments

- **Install locally** on end-user machines (laptops, workstations)
- **Use central server** for always-on servers

### Benefits
- Laptops/desktops backup when online (no SSH needed)
- Servers managed centrally (SSH works on Linux)
- Flexible deployment

---

## Pattern 4: Kubernetes/Cloud Native

**Best for:** Kubernetes environments, cloud deployments

Deploy as a DaemonSet so each node runs its own Borgmatic UI instance:

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: borgmatic-ui
spec:
  selector:
    matchLabels:
      app: borgmatic-ui
  template:
    metadata:
      labels:
        app: borgmatic-ui
    spec:
      hostNetwork: true  # Access node's network
      containers:
      - name: borgmatic-ui
        image: borgmatic-ui:latest
        ports:
        - containerPort: 8000
        volumeMounts:
        - name: host-root
          mountPath: /backup-source
          readOnly: true
      volumes:
      - name: host-root
        hostPath:
          path: /
```

---

## Decision Matrix

| Your Situation | Recommended Pattern |
|----------------|---------------------|
| Home user backing up 1-2 computers | **Pattern 1** (Local) |
| Home lab with multiple Linux servers | **Pattern 2** (Central) or **Pattern 1** |
| Small business (mixed Windows/Linux) | **Pattern 1** (Local on each) |
| Large organization | **Pattern 3** (Hybrid) |
| Running on Docker Desktop (Mac/Win) | **Pattern 1** (Local) ONLY |
| Running on Portainer (Mac/Win) | **Pattern 1** (Local) ONLY |
| Running on Linux server | **Pattern 1** or **Pattern 2** |
| Kubernetes cluster | **Pattern 4** (DaemonSet) |

---

## Common Questions

### "Can I use Pattern 2 on macOS/Windows?"

Technically yes, but you'll need workarounds:

**For macOS with Colima:**
```bash
# Enable SSH on your Mac
sudo systemsetup -setremotelogin on

# Configure container to use Mac as jump host
# Then Mac can SSH to other machines
```

**For Windows with Docker Desktop:**
```powershell
# Install OpenSSH Server
Add-WindowsCapability -Online -Name OpenSSH.Server

# Same concept - use Windows as jump host
```

**However:** This is complex and error-prone. Pattern 1 is much simpler.

### "I want a unified dashboard for all my backups!"

Two options:

1. **Use a reverse proxy** to access multiple instances through one URL
2. **Build an aggregator service** that polls all Borgmatic UI instances (community contribution welcome!)

### "What about backing up remote VPS/cloud servers?"

Pattern 1 works great! Just install Borgmatic UI on each VPS:
```bash
ssh user@vps1.example.com
docker run -d -p 8000:8000 --name borgmatic-ui borgmatic-ui:latest

ssh user@vps2.example.com
docker run -d -p 8000:8000 --name borgmatic-ui borgmatic-ui:latest
```

Access via SSH tunnels:
```bash
ssh -L 8001:localhost:8000 user@vps1.example.com
ssh -L 8002:localhost:8000 user@vps2.example.com
```

Then access:
- VPS 1: http://localhost:8001
- VPS 2: http://localhost:8002

---

## Summary

**For 90% of users:** Use **Pattern 1** (local installation)

**For advanced Linux users:** Pattern 2 is an option

**For everyone else:** Pattern 1 is simpler, more secure, and actually works
