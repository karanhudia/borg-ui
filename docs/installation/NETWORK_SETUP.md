# Network Setup Guide

This guide helps you configure networking so the Borgmatic UI container can access SSH servers on your network.

## Understanding the Network Issue

When running in Docker, the container is isolated from your host machine's network. This means:
- ✅ Container can access the internet
- ✅ Container can access other containers on the same Docker network
- ❌ Container **cannot** directly access devices on your local network (e.g., `192.168.1.x`)

## Solution Options

Choose the deployment option that works best for your environment:

---

### **Option 1: Host Network Mode** (Linux only, simplest)

**Best for:** Linux servers, dedicated backup servers

**Setup:**
```yaml
# docker-compose.yml
services:
  borgmatic-ui:
    network_mode: "host"
    # Remove ports section when using host mode
```

**Pros:**
- Container has direct access to all network interfaces
- Can SSH to any device on your network
- Simplest configuration

**Cons:**
- ⚠️ Only works on **Linux** (not macOS/Windows)
- ⚠️ Container uses host's network namespace (less isolation)

---

### **Option 2: Bridge Network with Port Forwarding** (Recommended for most users)

**Best for:** Docker Desktop (Mac/Windows), Portainer, Colima

**Setup:**
```yaml
# docker-compose.yml
services:
  borgmatic-ui:
    ports:
      - "8000:8000"
    networks:
      - borgmatic-network
```

**Access SSH servers using:**

1. **Via Host IP:** If your Docker host is `192.168.1.48`, SSH to `192.168.1.48:22` from the container
2. **Using host.docker.internal:** Reference `host.docker.internal` to reach your host machine
3. **Port Mapping:** Expose SSH servers through Docker host

**Example:**
```bash
# If your target SSH server is 192.168.1.150:22
# And your Docker host is 192.168.1.48
# You can:

# 1. SSH via the Docker host as a jump host
ssh -J user@192.168.1.48 user@192.168.1.150

# 2. Or add this to docker-compose.yml
extra_hosts:
  - "target-server:192.168.1.150"  # Won't work if on different network
```

---

### **Option 3: Install on the Target Machines** (Best practice)

**Best for:** Production environments, security-conscious setups

Instead of deploying centrally and SSHing to other machines, **install Borgmatic UI directly on each machine** you want to backup.

**Benefits:**
- ✅ No SSH required
- ✅ Direct access to local files
- ✅ Better security (no key distribution)
- ✅ No network configuration needed

**Setup:**
```bash
# On each machine you want to backup:
git clone https://github.com/your-repo/borgmatic-ui
cd borgmatic-ui
docker-compose up -d

# Access each instance at:
# http://server1:8000
# http://server2:8000
```

---

### **Option 4: SSH Tunnel from Host** (Workaround)

**Best for:** Testing, temporary setups

Create SSH tunnels from your Docker host to forward connections:

```bash
# On your Docker host (Mac/Windows/Linux)
# Forward container requests to your local network

# Example: Forward port 2222 to 192.168.1.150:22
ssh -L 2222:192.168.1.150:22 -N user@192.168.1.150 &

# Then in Borgmatic UI, connect to:
# Host: host.docker.internal
# Port: 2222
```

---

### **Option 5: Macvlan Network** (Advanced)

**Best for:** Advanced users, home lab setups

Give your container its own IP address on your local network:

```yaml
# docker-compose.yml
services:
  borgmatic-ui:
    networks:
      borgmatic-macvlan:
        ipv4_address: 192.168.1.200

networks:
  borgmatic-macvlan:
    driver: macvlan
    driver_opts:
      parent: eth0  # Your network interface
    ipam:
      config:
        - subnet: 192.168.1.0/24
          gateway: 192.168.1.1
          ip_range: 192.168.1.200/29  # Reserve IPs for containers
```

**Note:** Requires Docker host network interface configuration.

---

## Testing Network Connectivity

Once configured, test connectivity from inside the container:

```bash
# Check if you can reach the target server
docker exec borgmatic-web-ui ping -c 3 192.168.1.150

# Test SSH connectivity
docker exec borgmatic-web-ui ssh -o ConnectTimeout=5 user@192.168.1.150 echo "success"

# Check routing
docker exec borgmatic-web-ui ip route
```

---

## Recommended Setup by Environment

| Environment | Recommended Option | Reason |
|-------------|-------------------|---------|
| **Linux Server** | Host Network Mode | Direct network access, simplest |
| **macOS/Windows Desktop** | Option 3 (Per-machine install) | Most reliable |
| **Portainer** | Bridge + Port Forwarding | Standard Docker networking |
| **Home Lab** | Macvlan | Container gets real IP |
| **Production** | Option 3 (Per-machine install) | Best security practice |

---

## Current Configuration

This repository is configured for **Bridge Network Mode** (Option 2) which works on all platforms.

To use **Host Network Mode** on Linux:
```bash
# Edit docker-compose.yml
nano docker-compose.yml

# Change:
# network_mode: "bridge"
# To:
network_mode: "host"

# Then restart:
docker-compose down && docker-compose up -d
```

---

## Troubleshooting

### Container can't reach SSH servers

1. **Check Docker network mode:**
   ```bash
   docker inspect borgmatic-web-ui | grep NetworkMode
   ```

2. **Test from host first:**
   ```bash
   # If you can't SSH from the Docker host, container won't be able to either
   ssh user@192.168.1.150
   ```

3. **Check firewall rules:**
   - Ensure SSH port (22) is open on target servers
   - Check Docker host firewall isn't blocking forwarded connections

4. **Verify routing:**
   ```bash
   docker exec borgmatic-web-ui traceroute 192.168.1.150
   ```

### "Connection refused" errors

- Target SSH server isn't running
- Firewall blocking connections
- Wrong port (check if SSH is on port 22)

### "Network unreachable" errors

- Container is on isolated network
- No route from container's network to target network
- Need to use Option 1, 3, or 5

---

## Security Considerations

- **Host Network Mode** reduces container isolation
- **Macvlan** requires careful IP management
- **Per-machine installation** (Option 3) is most secure
- Always use strong SSH key passphrases
- Regularly rotate SSH keys
- Monitor SSH connection logs

---

## Questions?

If you're still having network issues:
1. Run the network test commands above
2. Check which Docker platform you're using (Linux/Mac/Windows/Portainer)
3. Share the output in an issue: https://github.com/your-repo/issues
