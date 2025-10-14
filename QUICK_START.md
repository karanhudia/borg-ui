# Quick Start Guide

## Choose Your Platform

### 🐧 **Linux / Linux Server**

```bash
# Clone the repository
git clone <repo-url>
cd borgmatic-ui

# Start (uses host network by default - works out of the box!)
docker-compose up -d

# Access at http://localhost:8000
# Default login: admin / admin123
```

✅ **Works immediately** - container can access your local network directly

---

### 🍎 **macOS (Docker Desktop / Colima)**

```bash
# Clone the repository
git clone <repo-url>
cd borgmatic-ui

# Start with macOS override
docker-compose -f docker-compose.yml -f docker-compose.macos.yml up -d

# Access at http://localhost:8000
# Default login: admin / admin123
```

⚠️ **Network limitation:** Container cannot directly access `192.168.1.x` devices
📖 **See:** [NETWORK_SETUP.md](./NETWORK_SETUP.md) for solutions

---

### 🪟 **Windows (Docker Desktop)**

```bash
# Clone the repository
git clone <repo-url>
cd borgmatic-ui

# Start with macOS override (works for Windows too)
docker-compose -f docker-compose.yml -f docker-compose.macos.yml up -d

# Access at http://localhost:8000
# Default login: admin / admin123
```

⚠️ **Network limitation:** Container cannot directly access local network devices
📖 **See:** [NETWORK_SETUP.md](./NETWORK_SETUP.md) for solutions

---

### 🚢 **Portainer**

1. **Stacks** → **Add Stack**
2. **Name:** `borgmatic-ui`
3. **Upload** `docker-compose.yml`
4. **Deploy**

**For network access to local devices:**
- Linux Portainer: Works out of the box (host network)
- macOS/Windows Portainer: See [NETWORK_SETUP.md](./NETWORK_SETUP.md)

---

## Network Modes Explained

### **Host Network** (Default for Linux)
- ✅ Direct access to all network interfaces
- ✅ Can SSH to any device on your network
- ✅ Best for backup servers
- ❌ Only works on Linux

### **Bridge Network** (Default for macOS/Windows)
- ✅ Works on all platforms
- ✅ Container isolation
- ❌ Cannot directly access host's local network
- 💡 Use per-machine installation instead (recommended)

---

## Testing Network Connectivity

```bash
# Test if container can reach your SSH server
docker exec borgmatic-web-ui ping -c 3 192.168.1.150

# Or use the built-in network debugger
# Login to UI → http://localhost:8000/api/settings/debug/network?host=192.168.1.150
```

---

## Common Scenarios

### **Scenario 1: Backup a single machine**
✅ **Best solution:** Install Borgmatic UI directly on that machine

```bash
# On the machine you want to backup
docker-compose up -d
# Access at http://machine-ip:8000
```

### **Scenario 2: Backup multiple machines from one central location**
✅ **Best solution:** Use host network on Linux server

```bash
# On your Linux backup server
docker-compose up -d
# SSH to all other machines from here
```

### **Scenario 3: Using macOS/Windows as backup coordinator**
⚠️ **Challenge:** Docker Desktop isolates container from local network

**Options:**
1. **Install on each target machine** (recommended)
2. **Use SSH jump host** (your Mac/Windows as gateway)
3. **Reconfigure Colima/Docker Desktop** (see NETWORK_SETUP.md)

---

## Next Steps

1. **Login:** http://localhost:8000 (admin / admin123)
2. **Change password:** Settings → Profile
3. **Generate SSH key:** SSH Keys → Generate New Key
4. **Test connectivity:** Use network debugger endpoint
5. **Configure backup:** See full documentation

---

## Need Help?

- 📖 **Network issues?** → [NETWORK_SETUP.md](./NETWORK_SETUP.md)
- 🐛 **Bug or issue?** → [GitHub Issues](https://github.com/your-repo/issues)
- 💬 **Questions?** → [Discussions](https://github.com/your-repo/discussions)

---

## Pro Tips

💡 **For most users:** Install Borgmatic UI on each machine you want to backup, rather than trying to SSH from one central location

💡 **For homelab/servers:** Use host network mode on Linux for simplest setup

💡 **For cloud VPS:** Host network mode works perfectly

💡 **For Docker Desktop (Mac/Win):** Consider using a Linux VM or WSL2 instead
